import pandas as pd
import pytest

from world_cup_predictor.simulator import (
    aggregate_group_standings,
    calculate_match_probabilities,
    simulate_group_stage,
    simulate_knockout_match,
)


def test_calculate_match_probabilities_sums_to_one():
    strengths = pd.DataFrame(
        {
            "attack": [1.0, 1.0],
            "defense": [1.0, 1.0],
        },
        index=["Spain", "Japan"],
    )

    probs = calculate_match_probabilities("Spain", "Japan", strengths)
    assert pytest.approx(sum(probs.values()), rel=1e-6) == 1.0
    assert all(0.0 <= val <= 1.0 for val in probs.values())


def test_aggregate_group_standings_computes_points_and_goal_difference():
    results = pd.DataFrame(
        {
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_score": [2, 1],
            "away_score": [0, 1],
        }
    )

    standings = aggregate_group_standings(results)
    assert standings.loc["A", "points"] == 4
    assert standings.loc["A", "goal_difference"] == 2
    assert standings.loc["B", "points"] == 1


def test_simulate_group_stage_returns_probability_dataframe():
    schedule = pd.DataFrame(
        {
            "group": ["A", "A"],
            "home_team": ["A", "C"],
            "away_team": ["B", "D"],
        }
    )
    strengths = pd.DataFrame(
        {
            "attack": [1.0, 1.0, 1.0, 1.0],
            "defense": [1.0, 1.0, 1.0, 1.0],
        },
        index=["A", "B", "C", "D"],
    )

    probabilities = simulate_group_stage(schedule, strengths, n_simulations=10)
    assert set(probabilities.columns) == {"team", "advance_probability"}
    assert len(probabilities) == 4
    assert probabilities["advance_probability"].between(0, 1).all()


def test_simulate_knockout_match_returns_probabilities():
    strengths = pd.DataFrame(
        {
            "attack": [1.0, 1.0],
            "defense": [1.0, 1.0],
        },
        index=["Spain", "Japan"],
    )

    winner_probs = simulate_knockout_match("Spain", "Japan", strengths, n_simulations=10)
    assert "result" in winner_probs.columns
    assert "probability" in winner_probs.columns
    assert winner_probs["probability"].between(0, 1).all()
