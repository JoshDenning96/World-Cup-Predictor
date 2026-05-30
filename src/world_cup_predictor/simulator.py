"""Tournament simulation utilities for the World Cup Predictor."""
from __future__ import annotations

from typing import Dict
from collections import defaultdict
import math

import numpy as np
import pandas as pd
import warnings

from .stat_models import predict_elo_match_probabilities, predict_poisson_scores, simulate_match
import re

_R32_WINNER_GROUP_ORDER = ["A", "B", "D", "E", "G", "I", "K", "L"]

def _parse_third_place_assignment_text(text: str) -> dict[str, list[str]]:
    mapping = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("No.") or line.startswith("Third-placed"):
            continue
        tokens = line.split()
        if len(tokens) < 10 or not all(tok.startswith("3") for tok in tokens[-8:]):
            continue
        group_tokens = "".join(tokens[1:-8]).replace(" ", "")
        group_key = "".join(sorted(group_tokens))
        mapping[group_key] = [tok[1:] for tok in tokens[-8:]]
    return mapping

_THIRD_PLACE_ASSIGNMENT_TABLE_TEXT = """
1 EFGHIJKL 3E 3J 3I 3F 3H 3G 3L 3K
2 D FGHIJKL 3H 3G 3I 3D 3J 3F 3L 3K
3 DE GHIJKL 3E 3J 3I 3D 3H 3G 3L 3K
4 DEF HIJKL 3E 3J 3I 3D 3H 3F 3L 3K
5 DEFG IJKL 3E 3G 3I 3D 3J 3F 3L 3K
6 DEFGH JKL 3E 3G 3J 3D 3H 3F 3L 3K
7 DEFGHI KL 3E 3G 3I 3D 3H 3F 3L 3K
8 DEFGHIJ L 3E 3G 3J 3D 3H 3F 3L 3I
9 DEFGHIJK 3E 3G 3J 3D 3H 3F 3I 3K
10 C FGHIJKL 3H 3G 3I 3C 3J 3F 3L 3K
11 C E GHIJKL 3E 3J 3I 3C 3H 3G 3L 3K
12 C EF HIJKL 3E 3J 3I 3C 3H 3F 3L 3K
13 C EFG IJKL 3E 3G 3I 3C 3J 3F 3L 3K
14 C EFGH JKL 3E 3G 3J 3C 3H 3F 3L 3K
15 C EFGHI KL 3E 3G 3I 3C 3H 3F 3L 3K
16 C EFGHIJ L 3E 3G 3J 3C 3H 3F 3L 3I
17 C EFGHIJK 3E 3G 3J 3C 3H 3F 3I 3K
18 CD GHIJKL 3H 3G 3I 3C 3J 3D 3L 3K
19 CD F HIJKL 3C 3J 3I 3D 3H 3F 3L 3K
20 CD FG IJKL 3C 3G 3I 3D 3J 3F 3L 3K
21 CD FGH JKL 3C 3G 3J 3D 3H 3F 3L 3K
22 CD FGHI KL 3C 3G 3I 3D 3H 3F 3L 3K
23 CD FGHIJ L 3C 3G 3J 3D 3H 3F 3L 3I
24 CD FGHIJK 3C 3G 3J 3D 3H 3F 3I 3K
25 CDE HIJKL 3E 3J 3I 3C 3H 3D 3L 3K
26 CDE G IJKL 3E 3G 3I 3C 3J 3D 3L 3K
27 CDE GH JKL 3E 3G 3J 3C 3H 3D 3L 3K
28 CDE GHI KL 3E 3G 3I 3C 3H 3D 3L 3K
29 CDE GHIJ L 3E 3G 3J 3C 3H 3D 3L 3I
30 CDE GHIJK 3E 3G 3J 3C 3H 3D 3I 3K
31 CDEF IJKL 3C 3J 3E 3D 3I 3F 3L 3K
32 CDEF H JKL 3C 3J 3E 3D 3H 3F 3L 3K
33 CDEF HI KL 3C 3E 3I 3D 3H 3F 3L 3K
34 CDEF HIJ L 3C 3J 3E 3D 3H 3F 3L 3I
36 CDEFG JKL 3C 3G 3E 3D 3J 3F 3L 3K
37 CDEFG I KL 3C 3G 3E 3D 3I 3F 3L 3K
38 CDEFG IJ L 3C 3G 3E 3D 3J 3F 3L 3I
39 CDEFG IJK 3C 3G 3E 3D 3J 3F 3I 3K
40 CDEFGH KL 3C 3G 3E 3D 3H 3F 3L 3K
41 CDEFGH J L 3C 3G 3J 3D 3H 3F 3L 3E
42 CDEFGH JK 3C 3G 3J 3D 3H 3F 3E 3K
43 CDEFGHI L 3C 3G 3E 3D 3H 3F 3L 3I
44 CDEFGHI K 3C 3G 3E 3D 3H 3F 3I 3K
45 CDEFGHIJ 3C 3G 3J 3D 3H 3F 3E 3I
46 B FGHIJKL 3H 3J 3B 3F 3I 3G 3L 3K
47 B E GHIJKL 3E 3J 3I 3B 3H 3G 3L 3K
48 B EF HIJKL 3E 3J 3B 3F 3I 3H 3L 3K
49 B EFG IJKL 3E 3J 3B 3F 3I 3G 3L 3K
50 B EFGH JKL 3E 3J 3B 3F 3H 3G 3L 3K
51 B EFGHI KL 3E 3G 3B 3F 3I 3H 3L 3K
52 B EFGHIJ L 3E 3J 3B 3F 3H 3G 3L 3I
53 B EFGHIJK 3E 3J 3B 3F 3H 3G 3I 3K
54 B D GHIJKL 3H 3J 3B 3D 3I 3G 3L 3K
55 B D F HIJKL 3H 3J 3B 3D 3I 3F 3L 3K
56 B D FG IJKL 3I 3G 3B 3D 3J 3F 3L 3K
57 B D FGH JKL 3H 3G 3B 3D 3J 3F 3L 3K
58 B D FGHI KL 3H 3G 3B 3D 3I 3F 3L 3K
59 B D FGHIJ L 3H 3G 3B 3D 3J 3F 3L 3I
60 B D FGHIJK 3H 3G 3B 3D 3J 3F 3I 3K
61 B DE HIJKL 3E 3J 3B 3D 3I 3H 3L 3K
62 B DE G IJKL 3E 3J 3B 3D 3I 3G 3L 3K
63 B DE GH JKL 3E 3J 3B 3D 3H 3G 3L 3K
64 B DE GHI KL 3E 3G 3B 3D 3I 3H 3L 3K
65 B DE GHIJ L 3E 3J 3B 3D 3H 3G 3L 3I
66 B DE GHIJK 3E 3J 3B 3D 3H 3G 3I 3K
67 B DEF IJKL 3E 3J 3B 3D 3I 3F 3L 3K
68 B DEF H JKL 3E 3J 3B 3D 3H 3F 3L 3K
69 B DEF HI KL 3E 3I 3B 3D 3H 3F 3L 3K
70 B DEF HIJ L 3E 3J 3B 3D 3H 3F 3L 3I
71 B DEF HIJK 3E 3J 3B 3D 3H 3F 3I 3K
72 B DEFG JKL 3E 3G 3B 3D 3J 3F 3L 3K
73 B DEFG I KL 3E 3G 3B 3D 3I 3F 3L 3K
74 B DEFG IJ L 3E 3G 3B 3D 3J 3F 3L 3I
75 B DEFG IJK 3E 3G 3B 3D 3J 3F 3I 3K
76 B DEFGH KL 3E 3G 3B 3D 3H 3F 3L 3K
77 B DEFGH J L 3H 3G 3B 3D 3J 3F 3L 3E
78 B DEFGH JK 3H 3G 3B 3D 3J 3F 3E 3K
79 B DEFGHI L 3E 3G 3B 3D 3H 3F 3L 3I
80 B DEFGHI K 3E 3G 3B 3D 3H 3F 3I 3K
81 B DEFGHIJ 3H 3G 3B 3D 3J 3F 3E 3I
82 BC GHIJKL 3H 3J 3B 3C 3I 3G 3L 3K
83 BC F HIJKL 3H 3J 3B 3C 3I 3F 3L 3K
84 BC FG IJKL 3I 3G 3B 3C 3J 3F 3L 3K
85 BC FGH JKL 3H 3G 3B 3C 3J 3F 3L 3K
86 BC FGHI KL 3H 3G 3B 3C 3I 3F 3L 3K
87 BC FGHIJ L 3H 3G 3B 3C 3J 3F 3L 3I
88 BC FGHIJK 3H 3G 3B 3C 3J 3F 3I 3K
89 BC E HIJKL 3E 3J 3B 3C 3I 3H 3L 3K
90 BC E G IJKL 3E 3J 3B 3C 3I 3G 3L 3K
91 BC E GH JKL 3E 3J 3B 3C 3H 3G 3L 3K
92 BC E GHI KL 3E 3G 3B 3C 3I 3H 3L 3K
93 BC E GHIJ L 3E 3J 3B 3C 3H 3G 3L 3I
94 BC E GHIJK 3E 3J 3B 3C 3H 3G 3I 3K
95 BC EF IJKL 3E 3J 3B 3C 3I 3F 3L 3K
96 BC EF H JKL 3E 3J 3B 3C 3H 3F 3L 3K
97 BC EF HI KL 3E 3I 3B 3C 3H 3F 3L 3K
98 BC EF HIJ L 3E 3J 3B 3C 3H 3F 3L 3I
99 BC EF HIJK 3E 3J 3B 3C 3H 3F 3I 3K
100 BC EFG JKL 3E 3G 3B 3C 3J 3F 3L 3K
101 BC EFG I KL 3E 3G 3B 3C 3I 3F 3L 3K
102 BC EFG IJ L 3E 3G 3B 3C 3J 3F 3L 3I
103 BC EFG IJK 3E 3G 3B 3C 3J 3F 3I 3K
104 BC EFGH KL 3E 3G 3B 3C 3H 3F 3L 3K
105 BC EFGH J L 3H 3G 3B 3C 3J 3F 3L 3E
106 BC EFGH JK 3H 3G 3B 3C 3J 3F 3E 3K
107 BC EFGHI L 3E 3G 3B 3C 3H 3F 3L 3I
108 BC EFGHI K 3E 3G 3B 3C 3H 3F 3I 3K
109 BC EFGHIJ 3H 3G 3B 3C 3J 3F 3E 3I
110 BCD HIJKL 3H 3J 3B 3C 3I 3D 3L 3K
111 BCD G IJKL 3I 3G 3B 3D 3J 3D 3L 3K
112 BCD GH JKL 3H 3G 3B 3D 3J 3F 3L 3K
113 BCD GHI KL 3H 3G 3B 3D 3I 3D 3L 3K
114 BCD GHIJ L 3H 3G 3B 3D 3J 3D 3L 3I
115 BCD GHIJK 3H 3G 3B 3D 3J 3D 3I 3K
116 BCD F IJKL 3C 3J 3B 3D 3I 3F 3L 3K
117 BCD F H JKL 3C 3J 3B 3D 3H 3F 3L 3K
118 BCD F HI KL 3C 3I 3B 3D 3H 3F 3L 3K
119 BCD F HIJ L 3C 3J 3B 3D 3H 3F 3L 3I
120 BCD F HIJK 3C 3J 3B 3D 3H 3F 3I 3K
121 BCD FG JKL 3C 3G 3B 3D 3J 3F 3L 3K
122 BCD FG I KL 3C 3G 3B 3D 3I 3F 3L 3K
123 BCD FG IJ L 3C 3G 3B 3D 3J 3F 3L 3I
124 BCD FG IJK 3C 3G 3B 3D 3J 3F 3I 3K
125 BCD FGH KL 3C 3G 3B 3D 3H 3F 3L 3K
126 BCD FGH J L 3C 3G 3B 3D 3H 3F 3L 3J
127 BCD FGH JK 3H 3G 3B 3C 3J 3F 3D 3K
128 BCD FGHI L 3C 3G 3B 3D 3H 3F 3L 3I
129 BCD FGHI K 3C 3G 3B 3D 3H 3F 3I 3K
130 BCD FGHIJ 3H 3G 3B 3C 3J 3F 3D 3I
131 BCDE IJKL 3E 3J 3B 3C 3I 3D 3L 3K
132 BCDE H JKL 3E 3J 3B 3C 3H 3D 3L 3K
133 BCDE HI KL 3E 3I 3B 3C 3H 3D 3L 3K
134 BCDE HIJ L 3E 3J 3B 3C 3H 3D 3L 3I
135 BCDE HIJK 3E 3J 3B 3C 3H 3D 3I 3K
136 BCDE G JKL 3E 3G 3B 3C 3J 3F 3L 3K
137 BCDE G I KL 3E 3G 3B 3C 3I 3D 3L 3K
138 BCDE G IJ L 3E 3G 3B 3C 3J 3D 3L 3I
139 BCDE G IJK 3E 3G 3B 3C 3J 3D 3I 3K
140 BCDE GH KL 3E 3G 3B 3C 3H 3D 3L 3K
141 BCDE GH J L 3H 3G 3B 3C 3J 3D 3L 3E
142 BCDE GH JK 3H 3G 3B 3C 3J 3D 3E 3K
143 BCDE GHI L 3E 3G 3B 3C 3H 3D 3L 3I
144 BCDE GHI K 3E 3G 3B 3C 3H 3D 3I 3K
145 BCDE GHIJ 3H 3G 3B 3C 3J 3D 3E 3I
146 BCDEF JKL 3C 3J 3B 3D 3E 3F 3L 3K
147 BCDEF I KL 3C 3E 3B 3D 3I 3F 3L 3K
148 BCDEF IJ L 3C 3J 3B 3D 3E 3F 3L 3I
149 BCDEF IJK 3C 3J 3B 3D 3E 3F 3I 3K
150 BCDEF H KL 3C 3E 3B 3D 3H 3F 3L 3K
151 BCDEF H J L 3C 3J 3B 3D 3H 3F 3L 3E
152 BCDEF H JK 3C 3J 3B 3D 3H 3F 3E 3K
153 BCDEF HI L 3C 3E 3B 3D 3H 3F 3L 3I
154 BCDEF HI K 3C 3E 3B 3D 3H 3F 3I 3K
155 BCDEF HIJ 3C 3J 3B 3D 3H 3F 3E 3I
156 BCDEFG KL 3C 3G 3B 3D 3E 3F 3L 3K
157 BCDEFG J L 3C 3G 3B 3D 3J 3F 3L 3E
158 BCDEFG JK 3C 3G 3B 3D 3J 3F 3E 3K
159 BCDEFG I L 3C 3G 3B 3D 3E 3F 3L 3I
160 BCDEFG I K 3C 3G 3B 3D 3E 3F 3I 3K
161 BCDEFG IJ 3C 3G 3B 3D 3J 3F 3E 3I
162 BCDEFGH L 3C 3G 3B 3D 3H 3F 3L 3E
163 BCDEFGH K 3C 3G 3B 3D 3H 3F 3E 3K
164 BCDEFGH J 3H 3G 3B 3C 3J 3F 3D 3E
165 BCDEFGHI 3C 3G 3B 3D 3H 3F 3E 3I
"""

