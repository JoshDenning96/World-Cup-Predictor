#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime
import json
import re
import socket
import sys
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
WEB_DIR = ROOT / "website"
RAW_DIR = ROOT / "data" / "raw"
SAVE_DIR = WEB_DIR / "data" / "saved_simulations"
FIXTURES_FILE = RAW_DIR / "FIFA2026_schedule_Fixtures.csv"
UTC_SCHEDULE_FILE = RAW_DIR / "fifa-world-cup-2026-UTC.csv"
ACTUAL_RESULTS_FILE = WEB_DIR / "data" / "actual_results.json"

# Default CONMEBOL Elo offset applied by the website server
DEFAULT_CONMEBOL_OFFSET = -45.0

sys.path.insert(0, str(SRC_DIR))

try:
    from world_cup_predictor.cli import run_pipeline
except Exception as exc:
    raise SystemExit(f"Unable to import simulation code: {exc}") from exc

# In-memory job store for async simulation progress tracking
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _parse_fixture_slot(s: str) -> str:
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


def load_knockout_schedule(path: Path) -> list[dict[str, str]]:
    import re
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
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
                continue

            teams = str(row.get("teams", "") or "").strip()
            parts = re.split(r"\s+v\s+", teams, maxsplit=1)
            if len(parts) != 2:
                continue

            rows.append({
                "match_number": match_number,
                "round": round_name,
                "home": _parse_fixture_slot(parts[0]),
                "away": _parse_fixture_slot(parts[1]),
                "location": str(row.get("stadium", "") or "").strip(),
                "date": str(row.get("date", "") or "").strip(),
            })

    rows.sort(key=lambda r: r["match_number"])
    return rows


def load_group_schedule(path: Path) -> list[dict]:
    """Load the group stage schedule from the UTC CSV file."""
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            # only group stage rows have a Group value
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


def load_actual_results() -> dict:
    """Load actual results as a dict keyed by str(match_number)."""
    if not ACTUAL_RESULTS_FILE.exists():
        return {}
    try:
        items = json.loads(ACTUAL_RESULTS_FILE.read_text(encoding="utf-8"))
        return {str(item["match_number"]): item for item in items if "match_number" in item}
    except Exception:
        return {}


