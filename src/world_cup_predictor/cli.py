"""Command-line interface for the World Cup Predictor."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

from .feature_engineering import load_and_prepare_raw
from .simulator import calculate_match_probabilities, simulate_group_stage
from .stat_models import fit_elo_ratings, fit_poisson_attack_defense


def run_pipeline(raw_dir: Path, n_simulations: int = 200) -> dict:
    raw_dir = Path(raw_dir)
    raw_data = load_and_prepare_raw(raw_dir)

    strengths = fit_poisson_attack_defense(raw_data["results"])
    elo_ratings = fit_elo_ratings(raw_data["results"])
    group_probabilities = simulate_group_stage(raw_data["schedule_utc"], strengths, n_simulations=n_simulations)

    first_match = raw_data["schedule_utc"].iloc[0]
    first_match_probabilities = calculate_match_probabilities(
        first_match["home_team"], first_match["away_team"], strengths
    )

    return {
        "strengths": strengths,
        "elo_ratings": elo_ratings,
        "group_probabilities": group_probabilities,
        "first_match_probabilities": first_match_probabilities,
        "first_match": {
            "home_team": first_match["home_team"],
            "away_team": first_match["away_team"],
            "group": first_match.get("group"),
            "date": first_match.get("date"),
        },
    }


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the World Cup Predictor pipeline.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Path to the raw CSV data directory.",
    )
    parser.add_argument(
        "--simulations",
        type=int,
        default=200,
        help="Number of simulated group-stage tournament runs.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_pipeline(args.raw_dir, n_simulations=args.simulations)

    print("\n=== World Cup Predictor Pipeline ===\n")
    print(f"Raw directory: {args.raw_dir}")
    print(f"Simulations: {args.simulations}\n")

    print("Top group advance probabilities:\n")
    print(result["group_probabilities"].head(12).to_string(index=False))

    print("\nFirst match prediction:\n")
    first_match = result["first_match"]
    print(
        f"{first_match['home_team']} vs {first_match['away_team']} "
        f"(group={first_match['group']}, date={first_match['date']})"
    )
    print(
        f"Home win: {result['first_match_probabilities']['home_win']:.3f}, "
        f"Draw: {result['first_match_probabilities']['draw']:.3f}, "
        f"Away win: {result['first_match_probabilities']['away_win']:.3f}"
    )

    print("\nElo rating snapshot for sample teams:\n")
    sample_teams = list(result["elo_ratings"])[:5]
    for team in sample_teams:
        print(f"  {team}: {result['elo_ratings'][team]:.1f}")


if __name__ == "__main__":
    main()
