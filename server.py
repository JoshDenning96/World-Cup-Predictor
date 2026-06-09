#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime
import json
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
WEB_DIR = ROOT / "website"
RAW_DIR = ROOT / "data" / "raw"
SAVE_DIR = WEB_DIR / "data" / "saved_simulations"
SCHEDULE_FILE = RAW_DIR / "fifa-world-cup-2026-UTC.csv"

# Default CONMEBOL Elo offset applied by the website server
DEFAULT_CONMEBOL_OFFSET = -20.0

sys.path.insert(0, str(SRC_DIR))

try:
    from world_cup_predictor.cli import run_pipeline
except Exception as exc:
    raise SystemExit(f"Unable to import simulation code: {exc}") from exc


def load_knockout_schedule(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            round_name = str(row.get("Round Number", "") or "").strip()
            if not round_name.startswith("Round of") and round_name != "Finals":
                continue
            match_number = row.get("Match Number", "")
            try:
                match_number = int(match_number)
            except (TypeError, ValueError):
                match_number = None

            rows.append(
                {
                    "match_number": match_number,
                    "round": round_name,
                    "date": str(row.get("Date", "") or "").strip(),
                    "location": str(row.get("Location", "") or "").strip(),
                    "home": str(row.get("Home Team", "") or "").strip(),
                    "away": str(row.get("Away Team", "") or "").strip(),
                }
            )
    rows.sort(key=lambda r: (r.get("match_number") is None, r.get("match_number") or 0))
    return rows


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

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/run_simulation":
            self.handle_run_simulation()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_run_simulation(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            payload = json.loads(body) if body else {}
            simulations = int(payload.get("simulations", 200))
        except Exception as exc:
            self.send_error(400, f"Invalid request body: {exc}")
            return

        try:
            result = run_pipeline(
                RAW_DIR,
                n_simulations=simulations,
                run_full_tournament=True,
                conmebol_offset=DEFAULT_CONMEBOL_OFFSET,
            )
            tournament_simulation = result["tournament_simulation"].to_dict(orient="records")
            group_tables = result["group_tables"].to_dict(orient="records")
            group_probabilities = result["group_probabilities"].to_dict(orient="records")
            knockout_schedule = load_knockout_schedule(SCHEDULE_FILE)

            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            filename = f"simulation_runs_{simulations}_{timestamp}.json"
            save_path = SAVE_DIR / filename
            output = {
                "simulations": simulations,
                "tournament_simulation": tournament_simulation,
                "group_tables": group_tables,
                "group_probabilities": group_probabilities,
                "knockout_schedule": knockout_schedule,
            }
            save_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

            response = {**output, "saved_filename": str(Path("website") / "data" / "saved_simulations" / filename)}
            body = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_body = json.dumps({"error": str(exc)})
            self.wfile.write(error_body.encode("utf-8"))


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
