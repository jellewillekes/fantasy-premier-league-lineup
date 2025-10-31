from __future__ import annotations
import argparse
import pandas as pd
from common import load_universe, compute_strengths, build_ep_table, horizon_list 


def main():
    parser = argparse.ArgumentParser(description="Exploratory FPL data analysis")
    parser.add_argument(
        "--horizon", type=int, default=4,
        help="Number of upcoming gameweeks to consider (default: 4)"
    )
    parser.add_argument(
        "--min_sixty", type=int, default=5,
        help="Minimum number of matches with ≥60 minutes required to include a player (default: 5)"
    )
    args = parser.parse_args()

    players, fixtures = load_universe(min_sixty=args.min_sixty)

    strengths = compute_strengths()
    gws = horizon_list(fixtures, args.horizon)

    ep_by_gw = build_ep_table(players, fixtures, strengths, gws)

    def h_ep(pid: int) -> float:
        return sum(ep_by_gw.get(pid, {}).get(gw, {}).get("mean", 0.0) for gw in gws)

    df = players.copy()
    df["h_ep"] = df["id"].map(h_ep)
    df["value_ep"] = df["h_ep"] / df["now_cost"].replace(0, pd.NA)

    print(f"\n=== Top by Horizon EP (next {len(gws)}) ===")
    print(df.nlargest(20, "h_ep")[["player_name","position_name","club_name","now_cost","h_ep"]].to_string(index=False))

    print(f"\n=== Best Value (EP per £m) — next {len(gws)} GWs, min now_cost >= 4.0 ===")
    print(df[df["now_cost"] >= 4.0].nlargest(20, "value_ep")[["player_name","position_name","club_name","now_cost","h_ep","value_ep"]].to_string(index=False))

    for pos in ["GKP","DEF","MID","FWD"]:
        print(f"\n=== Form leaders ({pos}) — next {len(gws)} GWs ===")
        colset = ["player_name","club_name","now_cost","form","points_per_game","h_ep"]
        print(df[df["position_name"]==pos].nlargest(10, "form")[colset].to_string(index=False))

    print(f"\n=== xGI/90 leaders (MID/FWD) — next {len(gws)} GWs ===")
    colset = ["player_name","club_name","now_cost","expected_goal_involvements_per_90","h_ep"]
    att = df[df["position_name"].isin(["MID","FWD"])].copy()
    print(att.nlargest(15, "expected_goal_involvements_per_90")[colset].to_string(index=False))

    print(f"\n=== DEF defensive value (low xGC/90 + high h_ep) — next {len(gws)} GWs ===")
    d = df[df["position_name"]=="DEF"].copy()
    d["def_score"] = -d["expected_goals_conceded_per_90"] + 0.3*d["h_ep"]
    print(d.nlargest(15, "def_score")[["player_name","club_name","now_cost","expected_goals_conceded_per_90","h_ep","def_score"]].to_string(index=False))

if __name__ == "__main__":
    main()