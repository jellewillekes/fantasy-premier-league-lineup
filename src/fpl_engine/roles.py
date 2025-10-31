from __future__ import annotations
import pandas as pd

def role_boosts(player_row: pd.Series) -> tuple[float,float]:
    xg_boost = 1.0
    xa_boost = 1.0
    pen_order = player_row.get("penalties_order")
    try:
        if pd.notna(pen_order) and str(pen_order).strip() != "" and int(pen_order) == 1:
            xg_boost *= 1.20
    except Exception:
        pass
    if str(player_row.get("direct_freekicks_text","")).strip():
        xg_boost *= 1.05
    if str(player_row.get("corners_and_indirect_freekicks_text","")).strip():
        xa_boost *= 1.10
    return float(xg_boost), float(xa_boost)