ROUND_OF_32_THIRD_PLACE_ASSIGNMENT_MAP = _parse_third_place_assignment_text(
    _THIRD_PLACE_ASSIGNMENT_TABLE_TEXT
)


def _normalize_group_letter(letter: str, groups) -> str | None:
    letter = str(letter).strip()
    if not letter:
        return None
    if letter in groups:
        return letter
    group_name = f"Group {letter}"
    if group_name in groups:
        return group_name
    for group in groups:
        if str(group).strip().endswith(letter):
            return group
    return None


def _build_round_of_32_third_place_assignment_map(
    standings_by_group: dict,
) -> dict[str, str] | None:
    third_place_rows = []
    for group, standings in standings_by_group.items():
        if len(standings.index) < 3:
            continue
        third_team = standings.index[2]
        stats = standings.loc[third_team, ["points", "goal_difference", "goals_for"]].tolist()
        third_place_rows.append((group, third_team, stats))

    if len(third_place_rows) < 8:
        return None

    third_place_rows.sort(key=lambda x: (-x[2][0], -x[2][1], -x[2][2], x[0]))
    best_third_groups = [str(group).replace("Group ", "").strip() for group, _, _ in third_place_rows[:8]]
    group_key = "".join(sorted(best_third_groups))
    assignment = ROUND_OF_32_THIRD_PLACE_ASSIGNMENT_MAP.get(group_key)
    if assignment is None:
        return None

    return dict(zip(_R32_WINNER_GROUP_ORDER, assignment))


