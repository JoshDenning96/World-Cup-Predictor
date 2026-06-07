import pandas as pd

from world_cup_predictor.feature_engineering import (
    attach_rankings_to_matches,
    normalize_team_name,
    standardize_fixtures_schedule,
    standardize_ranking,
    standardize_schedule_utc,
)


def test_standardize_schedule_utc_renames_columns_and_parses_date():
    df = pd.DataFrame(
        {
            "date_dt": ["2026-11-21"],
            "home team": ["Germany"],
            "away team": ["Japan"],
            "stadium": ["Stadium A"],
            "group": ["A"],
        }
    )

    cleaned = standardize_schedule_utc(df)

    assert "home_team" in cleaned.columns
    assert "away_team" in cleaned.columns
    assert pd.api.types.is_datetime64_any_dtype(cleaned["date"])
    assert cleaned.loc[0, "home_team"] == "Germany"
    assert cleaned.loc[0, "away_team"] == "Japan"


def test_attach_rankings_to_matches_adds_home_and_away_rank_columns():
    ranking = pd.DataFrame(
        {
            "country_full": ["Spain", "Japan"],
            "rank": [1, 2],
            "total_points": [2000, 1800],
            "rank_date": ["2024-06-20", "2024-06-20"],
        }
    )
    results = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "home_score": [2, 1],
            "away_score": [1, 2],
        }
    )

    prepared = attach_rankings_to_matches(results, ranking)

    assert prepared.loc[0, "home_rank"] == 1
    assert prepared.loc[0, "away_rank"] == 2
    assert prepared.loc[1, "home_rank"] == 2
    assert prepared.loc[1, "away_rank"] == 1
    assert prepared.loc[0, "goal_difference"] == 1
    assert prepared.loc[1, "home_result"] == "loss"


def test_standardize_fixtures_schedule_replaces_candidate_pools_and_splits_teams():
    df = pd.DataFrame(
        {
            "date_dt": ["2026-11-21", "2026-11-22"],
            "teams": [
                "Albania/Poland/Sweden/Ukraine v Tunisia",
                "Group E winners v Group A/B/C/D/F third place",
            ],
            "stadium": ["Stadium A", "Stadium B"],
            "group": ["X", "Y"],
        }
    )
    replacements = {
        "Albania/Poland/Sweden/Ukraine": "Sweden",
    }

    cleaned = standardize_fixtures_schedule(df, qualifier_replacements=replacements)

    assert cleaned.loc[0, "home_team"] == "Sweden"
    assert cleaned.loc[0, "away_team"] == "Tunisia"
    assert cleaned.loc[1, "home_team"] == "1E"
    assert cleaned.loc[1, "away_team"] == "3ABCDF"


def test_normalize_team_name_maps_ivory_coast_to_cote_divoire():
    assert normalize_team_name("Ivory Coast") == "Cote d'Ivoire"
    assert normalize_team_name("Côte d'Ivoire") == "Cote d'Ivoire"


def test_standardize_ranking_accepts_fifa_csv_header_variants():
    df = pd.DataFrame(
        {
            "Rank": ["1\n2", "2\n1"],
            "Team": ["France", "Spain"],
            "Last Result": ["France\nCôte d'Ivoire\nFT\n1\n2", "Spain\nIraq\nFT\n1\n1"],
            "Points": ["1877.32*", "1876.40*"],
        }
    )
    cleaned = standardize_ranking(df)

    assert cleaned.loc[0, "country_full"] == "France"
    assert cleaned.loc[1, "country_full"] == "Spain"
    assert cleaned.loc[0, "rank"] == 1
    assert cleaned.loc[1, "rank"] == 2
    assert cleaned.loc[0, "total_points"] == 1877.32
    assert cleaned.loc[1, "total_points"] == 1876.40
