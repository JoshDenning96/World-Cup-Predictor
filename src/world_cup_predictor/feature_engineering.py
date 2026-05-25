"""Feature engineering helpers for World Cup match prediction."""
from pathlib import Path
from typing import Dict

import pandas as pd


ALIASES = {
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "Czechia": "Czech Republic",
    "Côte d'Ivoire": "Cote d'Ivoire",
    "IR Iran": "Iran",
    "Korea Republic": "South Korea",
    "Türkiye": "Turkey",
    "USA": "United States",
    "United States of America": "United States",
    "Republic of Ireland": "Ireland",
    "Korea DPR": "North Korea",
    "South Korea": "South Korea",
    "North Korea": "North Korea",
}


def normalize_team_name(name: str) -> str:
    if pd.isna(name):
        return name
    value = str(name).strip()
    value = " ".join(value.split())
    return ALIASES.get(value, value)


def parse_date_column(df: pd.DataFrame, column: str, fmt: str | None = None) -> pd.DataFrame:
    df = df.copy()
    if column not in df.columns:
        return df
    df[column] = pd.to_datetime(df[column], format=fmt, errors="coerce")
    return df


def standardize_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    ranking = ranking.copy()
    ranking["country_full"] = ranking["country_full"].apply(normalize_team_name)
    if "country_abrv" in ranking.columns:
        ranking["country_abrv"] = ranking["country_abrv"].apply(normalize_team_name)
    ranking = parse_date_column(ranking, "rank_date", fmt="%Y-%m-%d")
    return ranking


def standardize_results(results: pd.DataFrame) -> pd.DataFrame:
    results = results.copy()
    for col in ["home_team", "away_team", "country"]:
        if col in results.columns:
            results[col] = results[col].apply(normalize_team_name)
    results = parse_date_column(results, "date", fmt="%Y-%m-%d")
    return results


def standardize_schedule_utc(schedule: pd.DataFrame) -> pd.DataFrame:
    schedule = schedule.copy()
    rename_map = {
        "home team": "home_team",
        "away team": "away_team",
        "home_team": "home_team",
        "away_team": "away_team",
        "Home Team": "home_team",
        "Away Team": "away_team",
        "Group": "group",
        "group": "group",
        "Date": "date",
        "date_dt": "date",
        "date": "date",
        "Location": "stadium",
        "location": "stadium",
        "Stadium": "stadium",
        "Match Number": "match_number",
        "Round Number": "round_number",
    }
    # Rename columns but avoid creating duplicate target names (keep first occurrence)
    new_map = {}
    seen_targets = set()
    for col in schedule.columns:
        target = rename_map.get(col, col)
        if target in seen_targets:
            # skip this column to avoid duplicate column names
            continue
        new_map[col] = target
        seen_targets.add(target)

    schedule = schedule.rename(columns=new_map)

    for col in ["home_team", "away_team", "stadium", "group"]:
        if col in schedule.columns:
            schedule[col] = schedule[col].apply(normalize_team_name)

    if "date" in schedule.columns:
        schedule["date"] = pd.to_datetime(schedule["date"], errors="coerce")

    return schedule


def _merge_team_rankings(matches: pd.DataFrame, ranking: pd.DataFrame, team_col: str, suffix: str) -> pd.DataFrame:
    if team_col not in matches.columns:
        raise KeyError(f"Match column '{team_col}' not found")
    if "rank_date" not in ranking.columns:
        raise KeyError("Ranking dataframe must contain 'rank_date' after parsing")

    matches = matches.copy()
    ranking = ranking.copy()
    ranking = ranking.rename(columns={"country_full": "team"})

    temp = matches[[team_col, "date"]].rename(columns={team_col: "team"})
    temp = temp.reset_index()
    merged_frames = []

    for team, team_rows in temp.groupby("team", sort=False):
        team_rank = ranking[ranking["team"] == team].sort_values("rank_date")
        if team_rank.empty:
            merged_frames.append(team_rows.assign(**{
                f"{suffix}_rank": pd.NA,
                f"{suffix}_points": pd.NA,
                f"{suffix}_rank_date": pd.NaT,
            }))
            continue

        team_rows = team_rows.sort_values("date")
        merged_team = pd.merge_asof(
            team_rows,
            team_rank,
            left_on="date",
            right_on="rank_date",
            direction="backward",
        )
        merged_frames.append(merged_team)

    merged = pd.concat(merged_frames, ignore_index=True)
    merged = merged.set_index("index").sort_index()

    suffix_map = {
        "rank": f"{suffix}_rank",
        "total_points": f"{suffix}_points",
        "rank_date": f"{suffix}_rank_date",
    }
    merged = merged.rename(columns=suffix_map)
    result = matches.join(
        merged[[f"{suffix}_rank", f"{suffix}_points", f"{suffix}_rank_date"]]
    )
    return result


def attach_rankings_to_matches(results: pd.DataFrame, ranking: pd.DataFrame) -> pd.DataFrame:
    results = standardize_results(results)
    ranking = standardize_ranking(ranking)

    results = _merge_team_rankings(results, ranking, "home_team", "home")
    results = _merge_team_rankings(results, ranking, "away_team", "away")

    if "home_score" in results.columns and "away_score" in results.columns:
        results = results.copy()
        results["goal_difference"] = results["home_score"] - results["away_score"]
        results["home_result"] = results["goal_difference"].map(
            lambda diff: "win" if diff > 0 else "draw" if diff == 0 else "loss"
        )
    return results


def load_and_prepare_raw(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    from .data_loader import load_all

    raw_dir = Path(raw_dir)
    raw_data = load_all(raw_dir)
    raw_data["ranking"] = standardize_ranking(raw_data["ranking"])
    raw_data["results"] = standardize_results(raw_data["results"])
    raw_data["schedule_utc"] = standardize_schedule_utc(raw_data["schedule_utc"])
    return raw_data