def _resolve_group_placement(slot: str, standings_by_group: dict, position: int) -> str | None:
    match = re.match(r"([12])([A-Z])$", str(slot).strip())
    if not match:
        return None
    pos = int(match.group(1))
    letter = match.group(2)
    group_key = _normalize_group_letter(letter, standings_by_group.keys())
    if group_key and group_key in standings_by_group and len(standings_by_group[group_key].index) >= pos:
        return standings_by_group[group_key].index[pos - 1]
    return None


def _resolve_round_of_32_third_place(
    winner_slot: str,
    standings_by_group: dict,
    assignment_map: dict[str, str],
) -> str | None:
    match = re.match(r"^1([A-Z])$", str(winner_slot).strip())
    if not match:
        return None
    group_letter = match.group(1)
    third_group_letter = assignment_map.get(group_letter)
    if not third_group_letter:
        return None
    third_group_key = _normalize_group_letter(third_group_letter, standings_by_group.keys())
    if not third_group_key:
        return None
    standings = standings_by_group.get(third_group_key)
    if standings is None or len(standings.index) < 3:
        return None
    return standings.index[2]


def calculate_match_probabilities(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    elo_ratings=None,
    max_goals: int = 6,
) -> Dict[str, float]:
    """Compute win/draw probabilities for a single match."""
    if elo_ratings is not None:
        return predict_elo_match_probabilities(home_team, away_team, elo_ratings)

    expected_home, expected_away = predict_poisson_scores(home_team, away_team, strengths)
    home_probs = np.array([np.exp(-expected_home) * expected_home ** k / math.factorial(k) for k in range(max_goals + 1)])
    away_probs = np.array([np.exp(-expected_away) * expected_away ** k / math.factorial(k) for k in range(max_goals + 1)])

    matrix = np.outer(home_probs, away_probs)
    home_win = float(np.tril(matrix, -1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, 1).sum())

    total = home_win + draw + away_win
    if total <= 0:
        return {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}

    return {"home_win": home_win / total, "draw": draw / total, "away_win": away_win / total}


