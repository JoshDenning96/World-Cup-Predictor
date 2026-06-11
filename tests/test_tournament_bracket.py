"""
Tests for tournament simulation and bracket correctness.

Three categories:
  1. Slot resolution  — deterministic tests for _resolve_group_placement,
                        _build_round_of_32_third_place_assignment_map, and
                        _resolve_round_of_32_third_place.
  2. Mathematical invariants — probability sums and monotonicity across all
                        knockout stages.
  3. Dominant-team oracle — a near-invincible team should win the tournament
                        in the vast majority of simulations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from world_cup_predictor.simulator import (
    _R32_WINNER_GROUP_ORDER,
    _build_round_of_32_third_place_assignment_map,
    _resolve_group_placement,
    _resolve_round_of_32_third_place,
    simulate_full_tournament,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

GROUPS = list("ABCDEFGHIJKL")


def _make_standings(teams_in_order: list[str], pts_seq: tuple = (9, 6, 3, 0)) -> pd.DataFrame:
    """Return a standings DataFrame already sorted best-first."""
    n = len(teams_in_order)
    return pd.DataFrame(
        {
            "points": list(pts_seq[:n]),
            "played": [3] * n,
            "goals_for": [6, 4, 2, 1][:n],
            "goals_against": [1, 2, 4, 7][:n],
            "goal_difference": [5, 2, -2, -6][:n],
        },
        index=teams_in_order,
    )


def _make_full_standings(third_pts: dict[str, int] | None = None) -> dict[str, pd.DataFrame]:
    """Build standings_by_group for all 12 groups.

    third_pts maps group letter → points for the 3rd-place team (default 3).
    The goal difference for strong 3rd-place teams (pts=9) is set positive and
    for weak ones (pts=0) negative so sort order is unambiguous.
    """
    if third_pts is None:
        third_pts = {}
    result: dict[str, pd.DataFrame] = {}
    for g in GROUPS:
        t3_pts = third_pts.get(g, 3)
        t3_gf = 3 if t3_pts >= 6 else 2
        t3_ga = 2 if t3_pts >= 6 else 4
        standings = pd.DataFrame(
            {
                "points": [9, 6, t3_pts, 0],
                "played": [3, 3, 3, 3],
                "goals_for": [6, 4, t3_gf, 1],
                "goals_against": [1, 2, t3_ga, 7],
                "goal_difference": [5, 2, t3_gf - t3_ga, -6],
            },
            index=[f"{g}1", f"{g}2", f"{g}3", f"{g}4"],
        )
        result[f"Group {g}"] = standings
    return result


def _make_wc_fixture() -> pd.DataFrame:
    """Minimal structurally-correct WC 2026 fixture.

    Uses synthetic team names (A1, A2, …, L4) and the real R32 slot strings
    from the official fixture. Later knockout rounds use 'To be announced'
    so the simulator pairs previous-round winners sequentially.

    Each knockout round gets a distinct date so sort_values('date') preserves
    the correct round order when building round_order inside simulate_full_tournament.
    """
    rows: list[dict] = []
    base_date = pd.Timestamp("2026-06-11")
    match_num = 1

    # Group stage — full round-robin (6 matches per group, 72 total)
    for g in GROUPS:
        teams = [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                rows.append(
                    {
                        "match_number": match_num,
                        "round_number": "1",
                        "group": f"Group {g}",
                        "home_team": teams[i],
                        "away_team": teams[j],
                        "date": base_date,
                    }
                )
                match_num += 1

    # Round of 32 — exact slot pairings from the WC 2026 fixture
    r32_slots = [
        ("2A", "2B"),
        ("1C", "2F"),
        ("1E", "3ABCDF"),
        ("1F", "2C"),
        ("2E", "2I"),
        ("1I", "3CDFGH"),
        ("1A", "3CEFHI"),
        ("1L", "3EHIJK"),
        ("1G", "3AEHIJ"),
        ("1D", "3BEFIJ"),
        ("1H", "2J"),
        ("2K", "2L"),
        ("1B", "3EFGIJ"),
        ("2D", "2G"),
        ("1J", "2H"),
        ("1K", "3DEIJL"),
    ]
    # Distinct dates for each knockout round ensure correct sort order
    knockout_dates = {
        "Round of 32": pd.Timestamp("2026-06-28"),
        "Round of 16": pd.Timestamp("2026-07-05"),
        "Quarter Finals": pd.Timestamp("2026-07-09"),
        "Semi Finals": pd.Timestamp("2026-07-14"),
        "Finals": pd.Timestamp("2026-07-18"),
    }
    for home_slot, away_slot in r32_slots:
        rows.append(
            {
                "match_number": match_num,
                "round_number": "Round of 32",
                "group": None,
                "home_team": home_slot,
                "away_team": away_slot,
                "date": knockout_dates["Round of 32"],
            }
        )
        match_num += 1

    # Later rounds — "To be announced"; simulator pairs previous winners
    for rnd, count in [
        ("Round of 16", 8),
        ("Quarter Finals", 4),
        ("Semi Finals", 2),
        ("Finals", 2),
    ]:
        for _ in range(count):
            rows.append(
                {
                    "match_number": match_num,
                    "round_number": rnd,
                    "group": None,
                    "home_team": "To be announced",
                    "away_team": "To be announced",
                    "date": knockout_dates[rnd],
                }
            )
            match_num += 1

    return pd.DataFrame(rows)


def _make_strengths(boost_groups: str = "EFGHIJKL") -> pd.DataFrame:
    """Build team strengths.

    Teams in boost_groups get attack=1.6 so their 3rd-place finishers
    accumulate more points than A–D 3rd-placers, producing the EFGHIJKL
    key that is present in ROUND_OF_32_THIRD_PLACE_ASSIGNMENT_MAP.
    This ensures all 8 third-place R32 slots resolve correctly.
    """
    rows = {}
    for g in GROUPS:
        atk = 1.6 if g in boost_groups else 0.8
        dfc = 0.8 if g in boost_groups else 1.6
        for n in range(1, 5):
            rows[f"{g}{n}"] = {"attack": atk, "defense": dfc}
    return pd.DataFrame(rows).T.astype(float)


# ---------------------------------------------------------------------------
# Module-level fixture — run once, shared by all invariant tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tournament_result():
    np.random.seed(42)
    schedule = _make_wc_fixture()
    strengths = _make_strengths()
    return simulate_full_tournament(
        schedule, strengths, n_simulations=300, return_group_tables=True
    )


# ---------------------------------------------------------------------------
# Part 1 — Slot resolution (deterministic)
# ---------------------------------------------------------------------------

class TestSlotResolution:

    def test_first_place_slot_resolves_to_group_winner(self):
        standings = _make_full_standings()
        assert _resolve_group_placement("1A", standings, 1) == "A1"

    def test_second_place_slot_resolves_to_runner_up(self):
        standings = _make_full_standings()
        assert _resolve_group_placement("2B", standings, 2) == "B2"

    def test_first_place_slot_different_group(self):
        standings = _make_full_standings()
        assert _resolve_group_placement("1L", standings, 1) == "L1"

    def test_invalid_slot_returns_none(self):
        standings = _make_full_standings()
        assert _resolve_group_placement("XZ", standings, 1) is None
        assert _resolve_group_placement("3A", standings, 3) is None

    def test_slot_resolves_when_keys_have_no_group_prefix(self):
        # standings_by_group keyed as bare letters ("A") rather than "Group A"
        bare_standings = {g: _make_standings([f"{g}1", f"{g}2", f"{g}3", f"{g}4"]) for g in GROUPS}
        assert _resolve_group_placement("1A", bare_standings, 1) == "A1"
        assert _resolve_group_placement("2C", bare_standings, 2) == "C2"

    def test_third_place_assignment_map_returns_eight_entries(self):
        # Groups E–L have clearly better 3rd-place teams → key "EFGHIJKL" is in the map
        standings = _make_full_standings({g: 9 for g in "EFGHIJKL"} | {g: 0 for g in "ABCD"})
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        assert len(amap) == 8

    def test_third_place_assignment_map_keys_are_r32_winner_groups(self):
        standings = _make_full_standings({g: 9 for g in "EFGHIJKL"} | {g: 0 for g in "ABCD"})
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        assert set(amap.keys()) == set(_R32_WINNER_GROUP_ORDER)

    def test_third_place_assignment_map_values_are_valid_group_letters(self):
        standings = _make_full_standings({g: 9 for g in "EFGHIJKL"} | {g: 0 for g in "ABCD"})
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        for v in amap.values():
            assert v in set(GROUPS), f"Unexpected group letter '{v}' in assignment map"

    def test_best_eight_third_place_groups_selected(self):
        # Groups E–L have 3rd-place teams with 9 pts; A–D have 0 pts.
        # The assignment map should only reference groups E–L.
        third_pts = {g: 9 for g in "EFGHIJKL"}
        third_pts.update({g: 0 for g in "ABCD"})
        standings = _make_full_standings(third_pts=third_pts)
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        for v in amap.values():
            assert v in set("EFGHIJKL"), (
                f"Expected only groups E–L but got '{v}'"
            )

    def test_third_place_team_resolves_via_assignment_map(self):
        standings = _make_full_standings({g: 9 for g in "EFGHIJKL"} | {g: 0 for g in "ABCD"})
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        # Group A's winner (slot "1A") faces a 3rd-place team from whichever
        # group the map assigns to "A".
        third_group_letter = amap["A"]
        expected_team = f"{third_group_letter}3"
        resolved = _resolve_round_of_32_third_place("1A", standings, amap)
        assert resolved == expected_team

    def test_resolve_third_place_for_each_r32_winner_group(self):
        standings = _make_full_standings({g: 9 for g in "EFGHIJKL"} | {g: 0 for g in "ABCD"})
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert amap is not None
        for winner_group in _R32_WINNER_GROUP_ORDER:
            third_group = amap[winner_group]
            expected = f"{third_group}3"
            resolved = _resolve_round_of_32_third_place(f"1{winner_group}", standings, amap)
            assert resolved == expected, (
                f"1{winner_group}: expected '{expected}', got '{resolved}'"
            )

    def test_invalid_winner_slot_returns_none(self):
        standings = _make_full_standings()
        amap = _build_round_of_32_third_place_assignment_map(standings)
        assert _resolve_round_of_32_third_place("2A", standings, amap) is None
        assert _resolve_round_of_32_third_place("3ABC", standings, amap) is None


# ---------------------------------------------------------------------------
# Part 2 — Mathematical invariants
# ---------------------------------------------------------------------------

class TestTournamentInvariants:

    def test_winner_probabilities_sum_to_one(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        total = df["prob_Winner"].sum()
        assert abs(total - 1.0) < 0.02

    def test_finals_team_count_equals_two(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        assert abs(df["prob_Finals"].sum() - 2.0) < 0.2

    def test_semi_finals_team_count_equals_four(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        assert abs(df["prob_Semi_Finals"].sum() - 4.0) < 0.5

    def test_quarter_finals_team_count_equals_eight(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        assert abs(df["prob_Quarter_Finals"].sum() - 8.0) < 0.5

    def test_round_of_16_team_count_equals_sixteen(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        assert abs(df["prob_Round_of_16"].sum() - 16.0) < 0.5

    def test_round_of_32_team_count_equals_thirty_two(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        assert abs(df["prob_Round_of_32"].sum() - 32.0) < 1.0

    def test_all_probabilities_in_unit_interval(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        prob_cols = [c for c in df.columns if c.startswith("prob_")]
        assert ((df[prob_cols] >= -1e-9) & (df[prob_cols] <= 1.0 + 1e-9)).all().all()

    def test_monotonicity_later_round_never_exceeds_earlier_round(self, tournament_result):
        """prob of reaching a later stage cannot exceed prob of reaching an earlier stage."""
        df = tournament_result["tournament_simulation"]
        ordered = [
            "prob_Round_of_32",
            "prob_Round_of_16",
            "prob_Quarter_Finals",
            "prob_Semi_Finals",
            "prob_Finals",
            "prob_Winner",
        ]
        violations = []
        for _, row in df.iterrows():
            for early, late in zip(ordered, ordered[1:]):
                if row[late] > row[early] + 1e-9:
                    violations.append(
                        f"{row['team']}: {early}={row[early]:.4f} < {late}={row[late]:.4f}"
                    )
        assert not violations, "Monotonicity violated:\n" + "\n".join(violations)

    def test_group_table_position_probs_sum_to_one(self, tournament_result):
        group_tables = tournament_result["group_tables"]
        prob_cols = [c for c in group_tables.columns if c.startswith("prob_")]
        for _, row in group_tables.iterrows():
            total = float(sum(row[c] for c in prob_cols))
            assert abs(total - 1.0) < 1e-6, (
                f"{row['team']} in {row['group']}: position probs sum to {total:.6f}"
            )

    def test_group_tables_cover_all_groups(self, tournament_result):
        group_tables = tournament_result["group_tables"]
        found = set(group_tables["group"].unique())
        expected = {f"Group {g}" for g in GROUPS}
        assert found == expected

    def test_every_team_appears_in_tournament_results(self, tournament_result):
        df = tournament_result["tournament_simulation"]
        all_teams = {f"{g}{n}" for g in GROUPS for n in range(1, 5)}
        found = set(df["team"].tolist())
        assert all_teams == found


# ---------------------------------------------------------------------------
# Part 3 — Dominant-team oracle
# ---------------------------------------------------------------------------

class TestDominantTeamOracle:

    def test_dominant_team_wins_tournament_almost_always(self):
        """Elo 5000 vs 1500 → win prob should be >> 1/48 baseline (~2%).

        The threshold is 0.75 rather than close-to-1 because predict_poisson_scores
        caps the Elo advantage via tanh (max ~0.4 goal margin), so the dominant
        team only wins ~48% of individual group-stage matches.  In 1000 runs the
        observed value is ~0.82, comfortably above the 0.75 guard.
        """
        np.random.seed(0)
        schedule = _make_wc_fixture()
        strengths = _make_strengths()

        all_teams = [f"{g}{n}" for g in GROUPS for n in range(1, 5)]
        dominant = "A1"
        elo = {t: 5000.0 if t == dominant else 1500.0 for t in all_teams}

        df = simulate_full_tournament(schedule, strengths, n_simulations=1000, elo_ratings=elo)
        row = df[df["team"] == dominant].iloc[0]
        assert row["prob_Winner"] > 0.75, (
            f"Expected prob_Winner > 0.75, got {row['prob_Winner']:.3f}"
        )

    def test_dominant_team_reaches_finals_almost_always(self):
        """Dominant team should reach the final in > 70% of simulations."""
        np.random.seed(1)
        schedule = _make_wc_fixture()
        strengths = _make_strengths()

        all_teams = [f"{g}{n}" for g in GROUPS for n in range(1, 5)]
        dominant = "G2"
        elo = {t: 5000.0 if t == dominant else 1500.0 for t in all_teams}

        df = simulate_full_tournament(schedule, strengths, n_simulations=1000, elo_ratings=elo)
        row = df[df["team"] == dominant].iloc[0]
        assert row["prob_Finals"] > 0.70, (
            f"Expected prob_Finals > 0.70, got {row['prob_Finals']:.3f}"
        )

    def test_dominant_team_monotonicity_holds_at_extreme_elo(self):
        """Invariants must still hold when one team has extreme Elo."""
        np.random.seed(2)
        schedule = _make_wc_fixture()
        strengths = _make_strengths()

        all_teams = [f"{g}{n}" for g in GROUPS for n in range(1, 5)]
        dominant = "F3"
        elo = {t: 5000.0 if t == dominant else 1500.0 for t in all_teams}

        df = simulate_full_tournament(schedule, strengths, n_simulations=500, elo_ratings=elo)

        ordered = [
            "prob_Round_of_32",
            "prob_Round_of_16",
            "prob_Quarter_Finals",
            "prob_Semi_Finals",
            "prob_Finals",
            "prob_Winner",
        ]
        dom_row = df[df["team"] == dominant].iloc[0]
        for early, late in zip(ordered, ordered[1:]):
            assert dom_row[late] <= dom_row[early] + 1e-9, (
                f"Dominant team: {early}={dom_row[early]:.4f} < {late}={dom_row[late]:.4f}"
            )

    def test_weak_teams_have_near_zero_win_probability(self):
        """With one dominant team, all others should have very low win probability."""
        np.random.seed(3)
        schedule = _make_wc_fixture()
        strengths = _make_strengths()

        all_teams = [f"{g}{n}" for g in GROUPS for n in range(1, 5)]
        dominant = "C1"
        elo = {t: 5000.0 if t == dominant else 1500.0 for t in all_teams}

        df = simulate_full_tournament(schedule, strengths, n_simulations=500, elo_ratings=elo)
        others = df[df["team"] != dominant]
        assert (others["prob_Winner"] < 0.10).all(), (
            "Some non-dominant team has win prob >= 0.10:\n"
            + others[others["prob_Winner"] >= 0.10][["team", "prob_Winner"]].to_string()
        )
