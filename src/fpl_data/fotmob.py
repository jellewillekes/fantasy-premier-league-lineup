from typing import Dict, Any, List
import requests

FOTMOB_LEAGUE_API = "https://www.fotmob.com/api/leagues?id=47"  # 47 = EPL

def fetch_fotmob_league() -> Dict[str, Any]:
    """
    Fetch the EPL league JSON from FotMob (unofficial public endpoint).
    Returns structured JSON including leaderboards.
    """
    r = requests.get(FOTMOB_LEAGUE_API, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json()

def extract_leaderboard(league_json: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    """
    Extract a leaderboard by label key (e.g., 'expectedGoals', 'expectedAssists', 'shotsOnTarget',
    'saves', 'cleanSheets'). Returns list of dicts with player names and values.
    """
    stats = league_json.get("topPlayers", [])
    for block in stats:
        if block.get("stat") == key and "players" in block:
            out = []
            for p in block["players"]:
                out.append({
                    "player": p.get("name"),
                    "team": p.get("teamName"),
                    "value": p.get("statValue"),
                })
            return out
    return []

if __name__ == "__main__":
    lj = fetch_fotmob_league()
    for k in ["expectedGoals", "expectedAssists", "shotsOnTarget", "saves", "cleanSheets"]:
        print(k, extract_leaderboard(lj, k)[:5])
