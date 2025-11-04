from __future__ import annotations

import os, sys, json, math, argparse, re, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT / "src"))

import pandas as pd

from fpl_engine.fpl_api import get_bootstrap, get_fixtures_df, get_players_df
from fpl_engine.fdorg_api import get_pl_standings, get_pl_matches
from fpl_engine.team_strength import compute_team_strength
from fpl_engine.minutes import estimate_minutes_prob, distribute_minutes_dgw
from fpl_engine.roles import role_boosts
from fpl_engine.rates import event_rates_for_fixture
from fpl_engine.bonus import expected_bonus_points
from fpl_engine.ep import ep_from_components
from fpl_engine.filters import filter_min_sixty
from fpl_engine.lineup import best_xi_for_gw
from fpl_engine.transfers import suggest_best_transfer
from fpl_engine.optimize_squad import solve_wildcard_from_ep  # wildcard solver

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)
MY_TEAM_JSON = DATA_DIR / "my_team.json"

def load_my_team() -> list[str]:
    if MY_TEAM_JSON.exists():
        try:
            data = json.loads(MY_TEAM_JSON.read_text())
            names = data.get("names", [])
            if isinstance(names, list):
                return [str(x).strip() for x in names if str(x).strip()]
        except Exception:
            pass
    return []

def _normalize_name(s: str) -> str:
    # robust: strip accents, keep alnum + space, lowercase
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).strip()

