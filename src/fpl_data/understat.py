import json
import re
from html import unescape
from typing import List, Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup

UNDERSTAT_LEAGUE_URL = "https://understat.com/league/EPL/{season_start_year}"

def _extract_understat_json(html_text: str, var_name: str) -> List[Dict]:
    """
    Understat embeds JSON in a <script> tag, e.g.:
      var playersData = JSON.parse('...');
    Return the parsed list/dict.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    scripts = soup.find_all("script")
    pattern = re.compile(r"var\s+" + re.escape(var_name) + r"\s*=\s*JSON\.parse\('(.+?)'\);", re.S)
    for sc in scripts:
        if not sc.string:
            continue
        m = pattern.search(sc.string)
        if m:
            encoded = m.group(1)
            decoded = unescape(encoded)
            decoded = decoded.encode("utf-8").decode("unicode_escape")
            return json.loads(decoded)
    raise RuntimeError(f"Could not find {var_name} in the page scripts")

def fetch_understat_players(season_start_year: int = 2025, user_agent: str = "Mozilla/5.0") -> pd.DataFrame:
    """
    Fetch all EPL player rows for the given season (Understat), return as DataFrame.
    Columns include: player, team, pos, minutes, goals, assists, shots, key_passes, xG, xA, npxG, etc.
    """
    url = UNDERSTAT_LEAGUE_URL.format(season_start_year=season_start_year)
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=30)
    r.raise_for_status()
    players = _extract_understat_json(r.text, "playersData")
    df = pd.json_normalize(players)

    rename = {
        "player_name": "player",
        "team_title": "team",
        "position": "pos",
        "games": "games",
        "time": "minutes",
        "goals": "goals",
        "assists": "assists",
        "shots": "shots",
        "key_passes": "key_passes",
        "xG": "xG",
        "xA": "xA",
        "npxG": "npxG",
        "npg": "non_pen_goals",
        "yellow_cards": "yc",
        "red_cards": "rc",
    }
    keep = list(rename.keys())
    df = df[keep].rename(columns=rename)

    num_cols = ["games","minutes","goals","assists","shots","key_passes","xG","xA","npxG","non_pen_goals","yc","rc"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["90s"] = df["minutes"] / 90.0
    for raw, per90 in [("xG","xG_per90"), ("xA","xA_per90"), ("shots","shots_per90"),
                       ("key_passes","key_passes_per90"), ("goals","goals_per90"), ("assists","assists_per90")]:
        df[per90] = df.apply(lambda r: r[raw] / r["90s"] if r["90s"] > 0 else 0.0, axis=1)

    df["att_threat"] = df["xG_per90"] + 0.7 * df["xA_per90"]
    return df.sort_values(["xG"], ascending=False).reset_index(drop=True)

def topn(df: pd.DataFrame, stat: str, n: int = 5, min_minutes: int = 180) -> pd.DataFrame:
    cols = ["player", "team", "pos", "minutes", stat]
    view = df[df["minutes"] >= min_minutes][cols].sort_values(stat, ascending=False).head(n)
    return view.reset_index(drop=True)

if __name__ == "__main__":
    df = fetch_understat_players(2025)
    print("Top 5 xG:")
    print(topn(df, "xG"))
