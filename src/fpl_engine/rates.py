from __future__ import annotations
import pandas as pd


def event_rates_for_fixture(
    player_row: pd.Series,
    venue: str,
    team_strength_row: dict,
    opp_strength_row: dict,
    minutes: float,
    xg_boost: float,
    xa_boost: float,
) -> dict:
    xg90 = float(player_row.get("expected_goals_per_90", 0) or 0)
    xa90 = float(player_row.get("expected_assists_per_90", 0) or 0)
    pos = player_row.get("position_name", "MID")

    # Opponent defensive strength at the venue the opponent will be in
    def_mult = float(
        opp_strength_row.get(f"def_{'home' if venue=='away' else 'away'}", 1.0)
    )
    att_mult = 1.0 / max(def_mult, 1e-6)

    xg = xg90 * (minutes / 90.0) * att_mult * xg_boost
    xa = xa90 * (minutes / 90.0) * att_mult * xa_boost

    # GK saves proxy
    if pos == "GKP":
        saves90 = float(player_row.get("saves_per_90", 0) or 0)
        atk_mult = float(
            opp_strength_row.get(f"atk_{'home' if venue=='away' else 'away'}", 1.0)
        )
        saves = saves90 * (minutes / 90.0) * atk_mult
    else:
        saves = 0.0

    # Expected GA lambda from opp attack vs team defense
    team_def = float(
        team_strength_row.get(f"def_{'home' if venue=='home' else 'away'}", 1.0)
    )
    opp_atk = float(
        opp_strength_row.get(f"atk_{'home' if venue=='away' else 'away'}", 1.0)
    )
    lam = (
        1.4 * (opp_atk / max(team_def, 1e-6)) * (minutes / 90.0)
    )  # 1.4 ~= avg PL goals per team per match

    return {
        "xg": float(xg),
        "xa": float(xa),
        "saves": float(saves),
        "lam_ga": float(lam),
    }
