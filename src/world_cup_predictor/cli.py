"""Command-line interface for the World Cup Predictor."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

from .feature_engineering import load_and_prepare_raw
from .simulator import calculate_match_probabilities, simulate_group_tables, simulate_full_tournament
from .stat_models import (
    apply_confederation_rating_offset,
    fit_elo_ratings,
    fit_poisson_attack_defense,
)
import re
from typing import List

CONMEBOL_QUALIFIED_TEAMS = {
    "Argentina",
    "Brazil",
    "Colombia",
    "Uruguay",
    "Ecuador",
    "Paraguay",
}

# 2026 host nations receive a modest Elo boost to reflect home-crowd advantage.
# 50 points ≈ half the typical neutral-to-home shift, discounted because the
# tournament is spread across 16 venues in 3 countries rather than a single host.
HOST_NATIONS_2026 = {"United States", "Canada", "Mexico"}
HOST_ADVANTAGE_ELO = 50.0


def _elo_ratings_to_df(elo_ratings) -> pd.DataFrame:
    if isinstance(elo_ratings, pd.Series):
        df = elo_ratings.rename("elo_rating").reset_index()
        df = df.rename(columns={elo_ratings.index.name or "index": "team"})
    elif isinstance(elo_ratings, dict):
        df = pd.DataFrame(list(elo_ratings.items()), columns=["team", "elo_rating"])
    elif isinstance(elo_ratings, pd.DataFrame):
        if "team" in elo_ratings.columns and "elo_rating" in elo_ratings.columns:
            df = elo_ratings[["team", "elo_rating"]].copy()
        else:
            df = elo_ratings.reset_index().rename(columns={elo_ratings.index.name or "index": "team", 0: "elo_rating"})
    else:
        raise TypeError("elo_ratings must be a pandas Series, dict, or DataFrame")
    df["team"] = df["team"].astype(str)
    return df


def compare_elo_to_fifa_rankings(elo_ratings, fifa_ranking: pd.DataFrame) -> pd.DataFrame:
    elo_df = _elo_ratings_to_df(elo_ratings)
    ranking_df = fifa_ranking.copy()
    if "country_full" not in ranking_df.columns:
        raise KeyError("FIFA ranking data must contain a normalized team name column 'country_full'.")

    if "rank_date" in ranking_df.columns:
        ranking_df = ranking_df.sort_values("rank_date").drop_duplicates(subset=["country_full"], keep="last")

    merge_cols = ["country_full", "rank", "total_points"]
    if "confederation" in ranking_df.columns:
        merge_cols.append("confederation")

    comparison = pd.merge(
        elo_df,
        ranking_df[merge_cols].rename(columns={"country_full": "team"}),
        on="team",
        how="outer",
    )
    comparison["elo_rank"] = comparison["elo_rating"].rank(ascending=False, method="dense").astype("Int64")
    comparison["rank_diff"] = comparison["elo_rank"] - comparison["rank"]
    comparison = comparison.sort_values(["elo_rank", "rank"]).reset_index(drop=True)
    return comparison


def _get_qualified_teams(schedule: pd.DataFrame) -> List[str]:
    """Return list of qualified teams appearing in group-stage schedule (exclude placeholders)."""
    if schedule is None:
        return []
    sched = schedule.copy()
    teams = set()
    for col in ("home_team", "away_team", "teams"):
        if col in sched.columns:
            vals = sched[col].dropna().astype(str).tolist()
            teams.update(vals)

    # exclude placeholders like '1A', '3ABC', 'To be announced'
    placeholder_re = re.compile(r"^(?:To be announced|\d+[A-Z]+|3[A-Z]+)$", re.IGNORECASE)
    real = [t for t in teams if not placeholder_re.match(t.strip())]
    return sorted(real)


def _get_known_conmebol_qualified_teams(qualified_teams: List[str] | None) -> List[str]:
    if not qualified_teams:
        return []
    return [team for team in qualified_teams if team in CONMEBOL_QUALIFIED_TEAMS]


def run_pipeline(
    raw_dir: Path,
    n_simulations: int = 200,
    run_full_tournament: bool = False,
    conmebol_offset: float = 0.0,
    actual_results: dict | None = None,
    progress_callback=None,
) -> dict:
    raw_dir = Path(raw_dir)
    raw_data = load_and_prepare_raw(raw_dir)

    strengths = fit_poisson_attack_defense(raw_data["results"])
    raw_elo_ratings = fit_elo_ratings(raw_data["results"])

    qualified_teams = _get_qualified_teams(raw_data.get("schedule_utc"))
    conmebol_eligible_teams = _get_known_conmebol_qualified_teams(qualified_teams)
    elo_ratings = apply_confederation_rating_offset(
        raw_elo_ratings,
        raw_data["ranking"],
        confederation="CONMEBOL",
        offset=conmebol_offset,
        eligible_teams=conmebol_eligible_teams if conmebol_eligible_teams else None,
    )

    # Apply host-nation advantage (baked into Elo so it flows through both
    # group stage and knockout simulation automatically).
    host_teams_present = [t for t in HOST_NATIONS_2026 if t in elo_ratings]
    for team in host_teams_present:
        elo_ratings[team] = float(elo_ratings[team]) + HOST_ADVANTAGE_ELO

    first_match = raw_data["schedule_utc"].iloc[0]
    first_match_probabilities = calculate_match_probabilities(
        first_match["home_team"], first_match["away_team"], strengths
    )

    result = {
        "strengths": strengths,
        "raw_elo_ratings": raw_elo_ratings,
        "elo_ratings": elo_ratings,
        "qualified_teams": qualified_teams,
        "conmebol_teams_adjusted": conmebol_eligible_teams,
        "conmebol_offset": conmebol_offset,
        "first_match_probabilities": first_match_probabilities,
        "first_match": {
            "home_team": first_match["home_team"],
            "away_team": first_match["away_team"],
            "group": first_match.get("group"),
            "date": first_match.get("date"),
        },
    }

    if run_full_tournament:
        full_simulation = simulate_full_tournament(
            raw_data["schedule_utc"],
            strengths,
            n_simulations=n_simulations,
            elo_ratings=elo_ratings,
            return_group_tables=True,
            actual_results=actual_results,
            progress_callback=progress_callback,
        )
        result["tournament_simulation"] = full_simulation["tournament_simulation"]
        result["group_tables"] = full_simulation["group_tables"]
    else:
        result["group_tables"] = simulate_group_tables(
            raw_data["schedule_utc"],
            strengths,
            n_simulations=n_simulations,
            elo_ratings=elo_ratings,
            actual_results=actual_results,
        )

    # build elo vs fifa comparison but restrict to teams that have qualified (appear in group-stage schedule)
    full_comp = compare_elo_to_fifa_rankings(elo_ratings, raw_data["ranking"])
    sched_df = raw_data.get("schedule_utc") if raw_data.get("schedule_utc") is not None else raw_data.get("schedule")
    qualified = _get_qualified_teams(sched_df)
    if qualified:
        comp = full_comp[full_comp["team"].isin(qualified)].reset_index(drop=True)
    else:
        comp = full_comp
    result["elo_fifa_comparison"] = comp

    result["group_probabilities"] = (
        result["group_tables"].assign(advance_probability=result["group_tables"]["prob_1"] + result["group_tables"]["prob_2"])
        [["group", "team", "advance_probability"]]
        .sort_values("advance_probability", ascending=False)
        .reset_index(drop=True)
    )

    return result


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the World Cup Predictor pipeline.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Path to the raw CSV data directory.",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=200,
        help="Number of simulated group-stage tournament runs.",
    )
    parser.add_argument(
        "--full-tournament",
        action="store_true",
        help="Also run a full tournament simulation using ELO-based probabilities.",
    )
    parser.add_argument(
        "--compare-rankings",
        action="store_true",
        help="Print a comparison of ELO rankings to the latest FIFA rankings.",
    )
    parser.add_argument(
        "--conmebol-offset",
        type=float,
        default=0.0,
        help="Apply a uniform CONMEBOL Elo offset to qualified World Cup teams.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_pipeline(
        args.raw_dir,
        n_simulations=args.simulations,
        run_full_tournament=args.full_tournament,
        conmebol_offset=args.conmebol_offset,
    )

    print("\n=== World Cup Predictor Pipeline ===\n")
    print(f"Raw directory: {args.raw_dir}")
    print(f"Simulations: {args.simulations}\n")

    print("Top group advance probabilities:\n")
    print(result["group_probabilities"].head(12).to_string(index=False))

    print("\nFirst match prediction:\n")
    first_match = result["first_match"]
    print(
        f"{first_match['home_team']} vs {first_match['away_team']} "
        f"(group={first_match['group']}, date={first_match['date']})"
    )
    print(
        f"Home win: {result['first_match_probabilities']['home_win']:.3f}, "
        f"Draw: {result['first_match_probabilities']['draw']:.3f}, "
        f"Away win: {result['first_match_probabilities']['away_win']:.3f}"
    )

    print("\nElo rating snapshot for sample teams:\n")
    sample_teams = list(result["elo_ratings"])[:5]
    for team in sample_teams:
        print(f"  {team}: {result['elo_ratings'][team]:.1f}")

    if args.compare_rankings and "elo_fifa_comparison" in result:
        print("\nELO vs FIFA ranking comparison:\n")
        print(result["elo_fifa_comparison"].head(20).to_string(index=False))
        if args.conmebol_offset != 0.0 and result.get("conmebol_teams_adjusted"):
            print(f"\nApplied CONMEBOL offset: {args.conmebol_offset:+.1f} Elo points to qualified teams.")

    if args.full_tournament and "tournament_simulation" in result:
        print("\nTop tournament winners (sample):\n")
        print(result["tournament_simulation"].head(12).to_string(index=False))

        # Write a single master Excel workbook with key outputs (overwrites)
        out_dir = Path("data/processed")
        out_dir.mkdir(parents=True, exist_ok=True)
        master_path = out_dir / "master_simulation.xlsx"

        # Prepare ELO ratings as DataFrame
        elo_obj = result.get("elo_ratings")
        if hasattr(elo_obj, "to_frame"):
            df_elo = elo_obj.to_frame(name="elo").reset_index().rename(columns={elo_obj.index.name or 0: "team", "index": "team"})
            if "team" not in df_elo.columns:
                df_elo.columns = ["team", "elo"]
        elif isinstance(elo_obj, dict):
            df_elo = pd.DataFrame(list(elo_obj.items()), columns=["team", "elo"])
        else:
            try:
                df_elo = pd.DataFrame(elo_obj).reset_index().rename(columns={0: "elo", "index": "team"})
            except Exception:
                df_elo = pd.DataFrame({"team": [], "elo": []})

        # Predicted group tables
        df_groups = result.get("group_tables")
        if df_groups is None:
            df_groups = pd.DataFrame()

        # Tournament simulation
        df_tourney = result.get("tournament_simulation")
        if df_tourney is None:
            df_tourney = pd.DataFrame()

        with pd.ExcelWriter(master_path, engine="openpyxl", mode="w") as writer:
            df_elo.to_excel(writer, sheet_name="elo_ratings", index=False)
            df_groups.to_excel(writer, sheet_name="predicted_group_tables", index=False)
            df_tourney.to_excel(writer, sheet_name="tournament_simulation", index=False)
            if "elo_fifa_comparison" in result:
                result["elo_fifa_comparison"].to_excel(writer, sheet_name="elo_fifa_comparison", index=False)

        print(f"\nMaster simulation workbook written to: {master_path}")


if __name__ == "__main__":
    main()
