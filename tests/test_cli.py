from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression

from world_cup_predictor.cli import optimize_elo_parameters, run_pipeline


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
    assert "group_tables" in result
    assert "strengths" in result
    assert "elo_ratings" in result
    assert result["group_probabilities"]["advance_probability"].between(0, 1).all()
    assert "prob_1" in result["group_tables"].columns
    assert "prob_2" in result["group_tables"].columns
    assert "expected_rank" in result["group_tables"].columns


def test_run_pipeline_includes_qualified_elo_fifa_comparison(tmp_path: Path):
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
            "date": ["Long Date 1", "Long Date 2", "Long Date 3"],
            "date_dt": ["2026-11-21", "2026-11-22", "2026-11-23"],
            "group": ["A", "A", pd.NA],
            "round_number": [pd.NA, pd.NA, "Round of 32"],
            "home team": ["Spain", "Japan", "1A"],
            "away team": ["Japan", "Spain", "2A"],
            "stadium": ["Stadium A", "Stadium B", "Stadium C"],
        }
    ).to_csv(raw_dir / "fifa-world-cup-2026-UTC.csv", index=False)

    result = run_pipeline(raw_dir, n_simulations=10, run_full_tournament=True)

    assert "qualified_elo_fifa_comparison" in result
    comparison = result["qualified_elo_fifa_comparison"]
    assert list(comparison.columns) == [
        "team",
        "fifa_team",
        "elo",
        "elo_rank",
        "fifa_rank",
        "elo_minus_fifa_rank",
    ]
    assert len(comparison) == 2


def test_optimize_elo_parameters_returns_best_settings(tmp_path: Path):
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

    best_row, result_df = optimize_elo_parameters(
        raw_dir, k_values=[10.0, 20.0], half_life_values=[365.0, 1095.0]
    )

    assert "spearman_correlation" in result_df.columns
    assert best_row["k"] in {10.0, 20.0}
