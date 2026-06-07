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
    assert "group_tables" in result
    assert "strengths" in result
    assert "elo_ratings" in result
    assert result["group_probabilities"]["advance_probability"].between(0, 1).all()
    assert "prob_1" in result["group_tables"].columns
    assert "prob_2" in result["group_tables"].columns
    assert "expected_rank" in result["group_tables"].columns


def test_run_pipeline_with_full_tournament_returns_group_tables_and_tournament_simulation(tmp_path: Path):
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

    assert "group_tables" in result
    assert "group_probabilities" in result
    assert "tournament_simulation" in result
    assert "elo_fifa_comparison" in result
    assert result["group_probabilities"]["advance_probability"].between(0, 1).all()
    assert "prob_1" in result["group_tables"].columns
    assert "prob_2" in result["group_tables"].columns
    assert "expected_rank" in result["group_tables"].columns


def test_run_pipeline_applies_conmebol_offset_only_to_qualified_teams(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    pd.DataFrame(
        {
            "rank": [1, 2],
            "country_full": ["Paraguay", "Spain"],
            "country_abrv": ["PAR", "ESP"],
            "total_points": [1800, 2000],
            "previous_points": [1750, 1950],
            "rank_change": [0, 0],
            "confederation": ["CONMEBOL", "UEFA"],
            "rank_date": ["2024-06-20", "2024-06-20"],
        }
    ).to_csv(raw_dir / "fifa_ranking-2024-06-20.csv", index=False)

    pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["Paraguay", "Spain"],
            "away_team": ["Spain", "Paraguay"],
            "home_score": [1, 0],
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
            "home_team": ["Paraguay", "Spain"],
            "away_team": ["Spain", "Paraguay"],
            "stadium": ["Stadium A", "Stadium B"],
            "date": ["2026-11-21", "2026-11-22"],
        }
    ).to_csv(raw_dir / "FIFA2026_schedule.csv", index=False)

    pd.DataFrame(
        {
            "date": ["Long Date 1", "Long Date 2"],
            "date_dt": ["2026-11-21", "2026-11-22"],
            "group": ["A", "A"],
            "home team": ["Paraguay", "Spain"],
            "away team": ["Spain", "Paraguay"],
            "stadium": ["Stadium A", "Stadium B"],
        }
    ).to_csv(raw_dir / "fifa-world-cup-2026-UTC.csv", index=False)

    result = run_pipeline(raw_dir, n_simulations=10, conmebol_offset=-20.0)

    assert result["elo_ratings"]["Paraguay"] == result["raw_elo_ratings"]["Paraguay"] - 20.0
    assert result["elo_ratings"]["Spain"] == result["raw_elo_ratings"]["Spain"]


def test_run_pipeline_applies_conmebol_offset_when_ranking_lacks_confederation(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    pd.DataFrame(
        {
            "rank": [1, 2, 3],
            "country_full": ["Argentina", "Spain", "Japan"],
            "country_abrv": ["ARG", "ESP", "JPN"],
            "total_points": [1874.81, 1876.40, 1660.43],
            "previous_points": [1850, 1870, 1650],
            "rank_change": [0, 0, 0],
            "rank_date": ["2024-06-20", "2024-06-20", "2024-06-20"],
        }
    ).to_csv(raw_dir / "fifa_ranking-2024-06-20.csv", index=False)

    pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["Argentina", "Spain"],
            "away_team": ["Spain", "Japan"],
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
            "home_team": ["Argentina", "Spain"],
            "away_team": ["Spain", "Japan"],
            "stadium": ["Stadium A", "Stadium B"],
            "date": ["2026-11-21", "2026-11-22"],
        }
    ).to_csv(raw_dir / "FIFA2026_schedule.csv", index=False)

    pd.DataFrame(
        {
            "date": ["Long Date 1", "Long Date 2"],
            "date_dt": ["2026-11-21", "2026-11-22"],
            "group": ["A", "A"],
            "home team": ["Argentina", "Spain"],
            "away team": ["Spain", "Japan"],
            "stadium": ["Stadium A", "Stadium B"],
        }
    ).to_csv(raw_dir / "fifa-world-cup-2026-UTC.csv", index=False)

    result = run_pipeline(raw_dir, n_simulations=10, conmebol_offset=-20.0)

    assert result["elo_ratings"]["Argentina"] == result["raw_elo_ratings"]["Argentina"] - 20.0
    assert result["elo_ratings"]["Spain"] == result["raw_elo_ratings"]["Spain"]


def test_run_pipeline_uses_latest_fifa_ranking_file_if_present(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    pd.DataFrame(
        {
            "Rank": ["1\n2", "2\n1"],
            "Team": ["France", "Spain"],
            "Last Result": ["France\nCôte d'Ivoire\nFT\n1\n2", "Spain\nIraq\nFT\n1\n1"],
            "Points": ["1877.32*", "1876.40*"],
        }
    ).to_csv(raw_dir / "fifa_rankings_2026-01-19.csv", index=False)

    pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["France", "Spain"],
            "away_team": ["Spain", "France"],
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
            "home_team": ["France", "Spain"],
            "away_team": ["Spain", "France"],
            "stadium": ["Stadium A", "Stadium B"],
            "date": ["2026-11-21", "2026-11-22"],
        }
    ).to_csv(raw_dir / "FIFA2026_schedule.csv", index=False)

    pd.DataFrame(
        {
            "date": ["Long Date 1", "Long Date 2"],
            "date_dt": ["2026-11-21", "2026-11-22"],
            "group": ["A", "A"],
            "home team": ["France", "Spain"],
            "away team": ["Spain", "France"],
            "stadium": ["Stadium A", "Stadium B"],
        }
    ).to_csv(raw_dir / "fifa-world-cup-2026-UTC.csv", index=False)

    result = run_pipeline(raw_dir, n_simulations=10)

    assert "elo_fifa_comparison" in result
    assert result["elo_fifa_comparison"].loc[0, "rank"] == 1
    assert result["elo_fifa_comparison"].loc[1, "rank"] == 2
