from pathlib import Path

import pandas as pd

from world_cup_predictor.cli import run_pipeline


def test_run_pipeline_with_minimal_data(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    pd.DataFrame(
        {
            "rank": [1, 2],
            "country_full": ["Spain", "Japan"],
            "country_abrv": ["ESP", "JPN"],
            "total_points": [2000, 1800],
            "previous_points": [1950, 1750],
            "rank_change": [0, 0],
            "confederation": ["UEFA", "AFC"],
            "rank_date": ["2024-06-20", "2024-06-20"],
        }
    ).to_csv(raw_dir / "fifa_ranking-2024-06-20.csv", index=False)

    pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "home_score": [2, 1],
            "away_score": [1, 2],
            "tournament": ["Friendly", "Friendly"],
            "city": ["City A", "City B"],
            "country": ["Country A", "Country B"],
            "neutral": [False, False],
        }
    ).to_csv(raw_dir / "results.csv", index=False)

    pd.DataFrame(
        {
            "group": ["A", "A"],
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "stadium": ["Stadium A", "Stadium B"],
            "date": ["2026-11-21", "2026-11-22"],
        }
    ).to_csv(raw_dir / "FIFA2026_schedule.csv", index=False)

    pd.DataFrame(
        {
            "date": ["Long Date 1", "Long Date 2"],
            "date_dt": ["2026-11-21", "2026-11-22"],
            "group": ["A", "A"],
            "home team": ["Spain", "Japan"],
            "away team": ["Japan", "Spain"],
            "stadium": ["Stadium A", "Stadium B"],
        }
    ).to_csv(raw_dir / "fifa-world-cup-2026-UTC.csv", index=False)

    result = run_pipeline(raw_dir, n_simulations=10)

    assert "group_probabilities" in result
    assert "strengths" in result
    assert "elo_ratings" in result
    assert result["group_probabilities"]["advance_probability"].between(0, 1).all()
