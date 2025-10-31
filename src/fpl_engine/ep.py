from __future__ import annotations

SCORING = {
  "minutes_under_60": 1,
  "minutes_60_plus": 2,
  "assist": 3,
  "goal": {"FWD": 4, "MID": 5, "DEF": 6, "GKP": 6},
  "clean_sheet": {"FWD": 0, "MID": 1, "DEF": 4, "GKP": 4},
  "saves_per_3": 1,
  "penalty_save": 5,
  "penalty_miss": -2,
  "goals_conceded_per_2": -1,
  "yellow": -1,
  "red": -3,
  "own_goal": -2,
}

def ep_from_components(pos: str, minutes: float, p_start: float, p60_if_start: float,
                       xg: float, xa: float, p_cs: float, saves: float, lam_ga: float, bonus: float) -> tuple[float, float]:
    # Minutes expectation
    p60 = p_start * p60_if_start
    min_pts = p60*SCORING["minutes_60_plus"] + (p_start - p60)*SCORING["minutes_under_60"]

    # Attacking expectation (Poisson mean)
    goal_pts   = xg * SCORING["goal"].get(pos, 5)
    assist_pts = xa * SCORING["assist"]
    var_att    = xg * (SCORING["goal"].get(pos,5)**2) + xa * (SCORING["assist"]**2)

    # Clean sheet & goals conceded (smooth)
    cs_pts   = p_cs * SCORING["clean_sheet"].get(pos, 0)
    gc_malus = -0.5 * lam_ga if pos in ("DEF","GKP") else 0.0

    # GK saves
    saves_pts = (saves/3.0) * SCORING["saves_per_3"] if pos=="GKP" else 0.0

    total = min_pts + goal_pts + assist_pts + cs_pts + saves_pts + gc_malus + bonus
    var   = var_att + p60*(1-p60)
    return float(total), float(var)