def match_player_names(players: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """
    Fuzzy-ish matching on FPL 'player_name' (web_name). Picks the most-selected
    player on ties (selected_by_percent) if available.
    """
    if not names:
        return pd.DataFrame(columns=players.columns)

    df = players.copy()
    df["_norm"] = df["player_name"].map(_normalize_name)

    out_rows = []
    for raw in names:
        key = _normalize_name(raw)
        if not key:
            continue

        # 1) exact normalized match
        m = df[df["_norm"] == key]

        # 2) contains any token
        if m.empty:
            toks = [t for t in key.split() if t]
            if toks:
                pattern = "|".join(re.escape(t) for t in toks)
                m = df[df["_norm"].str.contains(pattern, na=False, regex=True)]

        # 3) startswith first token
        if m.empty:
            first = key.split()[0]
            m = df[df["_norm"].str.startswith(first, na=False)]

        if not m.empty:
            if "selected_by_percent" in m.columns:
                sel = pd.to_numeric(m["selected_by_percent"], errors="coerce")
                m = m.assign(sel=sel).sort_values("sel", ascending=False)
            out_rows.append(m.iloc[0])
        else:
            print(f"[WARN] Could not match: '{raw}'")

    res = pd.DataFrame(out_rows)
    # Drop helper columns if present
    res = res.drop(columns=["_norm", "sel"], errors="ignore")
    return res

def horizon_list(fixtures: pd.DataFrame, n: int = 4) -> list[int]:
    gws = sorted(fixtures["event"].dropna().unique().tolist())
    return gws[:n]

# ----------------------- universe builders -----------------------
def build_universe_pair(min_sixty: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      players_full      -> ALL players
      players_filtered  -> players passing the ≥60 rule
      fixtures
    """
    boot = get_bootstrap()
    players_full = get_players_df(boot)
    fixtures = get_fixtures_df()
    players_filtered = filter_min_sixty(players_full, min_matches=min_sixty)
    return players_full, players_filtered, fixtures

def compute_team_strengths() -> pd.DataFrame:
    standings = get_pl_standings()
    matches = get_pl_matches()
    strengths = compute_team_strength(matches, standings)  # team, atk_home, atk_away, def_home, def_away
    return strengths

def force_include_names(players_filtered: pd.DataFrame,
                        players_full: pd.DataFrame,
                        names: list[str]) -> pd.DataFrame:
    """Union of filtered + rows from full that match `names` by normalized player_name."""
    if not names:
        return players_filtered.copy()

    def norm_series(s: pd.Series) -> pd.Series:
        return s.map(_normalize_name)

    full = players_full.copy()
    full["_norm"] = norm_series(full["player_name"])
    want = {_normalize_name(n) for n in names if str(n).strip()}
    forced = full[full["_norm"].isin(want)].drop(columns=["_norm"], errors="ignore")

    base = players_filtered.copy()
    union = pd.concat([base, forced], ignore_index=True)
    union = union.drop_duplicates(subset=["id"], keep="first")
    return union

def ids_failing_minutes(players_full: pd.DataFrame,
                        players_filtered: pd.DataFrame,
                        names: list[str]) -> list[int]:
    """IDs among `names` that are NOT in the filtered universe (i.e., failed ≥60 rule)."""
    if not names:
        return []
    # map names -> IDs from full
    full = players_full.copy()
    full["_norm"] = full["player_name"].map(_normalize_name)
    want = {_normalize_name(n) for n in names if str(n).strip()}
    in_full = full[full["_norm"].isin(want)]
    ids_full = set(in_full["id"].astype(int))
    ids_ok = set(pd.to_numeric(players_filtered["id"], errors="coerce").dropna().astype(int))
    return sorted(list(ids_full - ids_ok))

# ----------------------- EP computation -------------------------
def ep_table(players: pd.DataFrame, fixtures: pd.DataFrame,
             strengths: pd.DataFrame, horizon_gws: list[int]) -> dict[int, dict[int, dict[str, float]]]:
    # Map: team_name -> strengths dict
    s_map = strengths.set_index("team").to_dict(orient="index") if "team" in strengths.columns else {}

    def neutral():
        return {"atk_home":1.0, "atk_away":1.0, "def_home":1.0, "def_away":1.0}

    ep_by_gw: dict[int, dict[int, dict[str, float]]] = {}
    for _, p in players.iterrows():
        pid  = int(p["id"])
        team = p["club_name"]
        pos  = p["position_name"]
        ep_by_gw[pid] = {}
        for gw in horizon_gws:
            fx = fixtures[fixtures["event"] == gw]
            team_fx = fx[(fx["team_h_name"] == team) | (fx["team_a_name"] == team)]
            if team_fx.empty:
                continue
            mins_est = estimate_minutes_prob(p, None, short_rest=False)
            per_fix_minutes = distribute_minutes_dgw(
                mins_est["E_min_if_start"], fixtures_in_gw=len(team_fx), is_gkp=(pos == "GKP")
            )
            mean_sum = 0.0
            var_sum  = 0.0
            rows = team_fx[["team_h_name","team_a_name"]].to_numpy()
            for i in range(len(rows)):
                home   = (rows[i,0] == team)
                venue  = "home" if home else "away"
                opp    = rows[i,1] if home else rows[i,0]
                t_str  = s_map.get(team, neutral())
                o_str  = s_map.get(opp,  neutral())
                xg_boost, xa_boost = role_boosts(p)
                rates = event_rates_for_fixture(
                    p, venue, t_str, o_str, per_fix_minutes[i], xg_boost, xa_boost
                )
                p_cs = math.exp(-rates["lam_ga"]) * mins_est["P60_if_start"]
                mean, var = ep_from_components(
                    pos,
                    per_fix_minutes[i],
                    mins_est["P_start"],
                    mins_est["P60_if_start"],
                    rates["xg"], rates["xa"],
                    p_cs,
                    rates["saves"],
                    rates["lam_ga"],
                    expected_bonus_points(p, rates["xg"], rates["xa"], rates["saves"]),
                )
                mean_sum += mean
                var_sum  += var
            ep_by_gw[pid][gw] = {"mean": float(mean_sum), "var": float(var_sum)}
    return ep_by_gw

def add_horizon_ep(df: pd.DataFrame, ep_by_gw: dict, gws: list[int]) -> pd.DataFrame:
    def h_ep(pid: int) -> float:
        return sum(ep_by_gw.get(int(pid), {}).get(gw, {}).get("mean", 0.0) for gw in gws)
    out = df.copy()
    out["h_ep"] = out["id"].map(h_ep)
    return out

# ----------------------------- main ------------------------------
def main():
    ap = argparse.ArgumentParser(description="Weekly FPL run: EPs, wildcard best 15, lineup, and transfer suggestion.")
    ap.add_argument("--horizon", type=int, default=4, help="Number of GWs to look ahead")
    ap.add_argument("--min_sixty", type=int, default=5, help="Minimum matches with ≥60 minutes to include a player")
    ap.add_argument("--use_wildcard", action="store_true", help="Build best-15 from scratch via wildcard")
    ap.add_argument("--budget", type=float, default=100.0, help="Wildcard budget in £m")
    ap.add_argument("--suggest_from_myteam", action="store_true",
                    help="Also suggest a transfer move starting from your saved team in data/my_team.json")
    ap.add_argument("--ft", type=int, default=1,
                    help="Number of free transfers available from your current team (default: 1)")
    args = ap.parse_args()

    # Universe (filtered + full) and fixtures
    players_full, players_filtered, fixtures = build_universe_pair(min_sixty=args.min_sixty)
    strengths = compute_team_strengths()
    gws = horizon_list(fixtures, args.horizon)
    if not gws:
        raise RuntimeError("No gameweeks found in fixtures")

    # Your saved team (if requested)
    names_saved = load_my_team() if args.suggest_from_myteam else []

    # Union for EP computation = filtered (optimization pool) + your saved players
    players_union = force_include_names(players_filtered, players_full, names_saved)

    # EP table over the union
    ep_by_gw = ep_table(players_union, fixtures, strengths, gws)

    # Add horizon EPs
    players_union_ep    = add_horizon_ep(players_union, ep_by_gw, gws)     # for printing/matching
    players_filtered_ep = add_horizon_ep(players_filtered, ep_by_gw, gws)  # optimization pool

    # --- Wildcard best 15 (from filtered pool) or fallback demo ---
    if args.use_wildcard:
        squad = solve_wildcard_from_ep(players_filtered_ep, ep_by_gw, gws, budget=args.budget, max_per_club=3)
        spent = squad["now_cost"].sum()
        h_ep_total = squad["h_ep"].sum()
        print(f"\n[WILDCARD] best 15 under budget {args.budget:.1f}m | cost: {spent:.1f}m | horizon EP: {h_ep_total:.2f}")
        print(squad[["player_name","position_name","club_name","now_cost","h_ep"]].to_string(index=False))
    else:
        # Fallback: pick 2/5/5/3 by horizon EP from filtered pool
        need = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
        parts = [players_filtered_ep[players_filtered_ep["position_name"] == pos].nlargest(k, "h_ep")
                 for pos, k in need.items()]
        squad = pd.concat(parts, ignore_index=True)

    # Lineup & captain for the immediate GW (from chosen squad)
    xi, captain, vice, bench = best_xi_for_gw(squad, ep_by_gw, gws[0], risk_lambda=0.0)
    print(f"\n[LINEUP] Best XI for GW {gws[0]} (from {'Wildcard' if args.use_wildcard else 'H-EP pick'}):")
    print(xi.sort_values("position_name")[["player_name","position_name","club_name","now_cost","ep_mean"]].to_string(index=False))
    print("CAPTAIN:", captain, "| VICE:", vice)
    print("BENCH:", bench[:3])

    # --- Suggest transfers from your saved current team (if requested) ---
    if args.suggest_from_myteam:
        names = names_saved
        if not names:
            print("\n[INFO] No saved team found at data/my_team.json. Skipping current-team transfer.")
        else:
            current = match_player_names(players_union_ep, names)
            if len(current) < len(names):
                print("[WARN] Some saved names were not matched; using matched subset.")

            # Who failed the minutes rule? (prioritize replacing)
            flagged_ids = ids_failing_minutes(players_full, players_filtered, names)
            if flagged_ids:
                flagged_names = current[current["id"].isin(flagged_ids)]["player_name"].tolist()
                print(f"[INFO] Players below minutes filter (prioritize replacing): {', '.join(flagged_names)}")

            if len(current) >= 11:
                # Try with prefer_out_ids first
                prioritized_move = None
                if flagged_ids:
                    prioritized_move = suggest_best_transfer(
                        current, players_filtered_ep, bank=0.0,
                        horizon_gws=gws, ep_by_gw=ep_by_gw, ft=args.ft,
                        prefer_out_ids=flagged_ids
                    )
                # Fallback: generic
                move = prioritized_move or suggest_best_transfer(
                    current, players_filtered_ep, bank=0.0,
                    horizon_gws=gws, ep_by_gw=ep_by_gw, ft=args.ft
                )
                print(f"\n[TRANSFER] Suggested {args.ft} transfer(s) from your saved current team:")
                print(move)
            else:
                print("\n[WARN] Not enough matched players from your saved team to suggest transfers (need ≥ 11).")

    # Also: suggest a move from the chosen (wildcard or demo) squad
    bank_after_wc = max(0.0, args.budget - squad["now_cost"].sum()) if args.use_wildcard else 0.0
    move_wc = suggest_best_transfer(
        squad, players_filtered_ep, bank=bank_after_wc, horizon_gws=gws, ep_by_gw=ep_by_gw, ft=args.ft
    )
    print(f"\n[TRANSFER] Suggested {args.ft} transfer(s) from the chosen squad (wildcard/demo):")
    print(move_wc)


if __name__ == "__main__":
    main()