def save_actual_result(match_number: int, home_goals: int, away_goals: int, winner: str | None = None) -> None:
    """Upsert a single actual result into the JSON file."""
    ACTUAL_RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if ACTUAL_RESULTS_FILE.exists():
        try:
            items = json.loads(ACTUAL_RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            items = []
    else:
        items = []

    entry: dict = {"match_number": match_number, "home_goals": home_goals, "away_goals": away_goals}
    if winner:
        entry["winner"] = winner
    items = [i for i in items if i.get("match_number") != match_number]
    items.append(entry)
    items.sort(key=lambda i: i["match_number"])
    ACTUAL_RESULTS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def find_available_port(start: int = 8000, max_port: int = 8100) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for port in range(start, max_port):
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port found between {start} and {max_port - 1}")


class SimulationHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/actual_results":
            self.handle_get_actual_results()
        elif parsed.path == "/api/simulation_status":
            qs = parse_qs(parsed.query)
            job_id = qs.get("job_id", [None])[0]
            self.handle_simulation_status(job_id)
        elif parsed.path == "/api/simulation_history":
            self.handle_simulation_history()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/run_simulation":
            self.handle_run_simulation()
        elif parsed.path == "/api/save_actual":
            self.handle_save_actual()
        elif parsed.path == "/api/clear_history":
            self.handle_clear_history()
        elif parsed.path == "/api/clear_actuals":
            self.handle_clear_actuals()
        else:
            self.send_error(404, "Endpoint not found")

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_get_actual_results(self):
        actuals = load_actual_results()
        self._send_json(list(actuals.values()))

    def handle_save_actual(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            payload = json.loads(body) if body else {}
            match_number = int(payload["match_number"])
            home_goals = int(payload["home_goals"])
            away_goals = int(payload["away_goals"])
            winner = str(payload["winner"]) if payload.get("winner") else None
        except Exception as exc:
            self._send_json({"error": f"Invalid request: {exc}"}, status=400)
            return
        save_actual_result(match_number, home_goals, away_goals, winner)
        self._send_json({"ok": True, "match_number": match_number})

    def handle_run_simulation(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            payload = json.loads(body) if body else {}
            simulations = int(payload.get("simulations", 200))
            conmebol_offset = float(payload.get("conmebol_offset", DEFAULT_CONMEBOL_OFFSET))
            use_actuals = bool(payload.get("use_actuals", False))
            actuals_list = payload.get("actual_results", [])
            run_label = str(payload.get("label", "")).strip()[:80]
        except Exception as exc:
            self.send_error(400, f"Invalid request body: {exc}")
            return

        if use_actuals:
            if actuals_list:
                actual_results = {str(item["match_number"]): item for item in actuals_list if "match_number" in item}
            else:
                actual_results = load_actual_results()
        else:
            actual_results = None

        job_id = uuid.uuid4().hex[:12]
        with _jobs_lock:
            _jobs[job_id] = {"progress": 0.0, "done": False, "result": None, "error": None}

        def _run():
            def on_progress(completed, total):
                with _jobs_lock:
                    _jobs[job_id]["progress"] = completed / total

            try:
                result = run_pipeline(
                    RAW_DIR,
                    n_simulations=simulations,
                    run_full_tournament=True,
                    conmebol_offset=conmebol_offset,
                    actual_results=actual_results,
                    progress_callback=on_progress,
                )
                tournament_simulation = result["tournament_simulation"].to_dict(orient="records")
                group_tables = result["group_tables"].to_dict(orient="records")
                group_probabilities = result["group_probabilities"].to_dict(orient="records")
                knockout_schedule = load_knockout_schedule(FIXTURES_FILE)
                group_schedule = load_group_schedule(UTC_SCHEDULE_FILE)

                SAVE_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                mode_tag = "actuals" if use_actuals else "full"
                safe_label = re.sub(r"[^\w\-]", "_", run_label)[:40] if run_label else ""
                label_part = f"_{safe_label}" if safe_label else ""
                filename = f"simulation_{mode_tag}_{simulations}{label_part}_{timestamp}.json"
                save_path = SAVE_DIR / filename
                output = {
                    "simulations": simulations,
                    "conmebol_offset": conmebol_offset,
                    "use_actuals": use_actuals,
                    "label": run_label,
                    "tournament_simulation": tournament_simulation,
                    "group_tables": group_tables,
                    "group_probabilities": group_probabilities,
                    "knockout_schedule": knockout_schedule,
                    "group_schedule": group_schedule,
                    "saved_filename": str(Path("website") / "data" / "saved_simulations" / filename),
                }
                payload = json.dumps(output, indent=2)
                save_path.write_text(payload, encoding="utf-8")
                (WEB_DIR / "data" / "master_simulation.json").write_text(payload, encoding="utf-8")
                with _jobs_lock:
                    _jobs[job_id]["result"] = output
                    _jobs[job_id]["progress"] = 1.0
                    _jobs[job_id]["done"] = True
            except Exception as exc:
                with _jobs_lock:
                    _jobs[job_id]["error"] = str(exc)
                    _jobs[job_id]["done"] = True

        threading.Thread(target=_run, daemon=True).start()
        self._send_json({"job_id": job_id})

    def handle_simulation_status(self, job_id):
        if not job_id:
            self._send_json({"error": "Missing job_id"}, status=400)
            return
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job is None:
            self._send_json({"error": "Unknown job_id"}, status=404)
            return
        self._send_json({
            "progress": job["progress"],
            "done": job["done"],
            "result": job["result"] if job["done"] and not job["error"] else None,
            "error": job["error"],
        })

    def handle_clear_actuals(self):
        try:
            ACTUAL_RESULTS_FILE.write_text("[]", encoding="utf-8")
            self._send_json({"ok": True})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def handle_clear_history(self):
        try:
            if not SAVE_DIR.exists():
                self._send_json({"archived": 0})
                return
            archive_dir = SAVE_DIR / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for f in SAVE_DIR.glob("*.json"):
                dest = archive_dir / f.name
                if dest.exists():
                    dest = archive_dir / f"{f.stem}_{uuid.uuid4().hex[:6]}{f.suffix}"
                f.rename(dest)
                count += 1
            self._send_json({"archived": count})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def handle_simulation_history(self):
        history = []
        if SAVE_DIR.exists():
            for f in sorted(SAVE_DIR.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    ts_str = f.stem.rsplit("_", 1)[-1]
                    try:
                        ts = datetime.datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        ts = ts_str
                    win_probs = {
                        row["team"]: round(row.get("prob_Winner", 0), 4)
                        for row in data.get("tournament_simulation", [])
                        if row.get("team")
                    }
                    if win_probs and max(win_probs.values(), default=0) > 0:
                        history.append({
                            "timestamp": ts,
                            "label": str(data.get("label", "")).strip(),
                            "simulations": int(data.get("simulations", 0)),
                            "mode": "actuals" if data.get("use_actuals") else "full",
                            "win_probs": win_probs,
                            "url": f"data/saved_simulations/{f.name}",
                        })
                except Exception:
                    pass
        history.sort(key=lambda x: x["timestamp"])
        self._send_json(history)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    chosen_port = port
    try:
        server = ThreadingHTTPServer((host, chosen_port), SimulationHandler)
    except OSError:
        chosen_port = find_available_port(port + 1)
        server = ThreadingHTTPServer((host, chosen_port), SimulationHandler)

    if chosen_port != port:
        print(f"Port {port} was unavailable. Serving website at http://{host}:{chosen_port}")
    else:
        print(f"Serving website at http://{host}:{chosen_port}")
    print("POST /api/run_simulation with JSON {\"simulations\": <count>} to rerun the model.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
