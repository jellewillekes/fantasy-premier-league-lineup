from __future__ import annotations
import numpy as np
import pandas as pd

def expected_bonus_points(player_row: pd.Series, xg: float, xa: float, saves: float) -> float:
    ict = float(player_row.get("ict_index", 0) or 0)
    pos = player_row.get("position_name","MID")
    pos_base = {"GKP": 0.10, "DEF": 0.15, "MID": 0.20, "FWD": 0.20}.get(pos, 0.18)
    ict_norm = ict / max(50.0, ict)  # in [0,1]
    base = pos_base + 0.4*(xg+xa) + 0.1*(saves/3.0)
    bonus = (0.3*ict_norm + base)
    return float(np.clip(bonus, 0.0, 1.5))
