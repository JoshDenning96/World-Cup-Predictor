from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "processed"
XLSX_PATH = CSV_DIR / "master_simulation.xlsx"
OUTPUT_PATH = ROOT / "website" / "data" / "master_simulation.json"

SOURCE_FILES = {
    "elo_ratings": "elo_ratings.csv",
    "group_tables": "predicted_group_tables.csv",
    "tournament_simulation": "tournament_simulation.csv",
    "group_probabilities": "group_probabilities.csv",
}


def parse_value(value: str) -> Any:
    if value is None or value == "":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip()


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            parsed = {key: parse_value(value) for key, value in row.items()}
            rows.append(parsed)
    return rows


def load_xlsx(path: Path) -> dict[str, list[dict[str, Any]]]:
    try:
        import pandas as pd
    except ImportError as error:
        raise ImportError("Pandas is required to read the master_simulation.xlsx file. Install it with `pip install pandas openpyxl`.") from error

    data = {}
    workbook = pd.read_excel(path, sheet_name=None)
    mapping = {
        "elo_ratings": "elo_ratings",
        "group_tables": "predicted_group_tables",
        "tournament_simulation": "tournament_simulation",
    }

    for key, sheet_name in mapping.items():
        if sheet_name in workbook:
            data[key] = workbook[sheet_name].fillna("").to_dict(orient="records")
        else:
            data[key] = []

    # Derive advance probabilities from group tables if not present in workbook.
    if "group_probabilities" not in data or not data["group_probabilities"]:
        if data["group_tables"]:
            probs = {}
            for row in data["group_tables"]:
                team = row.get("team")
                prob_1 = row.get("prob_1") or 0
                prob_2 = row.get("prob_2") or 0
                if team:
                    probs[team] = probs.get(team, 0) + prob_1 + prob_2
            data["group_probabilities"] = [
                {"team": team, "advance_probability": prob}
                for team, prob in sorted(probs.items(), key=lambda item: item[1], reverse=True)
            ]
        else:
            data["group_probabilities"] = []

    return data


def export_json() -> None:
    if XLSX_PATH.exists():
        try:
            output = load_xlsx(XLSX_PATH)
            print(f"Loaded simulation data from {XLSX_PATH}")
        except Exception as exc:
            print(f"Warning: failed to load {XLSX_PATH} ({exc}). Falling back to CSV files.")
            output = {key: load_csv(CSV_DIR / filename) for key, filename in SOURCE_FILES.items()}
    else:
        output = {key: load_csv(CSV_DIR / filename) for key, filename in SOURCE_FILES.items()}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported simulation JSON to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_json()
