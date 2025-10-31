from __future__ import annotations
import argparse
import pandas as pd
from common import (
    load_universe, compute_strengths, build_ep_table, horizon_list,
    match_player_names, save_my_team, load_my_team
)
from fpl_engine.lineup import best_xi_for_gw


def upcoming_fixtures_table(
    fixtures: pd.DataFrame, team_names: list[str], gws: list[int]
) -> pd.DataFrame:
    mask = fixtures["event"].isin(gws) & (
        fixtures["team_h_name"].isin(team_names) | fixtures["team_a_name"].isin(team_names)
    )
    cols = ["event", "team_h_name", "team_a_name"]
    return fixtures.loc[mask, cols].sort_values(["event", "team_h_name"])


def main():
    parser = argparse.ArgumentParser(description="Analyze your current FPL team over a GW horizon.")
    parser.add_argument(
        "--names",
        type=str,
        default="",
        help='Comma-separated list of your 15 player names (e.g., "Areola, Martinez, ..."). '
             "If omitted, the saved team in data/my_team.json will be used if available.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save these names as my team (data/my_team.json).",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=4,
        help="Number of upcoming gameweeks to consider (default: 4).",
    )
    parser.add_argument(
        "--min_sixty",
        type=int,
        default=5,
        help="Minimum number of matches with ≥60 minutes required to include a player (default: 5).",
    )
    args = parser.parse_args()

    # Load & filter universe according to min_sixty rule
    players, fixtures = load_universe(min_sixty=args.min_sixty)
    strengths = compute_strengths()
    gws = horizon_list(fixtures, args.horizon)
    if not gws:
        raise RuntimeError("No upcoming gameweeks found in fixtures.")
    ep_by_gw = build_ep_table(players, fixtures, strengths, gws)

    # Resolve team names: CLI > saved file
    names_list = (
        [s.strip() for s in args.names.split(",") if s.strip()]
        if args.names.strip()
        else load_my_team()
    )
    if not names_list:
        print('No team provided. Use --names "Areola, Martinez, ..." or save first with --save.')
        return
    if args.save and args.names.strip():
        save_my_team(names_list)

    # Match names to players
    squad_df = match_player_names(players, names_list)
    if squad_df.empty or len(squad_df) < len(names_list):
        print("[WARN] Some names could not be matched or were filtered by the ≥60-min rule. Showing matched subset only.")

    print("\n=== Matched squad ===")
    base_cols = ["player_name", "position_name", "club_name", "now_cost", "form", "points_per_game", "total_points"]
    print(squad_df[base_cols].to_string(index=False))

    # Horizon EP per player
    def h_ep(pid: int) -> float:
        return sum(ep_by_gw.get(pid, {}).get(gw, {}).get("mean", 0.0) for gw in gws)

    squad_df = squad_df.copy()
    squad_df["h_ep"] = squad_df["id"].map(h_ep)

    print(f"\n=== Squad — Horizon EP (next {len(gws)} GWs) ===")
    print(
        squad_df.sort_values("h_ep", ascending=False)[
            ["player_name", "position_name", "club_name", "now_cost", "h_ep"]
        ].to_string(index=False)
    )

    # Upcoming fixtures for clubs represented in your squad
    team_names = sorted(squad_df["club_name"].unique().tolist())
    print(f"\n=== Upcoming fixtures for your clubs (next {len(gws)} GWs) ===")
    print(upcoming_fixtures_table(fixtures, team_names, gws).to_string(index=False))

    # Best XI & captain for the next GW
    next_gw = gws[0]
    xi, captain, vice, bench = best_xi_for_gw(squad_df, ep_by_gw, next_gw, risk_lambda=0.0)
    print(f"\n=== Best XI for GW {next_gw} ===")
    print(
        xi.sort_values("position_name")[
            ["player_name", "position_name", "club_name", "now_cost", "ep_mean"]
        ].to_string(index=False)
    )
    print("CAPTAIN:", captain, "| VICE:", vice)
    print("BENCH ORDER:", bench[:3])

    # Position-level summary
    print("\n=== Position summary (Horizon EP) ===")
    print(squad_df.groupby("position_name")["h_ep"].sum().sort_values(ascending=False))


if __name__ == "__main__":
    main()
