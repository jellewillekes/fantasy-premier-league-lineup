from __future__ import annotations
import pandas as pd

LEGAL_FORMATIONS = [
    (1, 3, 4, 3),
    (1, 3, 5, 2),
    (1, 4, 4, 2),
    (1, 4, 3, 3),
    (1, 5, 3, 2),
]


def best_xi_for_gw(
    squad_df: pd.DataFrame, ep_by_gw: dict[int, dict], gw: int, risk_lambda: float = 0.0
):
    df = squad_df.copy()
    df["ep_mean"] = df["id"].map(
        lambda i: ep_by_gw.get(i, {}).get(gw, {}).get("mean", 0.0)
    )
    df["ep_var"] = df["id"].map(
        lambda i: ep_by_gw.get(i, {}).get(gw, {}).get("var", 0.0)
    )

    def pick(df, pos, k):
        return df[df["position_name"] == pos].nlargest(k, "ep_mean")

    best = None
    for gk, d, m, f in LEGAL_FORMATIONS:
        gk_df = pick(df, "GKP", gk)
        d_df = pick(df, "DEF", d)
        m_df = pick(df, "MID", m)
        f_df = pick(df, "FWD", f)
        xi = pd.concat([gk_df, d_df, m_df, f_df])
        if len(xi) != 11:
            continue
        utility = xi["ep_mean"].sum() - risk_lambda * xi["ep_var"].sum()
        if (best is None) or (utility > best["utility"]):
            best = {"XI": xi, "utility": float(utility)}

    if best is None:
        raise ValueError("Failed to form XI")

    xi = best["XI"].copy()
    xi_sorted = xi.sort_values(["ep_mean"], ascending=False)
    captain = xi_sorted.iloc[0]["player_name"]
    vice = xi_sorted.iloc[1]["player_name"] if len(xi_sorted) > 1 else captain

    bench = df[~df["id"].isin(set(xi["id"]))].copy()
    bench["bench_score"] = bench["ep_mean"]
    bench_order = bench.sort_values("bench_score", ascending=False)[
        "player_name"
    ].tolist()

    return xi, captain, vice, bench_order
