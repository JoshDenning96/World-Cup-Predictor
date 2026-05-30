"""Statistical match models for the World Cup Predictor."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, PoissonRegressor


def _default_tournament_weights() -> dict[str, float]:
    return {
        "World Cup": 4.0,
        "Friendly": 0.5,
        "Qualification": 2.0,
        "Euro": 3.0,
        "Copa America": 3.0,
        "Nations League": 2.0,
        "Gold Cup": 2.0,
        "African Cup": 2.5,
        "Asian Cup": 2.5,
        "CONCACAF": 2.0,
        "CAF": 2.0,
        "AFC": 2.0,
        "CONMEBOL": 2.0,
        "UEFA": 2.0,
    }


def fit_elo_ratings(
    results: pd.DataFrame,
    initial_rating: float = 1500.0,
    k: float = 20.0,
    home_advantage: float = 100.0,
    tournament_weights: dict[str, float] | None = None,
    date_decay_half_life_days: float = 365.0,
) -> Dict[str, float]:
    """Fit simple Elo ratings from historical match results.

    The function updates ratings sequentially by match date.
    It returns the final rating for each team.
    """
    ratings: Dict[str, float] = {}
    results = results.copy()
    if "date" in results.columns:
        results["date"] = pd.to_datetime(results["date"], errors="coerce")
        results = results.sort_values("date")

    if tournament_weights is None:
        tournament_weights = _default_tournament_weights()

    now = results["date"].max() if "date" in results.columns else None

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

        weight = 1.0
        if "tournament" in row and pd.notna(row["tournament"]):
            weight = tournament_weights.get(str(row["tournament"]).strip(), 1.0)
        if now is not None and pd.notna(row["date"]):
            age_days = (now - row["date"]).days
            weight *= 2 ** (-age_days / date_decay_half_life_days)

        k_effective = k * weight
        ratings[home] += k_effective * (actual_home - expected_home)
        ratings[away] += k_effective * (actual_away - expected_away)

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
    draw_probability_model=None,
) -> Dict[str, float]:
    """Predict the probabilities of home win, draw, and away win using Elo."""
    ratings = _elo_ratings_to_series(elo_ratings)
    if home_team not in ratings or away_team not in ratings:
        raise KeyError("Both teams must exist in elo_ratings")

    home_rating = float(ratings[home_team])
    away_rating = float(ratings[away_team])
    expected_home = elo_expected_score(home_rating + home_advantage, away_rating)
    diff = abs((home_rating + home_advantage) - away_rating)

    if draw_probability_model is not None:
        draw_prob = float(
            draw_probability_model.predict_proba([[diff]])[0][1]
        )
        draw_prob = max(0.01, min(0.45, draw_prob))
    else:
        draw_prob = max(0.08, min(0.35, 0.35 - 0.10 * (diff / 100.0)))

    home_win = expected_home * (1.0 - draw_prob)
    away_win = (1.0 - expected_home) * (1.0 - draw_prob)

    return {"home_win": home_win, "draw": draw_prob, "away_win": away_win}


def fit_draw_probability_model(
    results: pd.DataFrame,
    elo_ratings,
    home_advantage: float = 100.0,
) -> LogisticRegression | None:
    """Fit a draw probability model using Elo rating difference."""
    ratings = _elo_ratings_to_series(elo_ratings)
    if "date" in results.columns:
        results = results.copy()
        results["date"] = pd.to_datetime(results["date"], errors="coerce")

    features = []
    targets = []
    for _, row in results.iterrows():
        home_team = row["home_team"]
        away_team = row["away_team"]
        if home_team not in ratings or away_team not in ratings:
            continue
        home_rating = float(ratings[home_team]) + home_advantage
        away_rating = float(ratings[away_team])
        diff = abs(home_rating - away_rating)
        is_draw = 1 if float(row["home_score"]) == float(row["away_score"]) else 0
        features.append([diff])
        targets.append(is_draw)

    if len(set(targets)) < 2:
        return None

    model = LogisticRegression(solver="lbfgs", max_iter=1000)
    model.fit(features, targets)
    return model


def fit_poisson_goal_models(
    results: pd.DataFrame,
    strengths: pd.DataFrame | None = None,
    elo_ratings=None,
    home_advantage: float = 100.0,
) -> dict[str, PoissonRegressor] | None:
    """Fit Poisson goal models for home and away goal totals."""
    if strengths is None:
        strengths = fit_poisson_attack_defense(results)

    ratings = None
    if elo_ratings is not None:
        ratings = _elo_ratings_to_series(elo_ratings)

    X_home = []
    y_home = []
    X_away = []
    y_away = []

    for _, row in results.iterrows():
        home = row["home_team"]
        away = row["away_team"]
        if home not in strengths.index or away not in strengths.index:
            continue

        home_attack = float(strengths.loc[home, "attack"])
        away_defense = float(strengths.loc[away, "defense"])
        away_attack = float(strengths.loc[away, "attack"])
        home_defense = float(strengths.loc[home, "defense"])
        diff = 0.0
        if ratings is not None and home in ratings and away in ratings:
            diff = float(ratings[home] + home_advantage - ratings[away])

        X_home.append([home_attack, away_defense, diff])
        y_home.append(float(row["home_score"]))
        X_away.append([away_attack, home_defense, -diff])
        y_away.append(float(row["away_score"]))

    if not X_home or not X_away:
        return None

    home_model = PoissonRegressor(alpha=0.0, max_iter=300)
    away_model = PoissonRegressor(alpha=0.0, max_iter=300)
    home_model.fit(X_home, y_home)
    away_model.fit(X_away, y_away)

    return {"home": home_model, "away": away_model}

    return {"home": home_model, "away": away_model}


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
    poisson_goal_models: dict[str, PoissonRegressor] | None = None,
) -> Tuple[float, float]:
    """Return expected home and away goal totals from the Poisson model."""
    if home_team not in strengths.index or away_team not in strengths.index:
        raise KeyError("Both teams must exist in the strength table")

    home_attack = float(strengths.loc[home_team, "attack"])
    home_defense = float(strengths.loc[home_team, "defense"])
    away_attack = float(strengths.loc[away_team, "attack"])
    away_defense = float(strengths.loc[away_team, "defense"])

    diff = 0.0
    if elo_ratings is not None:
        ratings = _elo_ratings_to_series(elo_ratings)
        if home_team not in ratings or away_team not in ratings:
            raise KeyError("Both teams must exist in elo_ratings")
        home_rating = float(ratings[home_team])
        away_rating = float(ratings[away_team])
        diff = (home_rating + home_advantage) - away_rating

    if poisson_goal_models is not None and "home" in poisson_goal_models and "away" in poisson_goal_models:
        home_model = poisson_goal_models["home"]
        away_model = poisson_goal_models["away"]
        expected_home = np.asarray(home_model.predict([[home_attack, away_defense, diff]])).item()
        expected_away = np.asarray(away_model.predict([[away_attack, home_defense, -diff]])).item()
        return max(0.05, expected_home), max(0.05, expected_away)

    if elo_ratings is not None:
        expected_margin = 0.4 * np.tanh(diff / 200.0)
        expected_home = max(0.15, base_home_goals * home_attack / away_defense + expected_margin / 2.0)
        expected_away = max(0.15, base_away_goals * away_attack / home_defense - expected_margin / 2.0)
        return expected_home, expected_away

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
    poisson_goal_models: dict[str, PoissonRegressor] | None = None,
) -> pd.DataFrame:
    """Simulate a match result distribution using Poisson goals."""
    expected_home, expected_away = predict_poisson_scores(
        home_team,
        away_team,
        strengths,
        elo_ratings=elo_ratings,
        home_advantage=home_advantage,
        poisson_goal_models=poisson_goal_models,
    )
    home_goals = np.random.poisson(expected_home, size=n_simulations)
    away_goals = np.random.poisson(expected_away, size=n_simulations)
    return pd.DataFrame({"home_goals": home_goals, "away_goals": away_goals})
