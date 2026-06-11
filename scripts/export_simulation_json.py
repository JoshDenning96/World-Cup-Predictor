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

FIXTURES_FILE = ROOT / "data" / "raw" / "FIFA2026_schedule_Fixtures.csv"
UTC_SCHEDULE_FILE = ROOT / "data" / "raw" / "fifa-world-cup-2026-UTC.csv"


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


def _parse_fixture_slot(s: str) -> str:
    """Convert a human-readable team slot to a bracket code.

    Examples:
      'Group A runners-up'            -> '2A'
      'Group E winners'               -> '1E'
      'Group A/B/C/D/F third place'   -> '3ABCDF'
      'Winner match 74'               -> 'W74'
      'Runner-up match 101'           -> 'RU101'
    """
    import re
    s = s.strip()
    m = re.match(r"Group ([A-L])\s+runners[-\s]*up", s, re.IGNORECASE)
    if m:
        return f"2{m.group(1).upper()}"
    m = re.match(r"Group ([A-L])\s+winners?", s, re.IGNORECASE)
    if m:
        return f"1{m.group(1).upper()}"
    m = re.match(r"Group ([A-L/]+)\s+third\s+place", s, re.IGNORECASE)
    if m:
        return "3" + m.group(1).upper().replace("/", "")
    m = re.match(r"Winner\s+match\s+(\d+)", s, re.IGNORECASE)
    if m:
        return f"W{m.group(1)}"
    m = re.match(r"Runner[-\s]*up\s+match\s+(\d+)", s, re.IGNORECASE)
    if m:
        return f"RU{m.group(1)}"
    return s


def _round_name(match_number: int) -> str:
    if 73 <= match_number <= 88:
        return "Round of 32"
    if 89 <= match_number <= 96:
        return "Round of 16"
    if 97 <= match_number <= 100:
        return "Quarter Finals"
    if 101 <= match_number <= 102:
        return "Semi Finals"
    if match_number == 104:
        return "Finals"
    return ""


def load_group_schedule(path: Path) -> list[dict[str, Any]]:
    """Load group stage matches from the UTC schedule CSV."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            group = str(row.get("Group", "") or "").strip()
            if not group:
                continue
            try:
                mn = int(str(row.get("Match Number", "") or "").strip())
            except ValueError:
                continue
            rows.append({
                "match_number": mn,
                "date": str(row.get("Date", "") or "").strip(),
                "home_team": str(row.get("Home Team", "") or "").strip(),
                "away_team": str(row.get("Away Team", "") or "").strip(),
                "group": group,
                "stadium": str(row.get("Location", "") or "").strip(),
            })
    rows.sort(key=lambda r: r["match_number"])
    return rows


def load_knockout_schedule(path: Path) -> list[dict[str, Any]]:
    """Load the full knockout bracket from the FIFA2026_schedule_Fixtures.csv file.

    Produces bracket-code slots for R32 (e.g. '1E', '3ABCDF') and feeder
    references for later rounds (e.g. 'W74').  Match 103 (third-place play-off)
    is omitted intentionally.
    """
    import re
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mn_raw = str(row.get("match_number", "") or "").strip()
            m = re.match(r"Match\s+(\d+)", mn_raw, re.IGNORECASE)
            if not m:
                continue
            match_number = int(m.group(1))
            round_name = _round_name(match_number)
            if not round_name:
                continue  # group stage or third-place play-off

            teams = str(row.get("teams", "") or "").strip()
            parts = re.split(r"\s+v\s+", teams, maxsplit=1)
            if len(parts) != 2:
                continue
            home = _parse_fixture_slot(parts[0])
            away = _parse_fixture_slot(parts[1])

            rows.append({
                "match_number": match_number,
                "round": round_name,
                "home": home,
                "away": away,
                "location": str(row.get("stadium", "") or "").strip(),
                "date": str(row.get("date", "") or "").strip(),
            })

    rows.sort(key=lambda r: r["match_number"])
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

    output["knockout_schedule"] = load_knockout_schedule(FIXTURES_FILE)
    output["group_schedule"] = load_group_schedule(UTC_SCHEDULE_FILE)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported simulation JSON to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_json()
