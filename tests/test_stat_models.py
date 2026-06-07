import pandas as pd
import pytest

from world_cup_predictor.stat_models import (
    apply_confederation_rating_offset,
    elo_expected_score,
    fit_elo_ratings,
    fit_poisson_attack_defense,
    predict_elo_match_probabilities,
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


def test_predict_elo_match_probabilities_sums_to_one():
    probs = predict_elo_match_probabilities(
        "Spain",
        "Japan",
        {"Spain": 1600.0, "Japan": 1500.0},
    )
    assert pytest.approx(sum(probs.values()), rel=1e-6) == 1.0
    assert all(0.0 <= v <= 1.0 for v in probs.values())


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


def test_predict_poisson_scores_with_elo_returns_expected_tuple():
    strengths = pd.DataFrame(
        {
            "attack": [1.0, 1.0],
            "defense": [1.0, 1.0],
        },
        index=["Spain", "Japan"],
    )

    home, away = predict_poisson_scores(
        "Spain",
        "Japan",
        strengths,
        elo_ratings={"Spain": 1600.0, "Japan": 1500.0},
    )
    assert home > 0
    assert away > 0
    assert isinstance(home, float)
    assert isinstance(away, float)


def test_apply_confederation_rating_offset_only_affects_qualified_conmebol_teams():
    ratings = {"Brazil": 1600.0, "England": 1550.0, "Japan": 1500.0}
    ranking = pd.DataFrame(
        {
            "country_full": ["Brazil", "England", "Japan"],
            "confederation": ["CONMEBOL", "UEFA", "AFC"],
        }
    )

    adjusted = apply_confederation_rating_offset(
        ratings,
        ranking,
        confederation="CONMEBOL",
        offset=-20.0,
        eligible_teams=["Brazil", "Japan"],
    )

    assert adjusted["Brazil"] == 1580.0
    assert adjusted["England"] == 1550.0
    assert adjusted["Japan"] == 1500.0


def test_apply_confederation_rating_offset_falls_back_without_confederation_column():
    ratings = {"Argentina": 1900.0, "Spain": 1880.0}
    ranking = pd.DataFrame(
        {
            "country_full": ["Argentina", "Spain"],
            "rank": [1, 2],
            "total_points": [1874.81, 1876.40],
        }
    )

    adjusted = apply_confederation_rating_offset(
        ratings,
        ranking,
        confederation="CONMEBOL",
        offset=-80.0,
        eligible_teams=["Argentina"],
    )

    assert adjusted["Argentina"] == 1820.0
    assert adjusted["Spain"] == 1880.0