def aggregate_group_standings(results: pd.DataFrame) -> pd.DataFrame:
    """Compute group standings from played results."""
    results = results.copy()
    results["points_home"] = results.apply(
        lambda row: 3 if row["home_score"] > row["away_score"] else 1 if row["home_score"] == row["away_score"] else 0,
        axis=1,
    )
    results["points_away"] = results.apply(
        lambda row: 3 if row["away_score"] > row["home_score"] else 1 if row["away_score"] == row["home_score"] else 0,
        axis=1,
    )

    home_stats = results.groupby("home_team").agg(
        points=("points_home", "sum"),
        played=("home_score", "count"),
        goals_for=("home_score", "sum"),
        goals_against=("away_score", "sum"),
    )
    away_stats = results.groupby("away_team").agg(
        points=("points_away", "sum"),
        played=("away_score", "count"),
        goals_for=("away_score", "sum"),
        goals_against=("home_score", "sum"),
    )

    standings = home_stats.add(away_stats, fill_value=0)
    standings["goal_difference"] = standings["goals_for"] - standings["goals_against"]
    standings = standings.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])
    return standings.astype({"points": int, "played": int, "goals_for": int, "goals_against": int, "goal_difference": int})


def simulate_group_stage(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
    elo_ratings=None,
) -> pd.DataFrame:
    """Simulate a group stage and estimate advancement probabilities.

    If `elo_ratings` is provided, match outcomes are sampled using the Elo-based
    probability model via `simulate_match(..., elo_ratings=elo_ratings)`; otherwise
    the Poisson strengths-based model is used.
    """
    if "group" not in schedule.columns:
        raise KeyError("Schedule must include a 'group' column")

    schedule = schedule.copy()
    schedule = schedule.reset_index(drop=True)
    teams = sorted(set(schedule["home_team"]).union(schedule["away_team"]))
    advance_counts = {team: 0 for team in teams}

    for _ in range(n_simulations):
        all_results = []
        for _, match in schedule.iterrows():
            home_team = match["home_team"]
            away_team = match["away_team"]
            if home_team not in strengths.index or away_team not in strengths.index:
                warnings.warn(
                    f"Skipping match with missing strengths: {home_team} vs {away_team}",
                    UserWarning,
                )
                continue

            sim = simulate_match(home_team, away_team, strengths, n_simulations=1, elo_ratings=elo_ratings)
            home_goals = int(sim["home_goals"].iloc[0])
            away_goals = int(sim["away_goals"].iloc[0])
            all_results.append(
                {
                    "group": match["group"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_goals,
                    "away_score": away_goals,
                }
            )

        if not all_results:
            warnings.warn("No valid matches were simulated for this group stage.", UserWarning)
            continue

        results_df = pd.DataFrame(all_results)
        standings = aggregate_group_standings(results_df)

        for team in standings.index[:2]:
            advance_counts[team] += 1

    probabilities = pd.DataFrame(
        {"team": list(advance_counts.keys()), "advance_probability": [count / n_simulations for count in advance_counts.values()]}
    )
    return probabilities.sort_values("advance_probability", ascending=False).reset_index(drop=True)


def simulate_knockout_match(
    home_team: str,
    away_team: str,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
) -> pd.DataFrame:
    """Simulate a knockout match and return counts for each possible winner."""
    sim = simulate_match(home_team, away_team, strengths, n_simulations=n_simulations)
    outcomes = sim.apply(
        lambda row: "home" if row["home_goals"] > row["away_goals"] else "away" if row["away_goals"] > row["home_goals"] else "draw",
        axis=1,
    )
    return outcomes.value_counts(normalize=True).rename_axis("result").reset_index(name="probability")


def simulate_group_tables(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
    elo_ratings=None,
) -> pd.DataFrame:
    """Simulate group stage many times and return predicted group tables.

    Returns a DataFrame with one row per group/team containing:
    - probabilities of finishing in each position (prob_1, prob_2, ...)
    - `expected_rank`, `avg_points`, and `avg_goal_difference`.

    If `elo_ratings` is provided, match outcomes inside each simulation are
    sampled using the Elo model through `simulate_match(..., elo_ratings=elo_ratings)`.
    """
    if "group" not in schedule.columns:
        raise KeyError("Schedule must include a 'group' column")

    schedule = schedule.copy().reset_index(drop=True)

    # determine teams in each group
    groups = list(pd.unique(schedule["group"]))
    group_teams: Dict[str, list] = {}
    for g in groups:
        homes = set(schedule.loc[schedule["group"] == g, "home_team"]) 
        aways = set(schedule.loc[schedule["group"] == g, "away_team"])
        group_teams[g] = sorted(homes.union(aways))

    # initialize counters
    rank_counts = {g: {t: [0] * len(group_teams[g]) for t in group_teams[g]} for g in group_teams}
    pts_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}
    gd_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}

    for _ in range(n_simulations):
        all_results = []
        for _, match in schedule.iterrows():
            home_team = match["home_team"]
            away_team = match["away_team"]
            if home_team not in strengths.index or away_team not in strengths.index:
                warnings.warn(
                    f"Skipping match with missing strengths: {home_team} vs {away_team}",
                    UserWarning,
                )
                continue

            sim = simulate_match(home_team, away_team, strengths, n_simulations=1, elo_ratings=elo_ratings)
            home_goals = int(sim["home_goals"].iloc[0])
            away_goals = int(sim["away_goals"].iloc[0])
            all_results.append(
                {
                    "group": match["group"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_goals,
                    "away_score": away_goals,
                }
            )

        if not all_results:
            warnings.warn("No valid matches were simulated for this group stage.", UserWarning)
            continue

        results_df = pd.DataFrame(all_results)

        for g, teams in group_teams.items():
            gr = results_df[results_df["group"] == g]
            if gr.empty:
                # nothing simulated for this group in this iteration
                continue

            standings = aggregate_group_standings(gr)
            # ensure all teams are present without forcing alphabetical order
            for team in teams:
                if team not in standings.index:
                    standings.loc[team] = {
                        "points": 0,
                        "played": 0,
                        "goals_for": 0,
                        "goals_against": 0,
                        "goal_difference": 0,
                    }
            standings = standings.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])

            for pos, team in enumerate(standings.index.tolist(), start=1):
                rank_counts[g][team][pos - 1] += 1
                pts_sums[g][team] += int(standings.loc[team, "points"])
                gd_sums[g][team] += int(standings.loc[team, "goal_difference"])

    # assemble final DataFrame
    rows = []
    for g, teams in group_teams.items():
        n_teams = len(teams)
        for team in teams:
            counts = rank_counts[g][team]
            probs = [c / n_simulations for c in counts]
            expected_rank = sum((i + 1) * p for i, p in enumerate(probs))
            avg_points = pts_sums[g][team] / n_simulations
            avg_gd = gd_sums[g][team] / n_simulations

            row = {
                "group": g,
                "team": team,
                "expected_rank": expected_rank,
                "avg_points": avg_points,
                "avg_goal_difference": avg_gd,
            }

            for i, p in enumerate(probs, start=1):
                row[f"prob_{i}"] = p

            rows.append(row)

    out = pd.DataFrame(rows)
    out = out.sort_values(["group", "expected_rank"]) .reset_index(drop=True)
    return out


