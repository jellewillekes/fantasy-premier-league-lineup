from __future__ import annotations
from typing import Dict, List, Iterable, Optional
import pandas as pd
import pulp as pl


def solve_wildcard_from_ep(
    players_df: pd.DataFrame,
    ep_by_gw: Dict[int, Dict[int, Dict[str, float]]],
    gws: List[int],
    budget: float = 100.0,
    max_per_club: int = 3,
    lock_ids: Optional[Iterable[int]] = None,
    exclude_ids: Optional[Iterable[int]] = None,
) -> pd.DataFrame:
    """
    Build the best 15-man squad using only FPL data.
    Maximizes sum of EP over gws from ep_by_gw; enforces 2/5/5/3, ≤ max_per_club, and budget.

    Returns: DataFrame with columns [id, player_name, position_name, club_name, now_cost, h_ep]
    """
    lock_ids = set(lock_ids or [])
    exclude_ids = set(exclude_ids or [])

    def h_ep(pid: int) -> float:
        return sum(
            ep_by_gw.get(int(pid), {}).get(gw, {}).get("mean", 0.0) for gw in gws
        )

    df = players_df.copy()
    df = df[["id", "player_name", "position_name", "club_name", "now_cost"]].dropna(
        subset=["now_cost"]
    )
    df["h_ep"] = df["id"].map(h_ep)

    # Optional exclusions
    if exclude_ids:
        df = df[~df["id"].isin(exclude_ids)]

    # Decision variables
    idx = list(df.index)
    pos_need = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    x = pl.LpVariable.dicts("pick", idx, lowBound=0, upBound=1, cat=pl.LpBinary)

    prob = pl.LpProblem("FPL_Wildcard", pl.LpMaximize)

    # Objective: maximize horizon expected points
    prob += pl.lpSum(df.loc[i, "h_ep"] * x[i] for i in idx)

    # Squad size
    prob += pl.lpSum(x[i] for i in idx) == 15

    # Positions
    for pos, need in pos_need.items():
        prob += pl.lpSum(x[i] for i in idx if df.loc[i, "position_name"] == pos) == need

    # Club cap
    for club in df["club_name"].dropna().unique():
        prob += (
            pl.lpSum(x[i] for i in idx if df.loc[i, "club_name"] == club)
            <= max_per_club
        )

    # Budget
    prob += pl.lpSum(df.loc[i, "now_cost"] * x[i] for i in idx) <= float(budget)

    # Locks (force specific players)
    for i in idx:
        if int(df.loc[i, "id"]) in lock_ids:
            prob += x[i] == 1

    status = prob.solve(pl.PULP_CBC_CMD(msg=False))
    if pl.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"Wildcard solver not optimal (status={pl.LpStatus[status]})."
        )

    picked_idx = [i for i in idx if (x[i].value() or 0) > 0.5]
    squad = df.loc[picked_idx].copy()

    # Nice ordering: GKP -> DEF -> MID -> FWD, then by h_ep desc
    order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    squad["_pos"] = squad["position_name"].map(order)
    squad = (
        squad.sort_values(["_pos", "h_ep"], ascending=[True, False])
        .drop(columns=["_pos"])
        .reset_index(drop=True)
    )
    return squad
