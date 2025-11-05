from __future__ import annotations
import requests
import pandas as pd
from .filters import filter_min_sixty  # <-- NEW

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES = "https://fantasy.premierleague.com/api/fixtures/"


def get_bootstrap() -> dict:
    r = requests.get(FPL_BOOTSTRAP, timeout=30)
    r.raise_for_status()
    return r.json()


def get_players_df(boot: dict) -> pd.DataFrame:
    elements = pd.DataFrame(boot["elements"])
    teams = pd.DataFrame(boot["teams"])[["id", "name"]].rename(
        columns={"id": "team_id", "name": "club_name"}
    )
    types = pd.DataFrame(boot["element_types"])[["id", "singular_name_short"]].rename(
        columns={"id": "element_type", "singular_name_short": "position_name"}
    )

    df = elements.merge(teams, left_on="team", right_on="team_id", how="left").merge(
        types, left_on="element_type", right_on="element_type", how="left"
    )

    if "now_cost" in df:
        df["now_cost"] = pd.to_numeric(df["now_cost"], errors="coerce") / 10.0

    df = df.rename(columns={"web_name": "player_name"})

    num_cols = [
        "now_cost",
        "total_points",
        "points_per_game",
        "form",
        "minutes",
        "starts",
        "selected_by_percent",
        "expected_goals",
        "expected_assists",
        "expected_goal_involvements",
        "expected_goals_conceded",
        "expected_goals_per_90",
        "expected_assists_per_90",
        "expected_goal_involvements_per_90",
        "expected_goals_conceded_per_90",
        "clean_sheets_per_90",
        "saves_per_90",
        "goals_conceded_per_90",
        "starts_per_90",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def get_players_df_filtered(min_sixty: int = 5) -> pd.DataFrame:
    """
    Convenience: bootstrap -> players -> apply >=60-mins-in->=min_sixty-matches filter.
    """
    boot = get_bootstrap()
    players = get_players_df(boot)
    players = filter_min_sixty(players, min_matches=min_sixty)
    return players


def get_fixtures_df() -> pd.DataFrame:
    r = requests.get(FPL_FIXTURES, timeout=30)
    r.raise_for_status()
    fixtures = pd.DataFrame(r.json())

    # Attach team names
    boot = get_bootstrap()
    teams = pd.DataFrame(boot["teams"])[["id", "name"]].rename(
        columns={"id": "team_id", "name": "club_name"}
    )
    id2name = dict(zip(teams["team_id"], teams["club_name"]))

    if "team_h" in fixtures:
        fixtures["team_h_name"] = fixtures["team_h"].map(id2name)
    if "team_a" in fixtures:
        fixtures["team_a_name"] = fixtures["team_a"].map(id2name)

    if "event" in fixtures.columns:
        fixtures = fixtures.dropna(subset=["event"]).astype({"event": int})

    return fixtures
