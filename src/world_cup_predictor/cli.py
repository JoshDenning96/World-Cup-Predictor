"""Command-line interface for the World Cup Predictor."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd

from .feature_engineering import load_and_prepare_raw
from .simulator import calculate_match_probabilities, simulate_group_tables, simulate_full_tournament
from .stat_models import fit_elo_ratings, fit_poisson_attack_defense


def run_pipeline(raw_dir: Path, n_simulations: int = 200, run_full_tournament: bool = False) -> dict:
    raw_dir = Path(raw_dir)
    raw_data = load_and_prepare_raw(raw_dir)

    strengths = fit_poisson_attack_defense(raw_data["results"])
    elo_ratings = fit_elo_ratings(raw_data["results"])

    first_match = raw_data["schedule_utc"].iloc[0]
    first_match_probabilities = calculate_match_probabilities(
        first_match["home_team"], first_match["away_team"], strengths
    )

    result = {
        "strengths": strengths,
        "elo_ratings": elo_ratings,
        "first_match_probabilities": first_match_probabilities,
        "first_match": {
            "home_team": first_match["home_team"],
            "away_team": first_match["away_team"],
            "group": first_match.get("group"),
            "date": first_match.get("date"),
        },
    }

    if run_full_tournament:
        full_simulation = simulate_full_tournament(
            raw_data["schedule_utc"],
            strengths,
            n_simulations=n_simulations,
            elo_ratings=elo_ratings,
            return_group_tables=True,
        )
        result["tournament_simulation"] = full_simulation["tournament_simulation"]
        result["group_tables"] = full_simulation["group_tables"]
    else:
        result["group_tables"] = simulate_group_tables(
            raw_data["schedule_utc"],
            strengths,
            n_simulations=n_simulations,
            elo_ratings=elo_ratings,
        )

    result["group_probabilities"] = (
        result["group_tables"].assign(advance_probability=result["group_tables"]["prob_1"] + result["group_tables"]["prob_2"])
        [["group", "team", "advance_probability"]]
        .sort_values("advance_probability", ascending=False)
        .reset_index(drop=True)
    )

    return result


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
    parser.add_argument(
        "--full-tournament",
        action="store_true",
        help="Also run a full tournament simulation using ELO-based probabilities.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_pipeline(args.raw_dir, n_simulations=args.simulations, run_full_tournament=args.full_tournament)

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

    if args.full_tournament and "tournament_simulation" in result:
        print("\nTop tournament winners (sample):\n")
        print(result["tournament_simulation"].head(12).to_string(index=False))

        # Write a single master Excel workbook with key outputs (overwrites)
        out_dir = Path("data/processed")
        out_dir.mkdir(parents=True, exist_ok=True)
        master_path = out_dir / "master_simulation.xlsx"

        # Prepare ELO ratings as DataFrame
        elo_obj = result.get("elo_ratings")
        if hasattr(elo_obj, "to_frame"):
            df_elo = elo_obj.to_frame(name="elo").reset_index().rename(columns={elo_obj.index.name or 0: "team", "index": "team"})
            if "team" not in df_elo.columns:
                df_elo.columns = ["team", "elo"]
        elif isinstance(elo_obj, dict):
            df_elo = pd.DataFrame(list(elo_obj.items()), columns=["team", "elo"])
        else:
            try:
                df_elo = pd.DataFrame(elo_obj).reset_index().rename(columns={0: "elo", "index": "team"})
            except Exception:
                df_elo = pd.DataFrame({"team": [], "elo": []})

        # Predicted group tables
        df_groups = result.get("group_tables")
        if df_groups is None:
            df_groups = pd.DataFrame()

        # Tournament simulation
        df_tourney = result.get("tournament_simulation")
        if df_tourney is None:
            df_tourney = pd.DataFrame()

        with pd.ExcelWriter(master_path, engine="openpyxl", mode="w") as writer:
            df_elo.to_excel(writer, sheet_name="elo_ratings", index=False)
            df_groups.to_excel(writer, sheet_name="predicted_group_tables", index=False)
            df_tourney.to_excel(writer, sheet_name="tournament_simulation", index=False)

        print(f"\nMaster simulation workbook written to: {master_path}")


if __name__ == "__main__":
    main()
