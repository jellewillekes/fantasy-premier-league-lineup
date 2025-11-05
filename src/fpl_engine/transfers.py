# src/fpl_engine/transfers.py
from __future__ import annotations
from typing import List, Dict, Optional, Tuple
import pandas as pd
from .lineup import best_xi_for_gw

# Columns we try to keep consistent across frames (others are tolerated but ignored on swap)
SCHEMA_PREFERRED = [
    "id",
    "player_name",
    "position_name",
    "club_name",
    "now_cost",
    "h_ep",
    "form",
    "points_per_game",
    "total_points",
    "selected_by_percent",
]


def _h_ep_for(pid: int, ep_by_gw: dict, gws: List[int]) -> float:
    return float(
        sum(ep_by_gw.get(int(pid), {}).get(gw, {}).get("mean", 0.0) for gw in gws)
    )


def _ensure_h_ep_column(
    df: pd.DataFrame, ep_by_gw: dict, gws: List[int]
) -> pd.DataFrame:
    out = df.copy()
    out["h_ep"] = out["id"].map(lambda x: _h_ep_for(int(x), ep_by_gw, gws))
    return out


def _price(s: pd.Series) -> float:
    return float(pd.to_numeric(s.get("now_cost", 0.0), errors="coerce") or 0.0)


def _squad_club_counts(squad: pd.DataFrame) -> Dict[str, int]:
    return squad["club_name"].value_counts().to_dict()


def _compute_horizon_squad_ep(
    squad: pd.DataFrame, ep_by_gw: dict, gws: List[int], risk_lambda: float = 0.0
) -> Tuple[float, Dict[int, Dict]]:
    total = 0.0
    details: Dict[int, Dict] = {}
    for gw in gws:
        xi, cap, vc, bench = best_xi_for_gw(
            squad, ep_by_gw, gw, risk_lambda=risk_lambda
        )
        gw_ep = float(xi["ep_mean"].sum())
        total += gw_ep
        details[gw] = {
            "xi": xi,
            "captain": cap,
            "vice": vc,
            "bench": bench,
            "ep_sum": gw_ep,
        }
    return total, details


