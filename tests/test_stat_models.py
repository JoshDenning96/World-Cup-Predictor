import pandas as pd

from world_cup_predictor.stat_models import (
    elo_expected_score,
    fit_elo_ratings,
    fit_poisson_attack_defense,
    predict_elo_win_probability,
    predict_poisson_scores,
)


def test_fit_elo_ratings_returns_team_ratings():
    results = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "home_score": [2, 1],
            "away_score": [1, 2],
        }
    )

    ratings = fit_elo_ratings(results)

    assert "Spain" in ratings
    assert "Japan" in ratings
    assert isinstance(ratings["Spain"], float)


def test_predict_elo_win_probability_is_between_zero_and_one():
    p = predict_elo_win_probability(1600, 1500)
    assert 0.0 < p < 1.0


def test_fit_poisson_attack_defense_returns_strengths():
    results = pd.DataFrame(
        {
            "home_team": ["Spain", "Japan"],
            "away_team": ["Japan", "Spain"],
            "home_score": [2, 1],
            "away_score": [1, 2],
        }
    )

    strengths = fit_poisson_attack_defense(results)
    assert "Spain" in strengths.index
    assert "Japan" in strengths.index
    assert strengths.loc["Spain", "attack"] > 0


def test_predict_poisson_scores_returns_expected_tuple():
    strengths = pd.DataFrame(
        {
            "attack": [1.0, 1.0],
            "defense": [1.0, 1.0],
        },
        index=["Spain", "Japan"],
    )

    home, away = predict_poisson_scores("Spain", "Japan", strengths)
    assert home > 0
    assert away > 0
    assert isinstance(home, float)
    assert isinstance(away, float)
