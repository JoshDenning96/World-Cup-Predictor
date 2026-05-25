import pandas as pd

from world_cup_predictor.feature_engineering import (
    attach_rankings_to_matches,
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
