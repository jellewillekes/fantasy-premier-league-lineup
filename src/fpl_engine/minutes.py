from __future__ import annotations
import pandas as pd
import numpy as np


def estimate_minutes_prob(
    player_row: pd.Series,
    history_df: pd.DataFrame | None = None,
    short_rest: bool = False,
) -> dict:
    pos = player_row.get("position_name", "MID")
    base_start = float(player_row.get("starts_per_90", 0.6))
    base_start = float(np.clip(base_start, 0.2, 0.98))

    # Simple news heuristic
    news = str(player_row.get("news", "")).lower()
    injury_penalty = 0.0
    if "doubt" in news or "late test" in news:
        injury_penalty = 0.15
    if "injury" in news or "ruled out" in news or "out" in news:
        injury_penalty = 0.40
    if "return" in news:
        injury_penalty = 0.10
    p_start = float(np.clip(base_start - injury_penalty, 0.05, 0.98))

    p60_if_start = {"GKP": 0.98, "DEF": 0.90, "MID": 0.82, "FWD": 0.78}.get(pos, 0.82)

    if short_rest:
        p_start *= 0.92
        p60_if_start *= 0.92

    e_min_if_start = 94 if pos == "GKP" else 86 if pos == "DEF" else 80
    e_min_if_sub = 0 if pos == "GKP" else 12

    return {
        "P_start": p_start,
        "P60_if_start": p60_if_start,
        "E_min_if_start": float(e_min_if_start),
        "E_min_if_sub": float(e_min_if_sub),
    }


def distribute_minutes_dgw(
    base_minutes: float, fixtures_in_gw: int, is_gkp: bool = False
) -> list[float]:
    if fixtures_in_gw <= 1:
        return [float(base_minutes)]
    cap = 180 if is_gkp else 160
    base = float(min(cap, base_minutes * 2))
    return [0.55 * base, 0.45 * base]
