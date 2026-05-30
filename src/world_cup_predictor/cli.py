"""Command-line interface for the World Cup Predictor."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import re

import pandas as pd
from scipy.stats import spearmanr

from .feature_engineering import load_and_prepare_raw, normalize_team_name, standardize_ranking
from .simulator import calculate_match_probabilities, simulate_group_tables, simulate_full_tournament
from .stat_models import (
    fit_draw_probability_model,
    fit_elo_ratings,
    fit_poisson_attack_defense,
    fit_poisson_goal_models,
)


def run_pipeline(
    raw_dir: Path,
    n_simulations: int = 200,
    run_full_tournament: bool = False,
    elo_k: float = 10.0,
    date_decay_half_life_days: float = 1825.0,
    train_draw_model: bool = True,
) -> dict:
    raw_dir = Path(raw_dir)
    raw_data = load_and_prepare_raw(raw_dir)

    strengths = fit_poisson_attack_defense(raw_data["results"])
    elo_ratings = fit_elo_ratings(
        raw_data["results"], k=elo_k, date_decay_half_life_days=date_decay_half_life_days
    )
    draw_probability_model = (
        fit_draw_probability_model(raw_data["results"], elo_ratings)
        if train_draw_model
        else None
    )
    poisson_goal_models = fit_poisson_goal_models(
        raw_data["results"], strengths=strengths, elo_ratings=elo_ratings
    )

    first_match = raw_data["schedule_utc"].iloc[0]
    first_match_probabilities = calculate_match_probabilities(
        first_match["home_team"],
        first_match["away_team"],
        strengths,
        elo_ratings=elo_ratings,
        draw_probability_model=draw_probability_model,
    )

    result = {
        "strengths": strengths,
        "elo_ratings": elo_ratings,
        "draw_probability_model": draw_probability_model,
        "poisson_goal_models": poisson_goal_models,
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
            draw_probability_model=draw_probability_model,
            poisson_goal_models=poisson_goal_models,
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
            draw_probability_model=draw_probability_model,
            poisson_goal_models=poisson_goal_models,
        )

    result["group_probabilities"] = (
        result["group_tables"].assign(advance_probability=result["group_tables"]["prob_1"] + result["group_tables"]["prob_2"])
        [["group", "team", "advance_probability"]]
        .sort_values("advance_probability", ascending=False)
        .reset_index(drop=True)
    )

    result["qualified_elo_fifa_comparison"] = build_qualified_elo_fifa_comparison(raw_data, elo_ratings)

    return result


def _extract_qualified_teams(schedule: pd.DataFrame) -> list[str]:
    placeholder = re.compile(r"^(?:\d+[A-L]?|To be announced|TBA|1st|2nd|Winner|Loser|Playoff|Qualifier|Group|\d+.*)$", re.IGNORECASE)
    teams = pd.concat([schedule["home_team"], schedule["away_team"]]).dropna().unique()
    return sorted(
        {
            normalize_team_name(team.strip())
            for team in teams
            if isinstance(team, str) and not placeholder.match(team.strip())
        }
    )


def build_qualified_elo_fifa_comparison(raw_data: dict[str, pd.DataFrame], elo_ratings: dict[str, float]) -> pd.DataFrame:
    qualified_teams = _extract_qualified_teams(raw_data["schedule_utc"])
    elo_df = pd.DataFrame(list(elo_ratings.items()), columns=["team", "elo"])
    elo_df["team_clean"] = elo_df["team"].str.strip().str.lower()
    elo_df["elo_rank"] = elo_df["elo"].rank(method="dense", ascending=False).astype(int)

    ranking = standardize_ranking(raw_data["ranking"])
    fifa_df = (
        ranking.sort_values("rank_date", ascending=False)
        .drop_duplicates("country_full")
        [["country_full", "rank"]]
        .rename(columns={"country_full": "fifa_team", "rank": "fifa_rank"})
    )
    fifa_df["team_clean"] = fifa_df["fifa_team"].str.strip().str.lower()

    qualified_df = pd.DataFrame({"team": qualified_teams})
    qualified_df["team_clean"] = qualified_df["team"].str.strip().str.lower()

    merged = qualified_df.merge(
        elo_df[["team_clean", "elo", "elo_rank"]], on="team_clean", how="left"
    ).merge(
        fifa_df[["team_clean", "fifa_team", "fifa_rank"]], on="team_clean", how="left"
    )

    merged["elo_minus_fifa_rank"] = merged["elo_rank"] - merged["fifa_rank"]
    merged = merged[
        ["team", "fifa_team", "elo", "elo_rank", "fifa_rank", "elo_minus_fifa_rank"]
    ].sort_values("elo_rank")
    return merged


def optimize_elo_parameters(
    raw_dir: Path,
    k_values: list[float] | None = None,
    half_life_values: list[float] | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    raw_data = load_and_prepare_raw(raw_dir)
    if k_values is None:
        k_values = [10.0, 20.0, 30.0, 40.0, 50.0, 75.0, 100.0]
    if half_life_values is None:
        half_life_values = [365.0, 730.0, 1095.0, 1460.0, 1825.0]

    results = []
    for k in k_values:
        for half_life in half_life_values:
            elo_ratings = fit_elo_ratings(
                raw_data["results"], k=k, date_decay_half_life_days=half_life
            )
            comparison = build_qualified_elo_fifa_comparison(raw_data, elo_ratings)
            comparison = comparison[comparison["fifa_rank"].notna()]
            if len(comparison) >= 2:
                corr, _ = spearmanr(comparison["elo_rank"], comparison["fifa_rank"])
            else:
                corr = float("nan")
            results.append(
                {
                    "k": k,
                    "date_decay_half_life_days": half_life,
                    "spearman_correlation": corr,
                }
            )

    result_df = pd.DataFrame(results).sort_values(
        "spearman_correlation", ascending=False
    ).reset_index(drop=True)
    best_row = result_df.iloc[0]
    return best_row, result_df


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
    parser.add_argument(
        "--elo-k",
        type=float,
        default=10.0,
        help="Elo K-factor for rating updates.",
    )
    parser.add_argument(
        "--elo-half-life-days",
        type=float,
        default=1825.0,
        help="Half-life (days) for recency decay when fitting Elo.",
    )
    parser.add_argument(
        "--no-draw-model",
        action="store_false",
        dest="train_draw_model",
        help="Disable training the draw-probability calibration model.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_pipeline(
        args.raw_dir,
        n_simulations=args.simulations,
        run_full_tournament=args.full_tournament,
        elo_k=args.elo_k,
        date_decay_half_life_days=args.elo_half_life_days,
        train_draw_model=args.train_draw_model,
    )

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
            df_comparison = result.get("qualified_elo_fifa_comparison", pd.DataFrame())
            df_comparison.to_excel(writer, sheet_name="qualified_elo_fifa_comparison", index=False)

        print(f"\nMaster simulation workbook written to: {master_path}")


if __name__ == "__main__":
    main()
