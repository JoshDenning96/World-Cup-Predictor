# World Cup Predictor

A machine learning system for predicting FIFA World Cup match outcomes and tournament results.

## Features
- Historical World Cup data analysis
- Team performance metrics
- Match outcome predictions
- Interactive prediction interface

## Installation
```bash
pip install -r requirements.txt
```

## Usage
```python
from world_cup_predictor import WorldCupPredictor

predictor = WorldCupPredictor()
predictions = predictor.predict_match(team1, team2)
```

## CLI

Run the pipeline and optionally simulate the full tournament using ELO-based probabilities.

## Web visualization
A static dashboard is available in the `website/` folder. It renders the latest simulation results using the exported data from `data/processed`.

To use it:
```bash
python3 scripts/export_simulation_json.py
python3 -m http.server 8000 --directory website
```

Then open `http://127.0.0.1:8000` in your browser.

The site loads the following JSON payload generated from the latest processed CSV outputs:
- `elo_ratings`
- `group_tables`
- `tournament_simulation`
- `group_probabilities`

## CLI

Run the pipeline and optionally simulate the full tournament using ELO-based probabilities.

Group-stage simulation (default):
```bash
PYTHONPATH=src python -m world_cup_predictor.cli --simulations 200
```

Full tournament simulation (ELO-driven):
```bash
PYTHONPATH=src python -m world_cup_predictor.cli --simulations 2000 --full-tournament
```

When `--full-tournament` is provided the CLI will run the full tournament simulation and include a `tournament_simulation` table in the output. It also writes a master workbook at `data/processed/master_simulation.xlsx` with these sheets:
- `elo_ratings`
- `predicted_group_tables`
- `tournament_simulation`

To persist results programmatically, call `simulate_full_tournament()` from `src/world_cup_predictor/simulator.py` and save the returned DataFrame to `data/processed/`.

## Project Structure
.
├── src/world_cup_predictor/  # Source code
├── tests/                     # Test suite
├── notebooks/               # Jupyter notebooks
├── data/                    # Data files
├── models/                  # Trained models
└── requirements.txt         # Dependencies

## License
MIT - see LICENSE file