def _harmonize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop obviously helper columns and keep a stable schema superset.
    We don't *force* the schema; we only ensure no rogue columns (e.g., 'sel') break row replacement.
    """
    out = df.copy()
    # Drop helper columns if they sneak in
    out = out.drop(columns=["_norm", "sel"], errors="ignore")
    # Keep everything, but the swap operation will use common columns only.
    return out


def _legal_candidate_pool(
    universe: pd.DataFrame,
    pos: str,
    exclude_ids: set[int],
) -> pd.DataFrame:
    pool = universe[universe["position_name"] == pos].copy()
    pool = pool[~pool["id"].isin(exclude_ids)]
    if "h_ep" in pool.columns:
        pool = pool.sort_values(
            ["h_ep", "points_per_game"], ascending=False, na_position="last"
        )
    else:
        pool = pool.sort_values(
            ["points_per_game", "total_points"], ascending=False, na_position="last"
        )
    return pool


def _club_ok_after_swap(
    out_row: pd.Series,
    in_row: pd.Series,
    club_counts: Dict[str, int],
    max_per_club: int,
) -> bool:
    out_club = str(out_row["club_name"])
    in_club = str(in_row["club_name"])
    cc = dict(club_counts)
    cc[out_club] = cc.get(out_club, 0) - 1
    if cc[out_club] <= 0:
        cc.pop(out_club, None)
    cc[in_club] = cc.get(in_club, 0) + 1
    return cc[in_club] <= max_per_club


def _safe_swap_row(
    new_squad: pd.DataFrame, out_id: int, cand: pd.Series
) -> pd.DataFrame:
    """
    Replace the row for out_id in new_squad with cand, aligning by column names.
    Extra columns on either side are ignored.
    """
    dst_cols = list(new_squad.columns)
    common = [c for c in dst_cols if c in cand.index]
    for c in common:
        new_squad.loc[new_squad["id"] == out_id, c] = cand[c]
    return new_squad


def _try_single_transfer(
    current_squad: pd.DataFrame,
    universe: pd.DataFrame,
    bank: float,
    gws: List[int],
    ep_by_gw: dict,
    max_per_club: int = 3,
    k_targets_per_out: int = 15,
    prefer_out_ids: Optional[List[int]] = None,
) -> Optional[Dict]:
    cur = _harmonize_schema(_ensure_h_ep_column(current_squad, ep_by_gw, gws))
    uni = _harmonize_schema(_ensure_h_ep_column(universe, ep_by_gw, gws))

    base_ep, base_details = _compute_horizon_squad_ep(cur, ep_by_gw, gws)

    # iteration order for outs
    out_rows = list(cur.itertuples(index=False))
    if prefer_out_ids:
        prefer_set = set(int(x) for x in prefer_out_ids)
        out_rows.sort(
            key=lambda r: (
                0 if int(r.id) in prefer_set else 1,
                -float(getattr(r, "h_ep", 0.0)),
            )
        )

    best = {
        "gain": 0.0,
        "out": None,
        "in": None,
        "new_squad": None,
        "new_total_ep": base_ep,
        "base_total_ep": base_ep,
        "xi_by_gw": base_details,
    }

    club_counts = _squad_club_counts(cur)
    squad_ids = set(int(x) for x in cur["id"].tolist())

    for out_r in out_rows:
        pos = str(out_r.position_name)
        out_price = _price(pd.Series(out_r._asdict()))
        out_id = int(out_r.id)

        pool = _legal_candidate_pool(uni, pos, exclude_ids=squad_ids).head(
            k_targets_per_out
        )

        for _, cand in pool.iterrows():
            in_id = int(cand["id"])
            in_price = _price(cand)

            # budget
            if in_price > bank + out_price + 1e-9:
                continue
            # club cap
            if not _club_ok_after_swap(
                pd.Series(out_r._asdict()), cand, club_counts, max_per_club
            ):
                continue

            new_squad = cur.copy()
            new_squad = _safe_swap_row(new_squad, out_id=out_id, cand=cand)

            new_total, new_details = _compute_horizon_squad_ep(new_squad, ep_by_gw, gws)
            gain = new_total - base_ep
            if gain > best["gain"]:
                best.update(
                    {
                        "gain": float(gain),
                        "out": int(out_id),
                        "in": int(in_id),
                        "new_squad": new_squad,
                        "new_total_ep": float(new_total),
                        "base_total_ep": float(base_ep),
                        "xi_by_gw": new_details,
                    }
                )

    if best["gain"] <= 1e-9:
        return None
    return best


def suggest_best_transfer(
    current_squad: pd.DataFrame,
    universe: pd.DataFrame,
    bank: float,
    horizon_gws: List[int],
    ep_by_gw: dict,
    ft: int = 1,
    max_per_club: int = 3,
    prefer_out_ids: Optional[List[int]] = None,
    k_targets_per_out: int = 15,
) -> Dict:
    # work on copies
    squad = _harmonize_schema(current_squad.copy())
    uni = _harmonize_schema(universe.copy())
    gws = list(horizon_gws)

    base_total, _ = _compute_horizon_squad_ep(squad, ep_by_gw, gws)
    moves: List[Dict] = []
    remaining_ft = int(max(0, ft))
    remaining_bank = float(bank)

    while remaining_ft > 0:
        best_one = _try_single_transfer(
            squad,
            uni,
            bank=remaining_bank,
            gws=gws,
            ep_by_gw=ep_by_gw,
            max_per_club=max_per_club,
            k_targets_per_out=k_targets_per_out,
            prefer_out_ids=prefer_out_ids,
        )
        if not best_one:
            break

        out_id = best_one["out"]
        in_id = best_one["in"]

        r_out = squad.loc[squad["id"] == out_id].iloc[0]
        r_in = uni.loc[uni["id"] == in_id].iloc[0]

        remaining_bank += _price(r_out) - _price(r_in)

        squad = best_one["new_squad"]

        moves.append(
            {
                "out_id": int(out_id),
                "out_name": str(r_out["player_name"]),
                "out_club": str(r_out["club_name"]),
                "out_price": float(_price(r_out)),
                "in_id": int(in_id),
                "in_name": str(r_in["player_name"]),
                "in_club": str(r_in["club_name"]),
                "in_price": float(_price(r_in)),
                "gain": float(best_one["gain"]),
            }
        )

        remaining_ft -= 1
        # Avoid cycling the same incoming again
        uni = uni[uni["id"] != in_id].copy()
        # If we had a prioritized out, remove it from the list
        if prefer_out_ids:
            try:
                prefer_out_ids = [pid for pid in prefer_out_ids if pid != out_id]
            except Exception:
                prefer_out_ids = None

    final_total, final_xi_by_gw = _compute_horizon_squad_ep(squad, ep_by_gw, gws)

    return {
        "moves": moves,
        "new_squad": squad,
        "total_gain": float(final_total - base_total),
        "base_total_ep": float(base_total),
        "new_total_ep": float(final_total),
        "bank_left": float(remaining_bank),
        "xi_by_gw": final_xi_by_gw,
    }
