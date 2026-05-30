# World Cup Predictor Plan

## Overview
Build a reproducible Python forecasting pipeline for the 2026 FIFA World Cup using historical match data, statistical models, tournament simulation, and HTML presentation output.

## Goals
- Ingest and clean historical international and World Cup match data
- Engineer interpretable match features including Elo ratings, form, and tournament context
- Fit statistical match models (Poisson goals, Elo probabilities)
- Simulate the 2026 tournament to estimate team advancement and title probability
- Document the process clearly and generate an HTML slide deck for stakeholders
- Enable reproducible development with GitHub Actions CI

## Steps
1. Scaffold repository layout, dependencies, and CI workflow
2. Collect raw match and ranking data into `data/raw/`
3. Explore data in notebooks under `notebooks/`
4. Implement feature engineering in `src/world_cup_predictor/feature_engineering.py`
5. Build statistical match models in `src/world_cup_predictor/stat_models.py`
6. Build a tournament simulator in `src/world_cup_predictor/simulator.py`
7. Validate with unit tests in `tests/`
8. Document methodology in `METHODOLOGY.md` and source references in `DATA_SOURCES.md`
9. Export results and visualisations to an HTML slide deck

## Files to create
- `plan.md`
- `README.md`
- `requirements.txt`
- `.gitignore`
- `Makefile`
- `LICENSE`
- `METHODOLOGY.md`
- `DATA_SOURCES.md`
- `src/world_cup_predictor/__init__.py`
- `src/world_cup_predictor/data_loader.py`
- `src/world_cup_predictor/feature_engineering.py`
- `src/world_cup_predictor/stat_models.py`
- `src/world_cup_predictor/simulator.py`
- `src/world_cup_predictor/cli.py`
- `tests/test_data_loader.py`
- `tests/test_feature_engineering.py`
- `tests/test_simulator.py`
- `.github/workflows/ci.yml`
- `notebooks/01-explore.ipynb`
- `notebooks/02-results.ipynb`

## Verification
1. `python -m pytest tests`
2. `make install`
3. `make example`
4. `PYTHONPATH=src python -m world_cup_predictor.cli example`

## Decisions
- License: MIT
- CI: GitHub Actions enabled
- Initial scope: statistical models only
- Presentation output: HTML slides