"""Tournament simulation utilities for the World Cup Predictor."""
from __future__ import annotations

from typing import Dict
from collections import defaultdict
import math

import numpy as np
import pandas as pd
import warnings

from .stat_models import predict_poisson_scores, simulate_match
import re


def calculate_match_probabilities(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    max_goals: int = 6,
) -> Dict[str, float]:
    """Compute win/draw probabilities for a single match using Poisson scoring."""
    expected_home, expected_away = predict_poisson_scores(home_team, away_team, strengths)
    home_probs = np.array([np.exp(-expected_home) * expected_home ** k / math.factorial(k) for k in range(max_goals + 1)])
    away_probs = np.array([np.exp(-expected_away) * expected_away ** k / math.factorial(k) for k in range(max_goals + 1)])

    matrix = np.outer(home_probs, away_probs)
    home_win = float(np.tril(matrix, -1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, 1).sum())

    total = home_win + draw + away_win
    if total <= 0:
        return {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}

    return {"home_win": home_win / total, "draw": draw / total, "away_win": away_win / total}


def aggregate_group_standings(results: pd.DataFrame) -> pd.DataFrame:
    """Compute group standings from played results."""
    results = results.copy()
    results["points_home"] = results.apply(
        lambda row: 3 if row["home_score"] > row["away_score"] else 1 if row["home_score"] == row["away_score"] else 0,
        axis=1,
    )
    results["points_away"] = results.apply(
        lambda row: 3 if row["away_score"] > row["home_score"] else 1 if row["away_score"] == row["home_score"] else 0,
        axis=1,
    )

    home_stats = results.groupby("home_team").agg(
        points=("points_home", "sum"),
        played=("home_score", "count"),
        goals_for=("home_score", "sum"),
        goals_against=("away_score", "sum"),
    )
    away_stats = results.groupby("away_team").agg(
        points=("points_away", "sum"),
        played=("away_score", "count"),
        goals_for=("away_score", "sum"),
        goals_against=("home_score", "sum"),
    )

    standings = home_stats.add(away_stats, fill_value=0)
    standings["goal_difference"] = standings["goals_for"] - standings["goals_against"]
    standings = standings.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])
    return standings.astype({"points": int, "played": int, "goals_for": int, "goals_against": int, "goal_difference": int})


