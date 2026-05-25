"""World Cup Predictor package."""

from .data_loader import (
    load_all,
    load_fifa_ranking,
    load_results,
    load_wcup_schedule,
    load_utc_schedule,
)
from .feature_engineering import (
    attach_rankings_to_matches,
    load_and_prepare_raw,
    normalize_team_name,
    parse_date_column,
    standardize_ranking,
    standardize_results,
    standardize_schedule_utc,
)
from .stat_models import (
    elo_expected_score,
    fit_elo_ratings,
    fit_poisson_attack_defense,
    predict_elo_win_probability,
    predict_poisson_scores,
    simulate_match,
)
from .simulator import (
    aggregate_group_standings,
    calculate_match_probabilities,
    simulate_group_stage,
    simulate_group_tables,
    simulate_knockout_match,
    simulate_full_tournament,
)

__all__ = [
    "load_all",
    "load_fifa_ranking",
    "load_results",
    "load_wcup_schedule",
    "load_utc_schedule",
    "attach_rankings_to_matches",
    "load_and_prepare_raw",
    "normalize_team_name",
    "parse_date_column",
    "standardize_ranking",
    "standardize_results",
    "standardize_schedule_utc",
    "elo_expected_score",
    "fit_elo_ratings",
    "fit_poisson_attack_defense",
    "predict_elo_win_probability",
    "predict_poisson_scores",
    "simulate_match",
    "aggregate_group_standings",
    "calculate_match_probabilities",
    "simulate_group_stage",
    "simulate_group_tables",
    "simulate_knockout_match",
    "simulate_full_tournament",
]
