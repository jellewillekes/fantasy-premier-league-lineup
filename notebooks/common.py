# notebooks/common.py
from __future__ import annotations
import os, sys, json, math, argparse
import re

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from fpl_engine.fpl_api import get_bootstrap, get_fixtures_df, get_players_df
from fpl_engine.fdorg_api import get_pl_standings, get_pl_matches
from fpl_engine.team_strength import compute_team_strength
from fpl_engine.minutes import estimate_minutes_prob, distribute_minutes_dgw
from fpl_engine.roles import role_boosts
from fpl_engine.rates import event_rates_for_fixture
from fpl_engine.bonus import expected_bonus_points
from fpl_engine.ep import ep_from_components
from fpl_engine.filters import filter_min_sixty

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
MY_TEAM_JSON = DATA_DIR / "my_team.json"

from functools import lru_cache

@lru_cache(maxsize=1)
def _boot_cached():
    return get_bootstrap()

@lru_cache(maxsize=1)
def _fixtures_cached():
    return get_fixtures_df()

def load_universe(min_sixty: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    boot = _boot_cached()
    players = get_players_df(boot)
    players = filter_min_sixty(players, min_matches=min_sixty)
    fixtures = _fixtures_cached()
    return players, fixtures

def compute_strengths() -> pd.DataFrame:
    standings = get_pl_standings()
    matches = get_pl_matches()
    strengths = compute_team_strength(matches, standings)
    return strengths

def build_ep_table(players: pd.DataFrame, fixtures: pd.DataFrame,
                   strengths: pd.DataFrame, gws: list[int]) -> dict[int, dict[int, dict[str, float]]]:
    # Map team name -> strengths
    s_map = strengths.set_index("team").to_dict(orient="index") if "team" in strengths.columns else {}
    def neutral():
        return {"atk_home":1.0, "atk_away":1.0, "def_home":1.0, "def_away":1.0}
    ep_by_gw: dict[int, dict[int, dict[str, float]]] = {}
    for _, p in players.iterrows():
        pid  = int(p["id"])
        team = p["club_name"]
        pos  = p["position_name"]
        ep_by_gw[pid] = {}
        for gw in gws:
            fx = fixtures[fixtures["event"] == gw]
            team_fx = fx[(fx["team_h_name"] == team) | (fx["team_a_name"] == team)]
            if team_fx.empty:
                continue
            mins_est = estimate_minutes_prob(p, None, short_rest=False)
            per_fix_minutes = distribute_minutes_dgw(mins_est["E_min_if_start"], fixtures_in_gw=len(team_fx), is_gkp=(pos=="GKP"))
            mean_sum = 0.0
            var_sum  = 0.0
            for i, (_, row) in enumerate(team_fx.reset_index().iterrows()):
                home   = (row["team_h_name"] == team)
                venue  = "home" if home else "away"
                opp    = row["team_a_name"] if home else row["team_h_name"]
                t_str  = s_map.get(team, neutral())
                o_str  = s_map.get(opp,  neutral())
                xg_boost, xa_boost = role_boosts(p)
                rates = event_rates_for_fixture(p, venue, t_str, o_str, per_fix_minutes[i], xg_boost, xa_boost)
                p_cs = math.exp(-rates["lam_ga"]) * mins_est["P60_if_start"]
                mean, var = ep_from_components(
                    pos, per_fix_minutes[i], mins_est["P_start"], mins_est["P60_if_start"],
                    rates["xg"], rates["xa"], p_cs, rates["saves"], rates["lam_ga"],
                    expected_bonus_points(p, rates["xg"], rates["xa"], rates["saves"])
                )
                mean_sum += mean
                var_sum  += var
            ep_by_gw[pid][gw] = {"mean": float(mean_sum), "var": float(var_sum)}
    return ep_by_gw

# -------- Team name matching & persistence --------
def _normalize_name(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).strip()

def match_player_names(players: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """
    Fuzzy-ish matching on FPL 'player_name' (web_name) with disambiguation via selection%.
    Normalizes both input and player names by lowercasing and stripping non-alphanumerics.
    """
    df = players.copy()
    df["_norm"] = df["player_name"].map(_normalize_name)

    out_rows = []
    for raw in names:
        key = _normalize_name(raw)
        if not key:
            continue

        # 1) exact normalized match
        m = df[df["_norm"] == key]

        # 2) any name containing all tokens (OR) in normalized form
        if m.empty:
            toks = [t for t in key.split() if t]
            if toks:
                # escape tokens for regex; _norm already lowercase/alnum, but safe anyway
                pattern = "|".join(re.escape(t) for t in toks)
                m = df[df["_norm"].str.contains(pattern, na=False, regex=True)]

        # 3) fallback: startswith first token
        if m.empty:
            first = key.split()[0]
            m = df[df["_norm"].str.startswith(first, na=False)]

        if not m.empty:
            # tie-breaker: pick most selected by managers if column exists
            if "selected_by_percent" in m.columns:
                sel = pd.to_numeric(m["selected_by_percent"], errors="coerce")
                m = m.assign(sel=sel).sort_values("sel", ascending=False)
            out_rows.append(m.iloc[0])
        else:
            print(f"[WARN] Could not match: '{raw}'")

    result = pd.DataFrame(out_rows)
    return result.drop(columns=["_norm"], errors="ignore")

def save_my_team(names: list[str]) -> None:
    MY_TEAM_JSON.write_text(json.dumps({"names": names}, indent=2))

def load_my_team() -> list[str]:
    if MY_TEAM_JSON.exists():
        try:
            data = json.loads(MY_TEAM_JSON.read_text())
            return data.get("names", [])
        except Exception:
            pass
    return []

def horizon_list(fixtures: pd.DataFrame, n: int = 4) -> list[int]:
    gws = sorted(fixtures["event"].dropna().unique().tolist())
    return gws[:n]
