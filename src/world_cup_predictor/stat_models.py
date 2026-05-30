"""Statistical match models for the World Cup Predictor."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def fit_elo_ratings(
    results: pd.DataFrame,
    initial_rating: float = 1500.0,
    k: float = 20.0,
    home_advantage: float = 100.0,
) -> Dict[str, float]:
    """Fit simple Elo ratings from historical match results.

    The function updates ratings sequentially by match date.
    It returns the final rating for each team.
    """
    ratings: Dict[str, float] = {}
    results = results.copy()
    if "date" in results.columns:
        results = results.sort_values("date")

    for _, row in results.iterrows():
        home = row["home_team"]
        away = row["away_team"]
        home_score = float(row["home_score"])
        away_score = float(row["away_score"])

        ratings.setdefault(home, initial_rating)
        ratings.setdefault(away, initial_rating)

        home_rating = ratings[home] + home_advantage
        away_rating = ratings[away]

        expected_home = elo_expected_score(home_rating, away_rating)
        expected_away = 1 - expected_home

        if home_score > away_score:
            actual_home, actual_away = 1.0, 0.0
        elif home_score < away_score:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        ratings[home] += k * (actual_home - expected_home)
        ratings[away] += k * (actual_away - expected_away)

    return ratings


def elo_expected_score(home_rating: float, away_rating: float) -> float:
    """Compute the expected home win probability from Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((away_rating - home_rating) / 400.0))


def predict_elo_win_probability(
    home_rating: float,
    away_rating: float,
    home_advantage: float = 100.0,
) -> float:
    """Predict the home win probability using Elo ratings."""
    return elo_expected_score(home_rating + home_advantage, away_rating)


def _elo_ratings_to_series(elo_ratings):
    if isinstance(elo_ratings, pd.DataFrame):
        if "team" in elo_ratings.columns and "elo_rating" in elo_ratings.columns:
            return elo_ratings.set_index("team")["elo_rating"]
        raise ValueError("Elo ratings DataFrame must contain 'team' and 'elo_rating' columns")
    if isinstance(elo_ratings, dict):
        return pd.Series(elo_ratings)
    if isinstance(elo_ratings, pd.Series):
        return elo_ratings
    raise TypeError("elo_ratings must be a pandas Series, dict, or DataFrame")


def predict_elo_match_probabilities(
    home_team: str,
    away_team: str,
    elo_ratings,
    home_advantage: float = 100.0,
) -> Dict[str, float]:
    """Predict the probabilities of home win, draw, and away win using Elo."""
    ratings = _elo_ratings_to_series(elo_ratings)
    if home_team not in ratings or away_team not in ratings:
        raise KeyError("Both teams must exist in elo_ratings")

    home_rating = float(ratings[home_team])
    away_rating = float(ratings[away_team])
    expected_home = elo_expected_score(home_rating + home_advantage, away_rating)
    diff = abs((home_rating + home_advantage) - away_rating)
    draw_prob = max(0.08, min(0.35, 0.35 - 0.10 * (diff / 100.0)))
    home_win = expected_home * (1.0 - draw_prob)
    away_win = (1.0 - expected_home) * (1.0 - draw_prob)

    return {"home_win": home_win, "draw": draw_prob, "away_win": away_win}


def fit_poisson_attack_defense(results: pd.DataFrame) -> pd.DataFrame:
    """Estimate attack and defense strength for each team from match results."""
    results = results.copy()
    home_goals = results.groupby("home_team")["home_score"].mean().rename("attack")
    away_goals = results.groupby("away_team")["away_score"].mean().rename("attack")
    home_concede = results.groupby("home_team")["away_score"].mean().rename("defense")
    away_concede = results.groupby("away_team")["home_score"].mean().rename("defense")

    strengths = pd.DataFrame(index=home_goals.index.union(away_goals.index))
    strengths["attack"] = (home_goals.reindex(strengths.index).fillna(0) + away_goals.reindex(strengths.index).fillna(0)) / 2
    strengths["defense"] = (home_concede.reindex(strengths.index).fillna(0) + away_concede.reindex(strengths.index).fillna(0)) / 2

    strengths["attack"] = strengths["attack"] / strengths["attack"].mean()
    strengths["defense"] = strengths["defense"].mean() / strengths["defense"]

    return strengths


def predict_poisson_scores(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    base_home_goals: float = 1.3,
    base_away_goals: float = 1.1,
    elo_ratings=None,
    home_advantage: float = 100.0,
) -> Tuple[float, float]:
    """Return expected home and away goal totals from the Poisson model."""
    if elo_ratings is not None:
        ratings = _elo_ratings_to_series(elo_ratings)
        if home_team not in ratings or away_team not in ratings:
            raise KeyError("Both teams must exist in elo_ratings")

        home_rating = float(ratings[home_team])
        away_rating = float(ratings[away_team])
        diff = (home_rating + home_advantage) - away_rating
        expected_margin = 0.4 * np.tanh(diff / 200.0)
        expected_home = max(0.15, base_home_goals + expected_margin / 2.0)
        expected_away = max(0.15, base_away_goals - expected_margin / 2.0)
        return expected_home, expected_away

    if home_team not in strengths.index or away_team not in strengths.index:
        raise KeyError("Both teams must exist in the strength table")

    home_attack = float(strengths.loc[home_team, "attack"])
    home_defense = float(strengths.loc[home_team, "defense"])
    away_attack = float(strengths.loc[away_team, "attack"])
    away_defense = float(strengths.loc[away_team, "defense"])
    # Interpret `defense` as a factor that reduces expected opponent goals.
    # A stronger defense (larger `defense` after normalization) should lower
    # the expected goals conceded, so divide by the opponent's defense.
    expected_home = base_home_goals * home_attack / away_defense
    expected_away = base_away_goals * away_attack / home_defense
    return expected_home, expected_away


def simulate_match(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    n_simulations: int = 1000,
    elo_ratings=None,
    home_advantage: float = 100.0,
) -> pd.DataFrame:
    """Simulate a match result distribution using Poisson goals."""
    expected_home, expected_away = predict_poisson_scores(
        home_team,
        away_team,
        strengths,
        elo_ratings=elo_ratings,
        home_advantage=home_advantage,
    )
    home_goals = np.random.poisson(expected_home, size=n_simulations)
    away_goals = np.random.poisson(expected_away, size=n_simulations)
    return pd.DataFrame({"home_goals": home_goals, "away_goals": away_goals})