def simulate_group_stage(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """Simulate a group stage and estimate advancement probabilities."""
    if "group" not in schedule.columns:
        raise KeyError("Schedule must include a 'group' column")

    schedule = schedule.copy()
    schedule = schedule.reset_index(drop=True)
    teams = sorted(set(schedule["home_team"]).union(schedule["away_team"]))
    advance_counts = {team: 0 for team in teams}

    for _ in range(n_simulations):
        all_results = []
        for _, match in schedule.iterrows():
            home_team = match["home_team"]
            away_team = match["away_team"]
            if home_team not in strengths.index or away_team not in strengths.index:
                warnings.warn(
                    f"Skipping match with missing strengths: {home_team} vs {away_team}",
                    UserWarning,
                )
                continue

            sim = simulate_match(home_team, away_team, strengths, n_simulations=1)
            home_goals = int(sim["home_goals"].iloc[0])
            away_goals = int(sim["away_goals"].iloc[0])
            all_results.append(
                {
                    "group": match["group"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_goals,
                    "away_score": away_goals,
                }
            )

        if not all_results:
            warnings.warn("No valid matches were simulated for this group stage.", UserWarning)
            continue

        results_df = pd.DataFrame(all_results)
        standings = aggregate_group_standings(results_df)

        for team in standings.index[:2]:
            advance_counts[team] += 1

    probabilities = pd.DataFrame(
        {"team": list(advance_counts.keys()), "advance_probability": [count / n_simulations for count in advance_counts.values()]}
    )
    return probabilities.sort_values("advance_probability", ascending=False).reset_index(drop=True)


def simulate_knockout_match(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """Simulate a knockout match and return counts for each possible winner."""
    sim = simulate_match(home_team, away_team, strengths, n_simulations=n_simulations)
    outcomes = sim.apply(
        lambda row: "home" if row["home_goals"] > row["away_goals"] else "away" if row["away_goals"] > row["home_goals"] else "draw",
        axis=1,
    )
    return outcomes.value_counts(normalize=True).rename_axis("result").reset_index(name="probability")


def simulate_group_tables(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """Simulate group stage many times and return predicted group tables.

    Returns a DataFrame with one row per group/team containing:
    - probabilities of finishing in each position (prob_1, prob_2, ...)
    - `expected_rank`, `avg_points`, and `avg_goal_difference`.
    """
    if "group" not in schedule.columns:
        raise KeyError("Schedule must include a 'group' column")

    schedule = schedule.copy().reset_index(drop=True)

    # determine teams in each group
    groups = list(pd.unique(schedule["group"]))
    group_teams: Dict[str, list] = {}
    for g in groups:
        homes = set(schedule.loc[schedule["group"] == g, "home_team"]) 
        aways = set(schedule.loc[schedule["group"] == g, "away_team"])
        group_teams[g] = sorted(homes.union(aways))

    # initialize counters
    rank_counts = {g: {t: [0] * len(group_teams[g]) for t in group_teams[g]} for g in group_teams}
    pts_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}
    gd_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}

    for _ in range(n_simulations):
        all_results = []
        for _, match in schedule.iterrows():
            home_team = match["home_team"]
            away_team = match["away_team"]
            if home_team not in strengths.index or away_team not in strengths.index:
                warnings.warn(
                    f"Skipping match with missing strengths: {home_team} vs {away_team}",
                    UserWarning,
                )
                continue

            sim = simulate_match(home_team, away_team, strengths, n_simulations=1)
            home_goals = int(sim["home_goals"].iloc[0])
            away_goals = int(sim["away_goals"].iloc[0])
            all_results.append(
                {
                    "group": match["group"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_goals,
                    "away_score": away_goals,
                }
            )

        if not all_results:
            warnings.warn("No valid matches were simulated for this group stage.", UserWarning)
            continue

        results_df = pd.DataFrame(all_results)

        for g, teams in group_teams.items():
            gr = results_df[results_df["group"] == g]
            if gr.empty:
                # nothing simulated for this group in this iteration
                continue

            standings = aggregate_group_standings(gr)
            # ensure all teams are present without forcing alphabetical order
            for team in teams:
                if team not in standings.index:
                    standings.loc[team] = {
                        "points": 0,
                        "played": 0,
                        "goals_for": 0,
                        "goals_against": 0,
                        "goal_difference": 0,
                    }
            standings = standings.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])

            for pos, team in enumerate(standings.index.tolist(), start=1):
                rank_counts[g][team][pos - 1] += 1
                pts_sums[g][team] += int(standings.loc[team, "points"])
                gd_sums[g][team] += int(standings.loc[team, "goal_difference"])

    # assemble final DataFrame
    rows = []
    for g, teams in group_teams.items():
        n_teams = len(teams)
        for team in teams:
            counts = rank_counts[g][team]
            probs = [c / n_simulations for c in counts]
            expected_rank = sum((i + 1) * p for i, p in enumerate(probs))
            avg_points = pts_sums[g][team] / n_simulations
            avg_gd = gd_sums[g][team] / n_simulations

            row = {
                "group": g,
                "team": team,
                "expected_rank": expected_rank,
                "avg_points": avg_points,
                "avg_goal_difference": avg_gd,
            }

            for i, p in enumerate(probs, start=1):
                row[f"prob_{i}"] = p

            rows.append(row)

    out = pd.DataFrame(rows)
    out = out.sort_values(["group", "expected_rank"]) .reset_index(drop=True)
    return out


def simulate_full_tournament(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """Simulate full tournament including knockout rounds.

    Returns a DataFrame with per-team probabilities for reaching each knockout
    stage and winning the tournament.
    """
    # prepare schedule
    if "group" not in schedule.columns and "round_number" not in schedule.columns:
        raise KeyError("Schedule must include 'group' or 'round_number' columns")

    sched = schedule.copy().reset_index(drop=True)
    # sort by date if available else by index
    if "date" in sched.columns:
        sched = sched.sort_values("date")

    # identify knockout round names in order of appearance
    knock_mask = sched["round_number"].astype(str).str.contains("Round|Quarter|Semi|Final", na=False)
    knockout = sched[knock_mask].copy()
    if knockout.empty:
        raise ValueError("No knockout matches found in schedule")

    round_order = list(dict.fromkeys(knockout["round_number"]))

    # counters for stages
    stages = [
        "Round of 32",
        "Round of 16",
        "Quarter Finals",
        "Semi Finals",
        "Finals",
    ]

    # determine real teams (exclude placeholders like '1A', '3ABC', 'To be announced')
    placeholder_re = re.compile(r"^(?:To be announced|\d+[A-Z]+|3[A-Z]+)$", re.IGNORECASE)
    raw_home = [x for x in sched.get("home_team").dropna().tolist()]
    raw_away = [x for x in sched.get("away_team").dropna().tolist()]
    candidate = set(raw_home + raw_away)
    real_teams = set()
    for t in candidate:
        if not placeholder_re.match(str(t).strip()):
            real_teams.add(t)

    # also include any teams appearing in group match listings (they are real)
    group_mask = sched["group"].notna()
    for _, row in sched[group_mask].iterrows():
        real_teams.add(row["home_team"]) if pd.notna(row["home_team"]) else None
        real_teams.add(row["away_team"]) if pd.notna(row["away_team"]) else None

    all_teams = sorted(real_teams)
    stage_counts = {team: {s: 0 for s in stages + ["Winner"]} for team in all_teams}

    # ensure strengths contains all teams (fill missing with mean strengths)
    strengths = strengths.copy()
    missing = [t for t in all_teams if t not in strengths.index]
    if missing:
        # use neutral strengths to avoid extreme expected goals
        default_attack = 1.0
        default_defense = 1.0
        for t in missing:
            strengths.loc[t] = {"attack": default_attack, "defense": default_defense}

    # helper to resolve placeholders like '1A', '2B', '3ABC'
    def normalize_group_key(letter: str, groups):
        # try exact letter, then 'Group X'
        if letter in groups:
            return letter
        g = f"Group {letter}"
        if g in groups:
            return g
        # fallback to first group that endswith letter
        for gr in groups:
            if str(gr).strip().endswith(letter):
                return gr
        return None

    for _ in range(n_simulations):
        # simulate group matches to produce standings
        group_sched = sched[sched["round_number"].astype(str).str.match(r"^\d+$", na=False) | sched["group"].notna()]
        groups = list(pd.unique(group_sched["group"]))
        group_teams = {g: sorted(set(group_sched.loc[group_sched["group"] == g, "home_team"]).union(group_sched.loc[group_sched["group"] == g, "away_team"])) for g in groups}

        # simulate matches
        all_results = []
        for _, match in group_sched.iterrows():
            h = match["home_team"]
            a = match["away_team"]
            if h not in strengths.index or a not in strengths.index:
                continue
            sim = simulate_match(h, a, strengths, n_simulations=1)
            all_results.append({
                "group": match.get("group"),
                "home_team": h,
                "away_team": a,
                "home_score": int(sim["home_goals"].iloc[0]),
                "away_score": int(sim["away_goals"].iloc[0]),
            })

        results_df = pd.DataFrame(all_results)
        standings_by_group = {}
        for g in groups:
            gr = results_df[results_df["group"] == g]
            if gr.empty:
                continue
            st = aggregate_group_standings(gr)
            # ensure all teams present
            for t in group_teams[g]:
                if t not in st.index:
                    st.loc[t] = {"points": 0, "played": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0}
            st = st.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])
            standings_by_group[g] = st

        # initial knockout: process Round of 32 by resolving placeholders
        prev_winners = []
        for rnd in round_order:
            round_matches = knockout[knockout["round_number"] == rnd]
            # Round of 32: resolve slots directly from placeholders
            if str(rnd).startswith("Round of 32") or "32" in str(rnd):
                # for third-place placeholders, we'll maintain a used set
                used_third = set()
                for _, match in round_matches.iterrows():
                    h_slot = str(match.get("home_team", "")).strip()
                    a_slot = str(match.get("away_team", "")).strip()

                    def resolve(slot):
                        if not slot or slot.lower().startswith("to be"):
                            return None
                        # direct team name
                        if slot in all_teams:
                            return slot
                        m = re.match(r"([12])(\w)", slot)
                        if m:
                            pos = int(m.group(1))
                            letter = m.group(2)
                            gkey = normalize_group_key(letter, standings_by_group.keys())
                            if gkey and gkey in standings_by_group and len(standings_by_group[gkey].index) >= pos:
                                return standings_by_group[gkey].index[pos - 1]
                        m3 = re.match(r"3([A-Z]+)", slot)
                        if m3:
                            letters = list(m3.group(1))
                            # collect third-placed from listed groups
                            third_candidates = []
                            for L in letters:
                                gk = normalize_group_key(L, standings_by_group.keys())
                                if gk and gk in standings_by_group and len(standings_by_group[gk].index) >= 3:
                                    team3 = standings_by_group[gk].index[2]
                                    third_candidates.append((team3, standings_by_group[gk].loc[team3, ["points", "goal_difference", "goals_for"]].tolist()))
                            # sort candidates by points, gd, gf
                            third_candidates.sort(key=lambda x: ( -x[1][0], -x[1][1], -x[1][2]))
                            for team, _ in third_candidates:
                                if team not in used_third:
                                    used_third.add(team)
                                    return team
                        return None

                    home = resolve(h_slot)
                    away = resolve(a_slot)

                    if home is None or away is None:
                        # cannot resolve; skip match
                        continue

                    # simulate knockout match: if draw, decide via probabilities
                    sim = simulate_match(home, away, strengths, n_simulations=1)
                    hg = int(sim["home_goals"].iloc[0])
                    ag = int(sim["away_goals"].iloc[0])
                    if hg == ag:
                        probs = calculate_match_probabilities(home, away, strengths)
                        # normalize without draw
                        hw = probs["home_win"]
                        aw = probs["away_win"]
                        winner = home if np.random.rand() < hw / (hw + aw + 1e-12) else away
                    else:
                        winner = home if hg > ag else away

                    prev_winners.append(winner)
                    stage_counts[winner]["Round of 32"] += 1

            else:
                # for later rounds, pair previous winners sequentially
                next_winners = []
                for i in range(0, len(prev_winners), 2):
                    try:
                        home = prev_winners[i]
                        away = prev_winners[i + 1]
                    except IndexError:
                        continue
                    if home is None or away is None:
                        continue
                    sim = simulate_match(home, away, strengths, n_simulations=1)
                    hg = int(sim["home_goals"].iloc[0])
                    ag = int(sim["away_goals"].iloc[0])
                    if hg == ag:
                        probs = calculate_match_probabilities(home, away, strengths)
                        hw = probs["home_win"]
                        aw = probs["away_win"]
                        winner = home if np.random.rand() < hw / (hw + aw + 1e-12) else away
                    else:
                        winner = home if hg > ag else away
                    next_winners.append(winner)
                    # mark stage reached
                    if "16" in str(rnd):
                        stage_counts[winner]["Round of 16"] += 1
                    elif "Quarter" in str(rnd):
                        stage_counts[winner]["Quarter Finals"] += 1
                    elif "Semi" in str(rnd):
                        stage_counts[winner]["Semi Finals"] += 1
                    elif "Final" in str(rnd):
                        stage_counts[winner]["Finals"] += 1

                prev_winners = next_winners

        # final winner
        if prev_winners:
            champ = prev_winners[0]
            if champ:
                stage_counts[champ]["Winner"] += 1

    # assemble probabilities
    rows = []
    for team, counts in stage_counts.items():
        row = {"team": team}
        for s in stages:
            row[f"prob_{s.replace(' ', '_')}"] = counts[s] / n_simulations
        row["prob_Winner"] = counts["Winner"] / n_simulations
        rows.append(row)

    return pd.DataFrame(rows).sort_values("prob_Winner", ascending=False).reset_index(drop=True)
