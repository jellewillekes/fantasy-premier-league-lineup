from __future__ import annotations
import os
from typing import Optional
import pandas as pd
import requests

BASE = "https://api.football-data.org/v4"

# TEMP: hard-coded token (replace/remove for production)
HARDCODED_TOKEN = "8ac494b08ce44f1498053fbe13e44541"


def _headers() -> dict:
    token = (
        os.getenv("FOOTBALL_DATA_ORG_TOKEN")
        or os.getenv("FDORG_TOKEN")
        or HARDCODED_TOKEN
    )
    return {"X-Auth-Token": token}


def get_pl_standings(season: Optional[str] = None) -> pd.DataFrame:
    url = f"{BASE}/competitions/PL/standings"
    params = {"season": season} if season else {}
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for st in data.get("standings", []):
        if st.get("type") != "TOTAL":
            continue
        for row in st.get("table", []):
            team = row["team"]
            rows.append(
                {
                    "team": team["name"],
                    "played": row["playedGames"],
                    "won": row["won"],
                    "draw": row["draw"],
                    "lost": row["lost"],
                    "gf": row["goalsFor"],
                    "ga": row["goalsAgainst"],
                    "gd": row["goalDifference"],
                    "points": row["points"],
                    "position": row["position"],
                }
            )
    return pd.DataFrame(rows)


def get_pl_matches(season: Optional[str] = None) -> pd.DataFrame:
    url = f"{BASE}/competitions/PL/matches"
    params = {"season": season} if season else {}
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for m in data.get("matches", []):
        score = m.get("score", {}).get("fullTime", {}) or {}
        rows.append(
            {
                "match_id": m["id"],
                "utcDate": m["utcDate"],
                "status": m["status"],
                "matchday": m.get("matchday"),
                "homeTeam": m["homeTeam"]["name"],
                "awayTeam": m["awayTeam"]["name"],
                "score_full_home": score.get("home"),
                "score_full_away": score.get("away"),
            }
        )
    return pd.DataFrame(rows)
