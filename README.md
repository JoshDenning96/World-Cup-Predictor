# World Cup 2026 Predictor

A Monte Carlo simulation dashboard for the FIFA World Cup 2026. Run simulations, track how win probabilities shift as the tournament progresses, and update the bracket with real results as matches are played.

## Features

- **Full simulation mode** — simulate the entire tournament from scratch using Elo ratings
- **Actuals + simulation mode** — lock in real results as they happen and simulate forward from the current state
- **Interactive bracket** — projected bracket with colour-coded win probabilities; green dots indicate positions confirmed by actual results
- **Simulation history chart** — track how team win probabilities change across simulation runs over time
- **Group stage tables** — expected standings and finishing probabilities per group
- **Tournament & advance probability charts** — top contenders ranked by likelihood

## How it works

Match outcomes are determined using FIFA Elo ratings. The rating difference between two teams sets the win/draw/loss probabilities for each simulated match. Knockout draws are resolved as a 50/50 coin flip (simulating a penalty shootout). A −20 Elo point adjustment is applied by default to all qualified CONMEBOL teams.

The simulation is run N times (user-selected) and probabilities reflect how often each outcome occurred — not a single prediction.

## Getting started

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Start the server**
```bash
python3 server.py
```

**3. Open the dashboard**

Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Entering actual results

Switch to **Actuals + simulation** mode using the dropdown in the dashboard. The actuals panel shows tabs for each group (A–L) and each knockout round (R32, R16, QF, SF, Final).

- **Group stage** — enter home and away scores for each match
- **Knockout rounds** — click the winning team's button (score doesn't matter, only the winner advances)

Once results are entered, click **Run simulation** to simulate the tournament forward from the current state. Bracket positions confirmed by actual results are shown with a green dot.

To clear all entered results, use the **Reset all results** button in the actuals panel.

## Project structure

```
.
├── server.py                        # Local web server + simulation API
├── src/world_cup_predictor/
│   ├── simulator.py                 # Monte Carlo tournament simulation
│   ├── stat_models.py               # Elo match probability model
│   └── cli.py                       # Command-line interface
├── website/
│   ├── index.html                   # Dashboard UI
│   ├── app.js                       # Frontend logic
│   ├── styles.css                   # Styles
│   └── data/
│       ├── master_simulation.json   # Latest simulation (loaded on page start)
│       ├── actual_results.json      # Persisted actual match results
│       └── saved_simulations/       # Simulation history (generated at runtime)
├── data/raw/                        # FIFA 2026 schedule and fixture data
└── tests/                           # Test suite
```

## CLI

Run the simulation directly from the command line:

```bash
# Group stage only
PYTHONPATH=src python -m world_cup_predictor.cli --simulations 200

# Full tournament
PYTHONPATH=src python -m world_cup_predictor.cli --simulations 1000 --full-tournament

# With CONMEBOL adjustment
PYTHONPATH=src python -m world_cup_predictor.cli --simulations 1000 --full-tournament --conmebol-offset -20
```

## License

MIT
