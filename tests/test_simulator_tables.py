import numpy as np
import pandas as pd

from world_cup_predictor.simulator import simulate_group_tables


def make_round_robin_group(group_name: str, teams: list) -> pd.DataFrame:
    matches = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            matches.append({"group": group_name, "home_team": teams[i], "away_team": teams[j]})
    return pd.DataFrame(matches)


def test_simulate_group_tables_stronger_team_finishes_higher():
    # deterministic randomness for the test
    np.random.seed(0)

    teams = ["Alpha", "Bravo", "Charlie", "Delta"]
    schedule = make_round_robin_group("G1", teams)

    # strengths: Alpha is much stronger, Delta is weakest
    strengths = pd.DataFrame(
        {
            "attack": [3.0, 1.0, 1.0, 0.5],
            "defense": [0.5, 1.0, 1.0, 2.0],
        },
        index=teams,
    )

    tables = simulate_group_tables(schedule, strengths, n_simulations=200)

    group_tables = tables[tables["group"] == "G1"].set_index("team")

    # each team should have probabilities for 4 positions
    prob_cols = [c for c in group_tables.columns if c.startswith("prob_")]
    assert len(prob_cols) == 4

    # probabilities across positions for each team should sum to ~1
    for team in teams:
        s = group_tables.loc[team, prob_cols].astype(float).sum()
        assert abs(s - 1.0) < 1e-6

    # Alpha should have highest probability to finish 1st and lowest expected_rank
    first_probs = group_tables["prob_1"]
    expected_ranks = group_tables["expected_rank"]
    assert first_probs["Alpha"] == max(first_probs)
    assert expected_ranks["Alpha"] == min(expected_ranks)
