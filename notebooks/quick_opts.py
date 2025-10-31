# notebooks/quick_opts.py
from __future__ import annotations
import argparse
import pandas as pd
from common import load_universe, compute_strengths, build_ep_table, horizon_list, match_player_names
from fpl_engine.optimize_squad import solve_wildcard_from_ep
from fpl_engine.lineup import best_xi_for_gw
from fpl_engine.transfers import suggest_best_transfer

def main():
    ap = argparse.ArgumentParser(description="Quick optimizations: wildcard, best XI, and suggested transfers.")
    ap.add_argument("--budget", type=float, default=100.0, help="Wildcard budget in £m")
    ap.add_argument("--horizon", type=int, default=4, help="Number of GWs for horizon")
    ap.add_argument("--myteam", type=str, default="", help="Comma-separated names to evaluate transfers from current team")
    ap.add_argument("--min_sixty", type=int, default=5, help="Minimum matches with ≥60 minutes required (default: 5)")
    ap.add_argument("--ft", type=int, default=1, help="Number of free transfers to suggest (default: 1)")
    args = ap.parse_args()

    players, fixtures = load_universe(min_sixty=args.min_sixty)
    strengths = compute_strengths()
    gws = horizon_list(fixtures, args.horizon)
    ep_by_gw = build_ep_table(players, fixtures, strengths, gws)

    # Wildcard best 15
    wc = solve_wildcard_from_ep(players, ep_by_gw, gws, budget=args.budget, max_per_club=3)
    wc_cost = wc["now_cost"].sum()
    wc_h_ep = wc["id"].map(lambda pid: sum(ep_by_gw.get(int(pid), {}).get(gw, {}).get("mean", 0.0) for gw in gws)).sum()
    wc = wc.assign(h_ep=wc["id"].map(lambda pid: sum(ep_by_gw.get(int(pid), {}).get(gw, {}).get("mean", 0.0) for gw in gws)))

    print(f"\n=== Wildcard (best 15) under {args.budget:.1f}m ===")
    print(wc[["player_name","position_name","club_name","now_cost","h_ep"]].to_string(index=False))
    print(f"Total cost: {wc_cost:.1f}m | Horizon EP: {wc_h_ep:.2f}")

    # Best XI next GW from wildcard
    xi, cap, vc, bench = best_xi_for_gw(wc, ep_by_gw, gws[0], risk_lambda=0.0)
    print(f"\nBest XI for GW {gws[0]} (from Wildcard):")
    print(xi.sort_values('position_name')[['player_name','position_name','club_name','now_cost','ep_mean']].to_string(index=False))
    print("CAPTAIN:", cap, "| VICE:", vc)
    print("BENCH:", bench[:3])

    # If user provided their current team, suggest transfers (ft can be >1)
    if args.myteam:
        names = [s.strip() for s in args.myteam.split(",") if s.strip()]
        current = match_player_names(players, names)
        if len(current) >= 11:
            move = suggest_best_transfer(
                current, players, bank=0.0, horizon_gws=gws, ep_by_gw=ep_by_gw, ft=args.ft
            )
            print(f"\nSuggested {args.ft} transfer(s) from your current team over horizon:")
            print(move)
        else:
            print("\n[WARN] Could not match enough players from --myteam to suggest transfers (need ≥ 11).")

if __name__ == "__main__":
    main()
