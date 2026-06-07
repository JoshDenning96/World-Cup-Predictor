"""Data loading utilities for the World Cup Predictor."""
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

RAW_FILES = {
    "ranking": "fifa_ranking-2024-06-20.csv",
    "results": "results.csv",
    "schedule": "FIFA2026_schedule.csv",
    "schedule_utc": "fifa-world-cup-2026-UTC.csv",
    "schedule_fixtures": "FIFA2026_schedule_Fixtures.csv",
}


def _find_latest_ranking_file(raw_dir: Path) -> Optional[Path]:
    raw_dir = Path(raw_dir)
    candidates = set()
    candidates.add(raw_dir / RAW_FILES["ranking"])
    candidates.update(raw_dir.glob("fifa_ranking*.csv"))
    candidates.update(raw_dir.glob("fifa_rankings*.csv"))
    candidates = [p for p in candidates if p.exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def resolve_raw_path(raw_dir: Path, key: str) -> Path:
    raw_dir = Path(raw_dir)
    if key not in RAW_FILES:
        raise ValueError(
            f"Unknown raw data key '{key}'. Supported keys: {', '.join(RAW_FILES)}"
        )

    if key == "ranking":
        ranking_path = _find_latest_ranking_file(raw_dir)
        if ranking_path is None:
            raise FileNotFoundError(
                f"No FIFA ranking file found in {raw_dir}."
            )
        return ranking_path

    return raw_dir / RAW_FILES[key]


def load_fifa_ranking(raw_dir: Path) -> pd.DataFrame:
    """Load the FIFA ranking file from the raw data directory."""
    return pd.read_csv(resolve_raw_path(raw_dir, "ranking"))


def load_results(raw_dir: Path) -> pd.DataFrame:
    """Load historical match results from the raw data directory."""
    return pd.read_csv(resolve_raw_path(raw_dir, "results"))


def load_wcup_schedule(raw_dir: Path) -> pd.DataFrame:
    """Load the World Cup schedule from the raw data directory."""
    return pd.read_csv(resolve_raw_path(raw_dir, "schedule"))


def load_utc_schedule(raw_dir: Path) -> pd.DataFrame:
    """Load the UTC world cup schedule from the raw data directory."""
    return pd.read_csv(resolve_raw_path(raw_dir, "schedule_utc"))


def load_fixtures_schedule(raw_dir: Path) -> pd.DataFrame:
    """Load the official FIFA fixtures schedule from the raw data directory."""
    return pd.read_csv(resolve_raw_path(raw_dir, "schedule_fixtures"))


def load_all(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    """Load all available raw files into a dictionary of DataFrames."""
    raw_dir = Path(raw_dir)
    data = {
        "ranking": load_fifa_ranking(raw_dir),
        "results": load_results(raw_dir),
        "schedule": load_wcup_schedule(raw_dir),
        "schedule_utc": load_utc_schedule(raw_dir),
    }

    fixtures_path = raw_dir / RAW_FILES["schedule_fixtures"]
    if fixtures_path.exists():
        data["schedule_fixtures"] = load_fixtures_schedule(raw_dir)

    return data