def simulate_full_tournament(
    schedule: pd.DataFrame,
    strengths: pd.DataFrame,
    n_simulations: int = 500,
    elo_ratings=None,
    return_group_tables: bool = False,
) -> pd.DataFrame | dict:
    """Simulate full tournament including knockout rounds.

    Returns a DataFrame with per-team probabilities for reaching each knockout
    stage and winning the tournament.
    """
    # prepare schedule
    if "group" not in schedule.columns and "round_number" not in schedule.columns:
        raise KeyError("Schedule must include 'group' or 'round_number' columns")

    sched = schedule.copy().reset_index(drop=True)
    # sort by date if available else by index
    if "date" in sched.columns:
        sched = sched.sort_values("date")

    # identify knockout round names in order of appearance
    knock_mask = sched["round_number"].astype(str).str.contains("Round|Quarter|Semi|Final", na=False)
    knockout = sched[knock_mask].copy()
    if knockout.empty:
        raise ValueError("No knockout matches found in schedule")

    round_order = list(dict.fromkeys(knockout["round_number"]))

    # counters for stages
    stages = [
        "Round of 32",
        "Round of 16",
        "Quarter Finals",
        "Semi Finals",
        "Finals",
    ]

    # prepare group schedule metadata for group-table aggregation
    group_sched = sched[sched["round_number"].astype(str).str.match(r"^\d+$", na=False) | sched["group"].notna()]
    groups = list(pd.unique(group_sched["group"]))
    group_teams = {
        g: sorted(
            set(group_sched.loc[group_sched["group"] == g, "home_team"]).union(
                group_sched.loc[group_sched["group"] == g, "away_team"]
            )
        )
        for g in groups
    }
    group_rank_counts = {g: {t: [0] * len(group_teams[g]) for t in group_teams[g]} for g in group_teams}
    group_pts_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}
    group_gd_sums = {g: {t: 0 for t in group_teams[g]} for g in group_teams}

    # determine real teams (exclude placeholders like '1A', '3ABC', 'To be announced')
    placeholder_re = re.compile(r"^(?:To be announced|\d+[A-Z]+|3[A-Z]+)$", re.IGNORECASE)
    raw_home = [x for x in sched.get("home_team").dropna().tolist()]
    raw_away = [x for x in sched.get("away_team").dropna().tolist()]
    candidate = set(raw_home + raw_away)
    real_teams = set()
    for t in candidate:
        if not placeholder_re.match(str(t).strip()):
            real_teams.add(t)

    # also include any teams appearing in group match listings (they are real)
    group_mask = sched["group"].notna()
    for _, row in sched[group_mask].iterrows():
        real_teams.add(row["home_team"]) if pd.notna(row["home_team"]) else None
        real_teams.add(row["away_team"]) if pd.notna(row["away_team"]) else None

    all_teams = sorted(real_teams)
    stage_counts = {team: {s: 0 for s in stages + ["Winner"]} for team in all_teams}

    # ensure strengths contains all teams (fill missing with mean strengths)
    strengths = strengths.copy()
    missing = [t for t in all_teams if t not in strengths.index]
    if missing:
        # use neutral strengths to avoid extreme expected goals
        default_attack = 1.0
        default_defense = 1.0
        for t in missing:
            strengths.loc[t] = {"attack": default_attack, "defense": default_defense}

    if elo_ratings is not None:
        if isinstance(elo_ratings, pd.DataFrame):
            if "team" in elo_ratings.columns and "elo_rating" in elo_ratings.columns:
                elo_ratings = elo_ratings.set_index("team")["elo_rating"]
            else:
                raise ValueError("elo_ratings DataFrame must contain 'team' and 'elo_rating' columns")
        elif isinstance(elo_ratings, dict):
            elo_ratings = pd.Series(elo_ratings)
        elif not isinstance(elo_ratings, pd.Series):
            raise TypeError("elo_ratings must be a pandas Series, dict, or DataFrame")

        elo_ratings = elo_ratings.astype(float)
        avg_elo = float(elo_ratings.mean())
        missing_elo = [t for t in all_teams if t not in elo_ratings.index]
        if missing_elo:
            elo_ratings = pd.concat([elo_ratings, pd.Series({t: avg_elo for t in missing_elo})])

    # helper to resolve placeholders like '1A', '2B', '3ABC'
    def normalize_group_key(letter: str, groups):
        # try exact letter, then 'Group X'
        if letter in groups:
            return letter
        g = f"Group {letter}"
        if g in groups:
            return g
        # fallback to first group that endswith letter
        for gr in groups:
            if str(gr).strip().endswith(letter):
                return gr
        return None

    def resolve_knockout_winner(home: str, away: str) -> str:
        if elo_ratings is not None:
            probs = predict_elo_match_probabilities(home, away, elo_ratings)
            outcome = np.random.choice(
                ["home", "draw", "away"],
                p=[probs["home_win"], probs["draw"], probs["away_win"]],
            )
            if outcome == "home":
                return home
            if outcome == "away":
                return away
            return home if np.random.rand() < probs["home_win"] / (probs["home_win"] + probs["away_win"] + 1e-12) else away

        sim = simulate_match(home, away, strengths, n_simulations=1, elo_ratings=elo_ratings)
        hg = int(sim["home_goals"].iloc[0])
        ag = int(sim["away_goals"].iloc[0])
        if hg == ag:
            probs = calculate_match_probabilities(home, away, strengths, elo_ratings=elo_ratings)
            hw = probs["home_win"]
            aw = probs["away_win"]
            return home if np.random.rand() < hw / (hw + aw + 1e-12) else away
        return home if hg > ag else away

    for _ in range(n_simulations):
        # simulate matches
        all_results = []
        for _, match in group_sched.iterrows():
            h = match["home_team"]
            a = match["away_team"]
            if h not in strengths.index or a not in strengths.index:
                continue
            sim = simulate_match(h, a, strengths, n_simulations=1, elo_ratings=elo_ratings)
            all_results.append({
                "group": match.get("group"),
                "home_team": h,
                "away_team": a,
                "home_score": int(sim["home_goals"].iloc[0]),
                "away_score": int(sim["away_goals"].iloc[0]),
            })

        results_df = pd.DataFrame(all_results)
        standings_by_group = {}
        for g in groups:
            gr = results_df[results_df["group"] == g]
            if gr.empty:
                continue
            st = aggregate_group_standings(gr)
            # ensure all teams present
            for t in group_teams[g]:
                if t not in st.index:
                    st.loc[t] = {"points": 0, "played": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0}
            st = st.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])
            standings_by_group[g] = st

        # accumulate group-table statistics from this simulated group stage
        for g, teams in group_teams.items():
            if g not in standings_by_group:
                continue
            st = standings_by_group[g].copy()
            for t in teams:
                if t not in st.index:
                    st.loc[t] = {"points": 0, "played": 0, "goals_for": 0, "goals_against": 0, "goal_difference": 0}
            st = st.sort_values(["points", "goal_difference", "goals_for"], ascending=[False, False, False])
            for pos, team in enumerate(st.index.tolist(), start=1):
                group_rank_counts[g][team][pos - 1] += 1
                group_pts_sums[g][team] += int(st.loc[team, "points"])
                group_gd_sums[g][team] += int(st.loc[team, "goal_difference"])

        # initial knockout: process Round of 32 by resolving placeholders
        prev_winners = []
        for rnd in round_order:
            round_matches = knockout[knockout["round_number"] == rnd]
            # Round of 32: resolve slots directly from placeholders
            if str(rnd).startswith("Round of 32") or "32" in str(rnd):
                assignment_map = _build_round_of_32_third_place_assignment_map(standings_by_group)
                used_third = set()

                def resolve_group_slot(slot: str) -> str | None:
                    match = re.match(r"([12])([A-Z])$", str(slot).strip())
                    if not match:
                        return None
                    pos = int(match.group(1))
                    letter = match.group(2)
                    gkey = normalize_group_key(letter, standings_by_group.keys())
                    if gkey and gkey in standings_by_group and len(standings_by_group[gkey].index) >= pos:
                        return standings_by_group[gkey].index[pos - 1]
                    return None

                def resolve_r32_third_place(slot: str, opposite_slot: str) -> str | None:
                    if not slot or slot.lower().startswith("to be"):
                        return None
                    if slot in all_teams:
                        return slot
                    if re.match(r"([12])[A-Z]$", slot):
                        return resolve_group_slot(slot)
                    if re.match(r"3[A-Z]+$", slot) and assignment_map:
                        winner_slot = opposite_slot if re.match(r"^1[A-Z]$", opposite_slot) else None
                        if winner_slot:
                            return _resolve_round_of_32_third_place(winner_slot, standings_by_group, assignment_map)
                    m3 = re.match(r"3([A-Z]+)$", slot)
                    if m3:
                        letters = list(m3.group(1))
                        third_candidates = []
                        for L in letters:
                            gkey = normalize_group_key(L, standings_by_group.keys())
                            if gkey and gkey in standings_by_group and len(standings_by_group[gkey].index) >= 3:
                                team3 = standings_by_group[gkey].index[2]
                                third_candidates.append((team3, standings_by_group[gkey].loc[team3, ["points", "goal_difference", "goals_for"]].tolist()))
                        third_candidates.sort(key=lambda x: (-x[1][0], -x[1][1], -x[1][2]))
                        for team, _ in third_candidates:
                            if team not in used_third:
                                used_third.add(team)
                                return team
                    return None

                for _, match in round_matches.iterrows():
                    h_slot = str(match.get("home_team", "")).strip()
                    a_slot = str(match.get("away_team", "")).strip()

                    home = resolve_r32_third_place(h_slot, a_slot)
                    away = resolve_r32_third_place(a_slot, h_slot)

                    if home is None or away is None:
                        # cannot resolve; skip match
                        continue

                    stage_counts[home]["Round of 32"] += 1
                    stage_counts[away]["Round of 32"] += 1

                    winner = resolve_knockout_winner(home, away)
                    prev_winners.append(winner)

            else:
                # for later rounds, pair previous winners sequentially
                next_winners = []
                for i in range(0, len(prev_winners), 2):
                    try:
                        home = prev_winners[i]
                        away = prev_winners[i + 1]
                    except IndexError:
                        continue
                    if home is None or away is None:
                        continue

                    if "16" in str(rnd):
                        stage_counts[home]["Round of 16"] += 1
                        stage_counts[away]["Round of 16"] += 1
                    elif "Quarter" in str(rnd):
                        stage_counts[home]["Quarter Finals"] += 1
                        stage_counts[away]["Quarter Finals"] += 1
                    elif "Semi" in str(rnd):
                        stage_counts[home]["Semi Finals"] += 1
                        stage_counts[away]["Semi Finals"] += 1
                    elif "Final" in str(rnd):
                        stage_counts[home]["Finals"] += 1
                        stage_counts[away]["Finals"] += 1

                    winner = resolve_knockout_winner(home, away)
                    next_winners.append(winner)

                prev_winners = next_winners

        # final winner
        if prev_winners:
            champ = prev_winners[0]
            if champ:
                stage_counts[champ]["Winner"] += 1

    # assemble full tournament probabilities
    rows = []
    for team, counts in stage_counts.items():
        row = {"team": team}
        for s in stages:
            row[f"prob_{s.replace(' ', '_')}"] = counts[s] / n_simulations
        row["prob_Winner"] = counts["Winner"] / n_simulations
        rows.append(row)

    tournament_df = pd.DataFrame(rows).sort_values("prob_Winner", ascending=False).reset_index(drop=True)

    # assemble group tables from full tournament runs
    group_rows = []
    for g, teams in group_teams.items():
        n_teams = len(teams)
        for team in teams:
            counts = group_rank_counts[g][team]
            probs = [c / n_simulations for c in counts]
            expected_rank = sum((i + 1) * p for i, p in enumerate(probs))
            avg_points = group_pts_sums[g][team] / n_simulations
            avg_gd = group_gd_sums[g][team] / n_simulations

            row = {
                "group": g,
                "team": team,
                "expected_rank": expected_rank,
                "avg_points": avg_points,
                "avg_goal_difference": avg_gd,
            }
            for i, p in enumerate(probs, start=1):
                row[f"prob_{i}"] = p
            group_rows.append(row)

    group_tables = pd.DataFrame(group_rows).sort_values(["group", "expected_rank"]).reset_index(drop=True)

    if return_group_tables:
        return {"tournament_simulation": tournament_df, "group_tables": group_tables}

    return tournament_df
