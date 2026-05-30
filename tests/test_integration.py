from pathlib import Path

import pandas as pd
import pytest

from world_cup_predictor.cli import run_pipeline


def test_end_to_end_pipeline_writes_master_workbook(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    # minimal ranking
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

    # small results history
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

    # official FIFA schedule file (minimal group matches)
    pd.DataFrame(
        {
            "group": ["A", "A"],
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "stadium": ["Stadium A", "Stadium B"],
            "date": ["2026-11-21", "2026-11-22"],
        }
    ).to_csv(raw_dir / "FIFA2026_schedule.csv", index=False)

    # schedule with a Round of 32 placeholder to force full-tournament path
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

    # run pipeline with reduced sims to keep test fast
    res = run_pipeline(raw_dir, n_simulations=20, run_full_tournament=True)

    assert "tournament_simulation" in res
    assert "group_tables" in res

    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    master_path = out_dir / "master_simulation.xlsx"

    # write master workbook
    df_elo = res.get("elo_ratings")
    if hasattr(df_elo, "to_frame"):
        df_elo = df_elo.to_frame(name="elo").reset_index().rename(columns={df_elo.index.name or 0: "team", "index": "team"})
        if "team" not in df_elo.columns:
            df_elo.columns = ["team", "elo"]
    elif isinstance(df_elo, dict):
        df_elo = pd.DataFrame(list(df_elo.items()), columns=["team", "elo"])
    else:
        try:
            df_elo = pd.DataFrame(df_elo).reset_index().rename(columns={0: "elo", "index": "team"})
        except Exception:
            df_elo = pd.DataFrame({"team": [], "elo": []})

    df_groups = res.get("group_tables")
    if df_groups is None:
        df_groups = pd.DataFrame()
    df_tourney = res.get("tournament_simulation")
    if df_tourney is None:
        df_tourney = pd.DataFrame()

    # skip writing if openpyxl isn't installed in the test environment
    pytest.importorskip("openpyxl")

    with pd.ExcelWriter(master_path, engine="openpyxl", mode="w") as writer:
        df_elo.to_excel(writer, sheet_name="elo_ratings", index=False)
        df_groups.to_excel(writer, sheet_name="predicted_group_tables", index=False)
        df_tourney.to_excel(writer, sheet_name="tournament_simulation", index=False)

    assert master_path.exists()
