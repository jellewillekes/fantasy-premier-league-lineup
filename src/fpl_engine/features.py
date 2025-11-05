# src/fpl_engine/features.py
from __future__ import annotations
import numpy as np
import pandas as pd
import requests
import certifi
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from difflib import get_close_matches


# =========================
# FPL difficulty multipliers
# =========================
def fdr_multiplier(teams_df: pd.DataFrame, opp_strength: float, median: float) -> float:
    ratio = opp_strength / median if median else 1.0
    return float(np.clip(1.2 / ratio, 0.6, 1.6))


def build_fixture_multipliers(
    players: pd.DataFrame,
    fixtures: pd.DataFrame,
    teams_df: pd.DataFrame,
    horizon_gws: list[int],
) -> pd.DataFrame:
    median = (
        teams_df["strength_overall_home"].median()
        + teams_df["strength_overall_away"].median()
    ) / 2
    rows = []
    for _, p in players.iterrows():
        tid = int(p.get("team_id")) if not pd.isna(p.get("team_id")) else None
        if tid is None:
            continue
        for gw in horizon_gws:
            fs = fixtures[
                (fixtures["event"] == gw)
                & ((fixtures["team_h"] == tid) | (fixtures["team_a"] == tid))
            ]
            if fs.empty:
                mult = 1.0
            else:
                f = fs.iloc[0]
                is_away = f["team_a"] == tid
                opp_id = int(f["team_h"] if is_away else f["team_a"])
                opp = teams_df.loc[teams_df["id"] == opp_id].iloc[0]
                opp_strength = (
                    opp["strength_overall_home"]
                    if is_away
                    else opp["strength_overall_away"]
                )
                mult = fdr_multiplier(teams_df, opp_strength, median)
            rows.append({"id": p["id"], "gw": gw, "fixture_mult": mult})
    return pd.DataFrame(rows)


# =========================
# Availability + EP model
# =========================
def availability_mult(row: pd.Series, season_gw: int | None = None) -> float:
    status = str(row.get("status", "a")).lower()
    if status in ("i", "s", "u"):
        return 0.0
    base = 0.9 if status == "a" else 0.6

    mins = float(row.get("minutes", 0) or 0)
    denom = 90.0 * float(max(1, (season_gw or 9) - 1))
    share = float(np.clip(mins / denom, 0.0, 1.0))

    sp90 = float(row.get("starts_per_90", 0) or 0)
    sp90 = float(np.clip(sp90 / 1.05, 0.0, 1.0))

    news = str(row.get("news") or "").lower()
    if any(k in news for k in ["hamstring", "knock", "injur", "illness", "susp"]):
        base *= 0.8

    p = 0.2 * base + 0.5 * share + 0.3 * sp90
    return float(np.clip(p, 0.0, 1.0))


SCORING = {
    "goal": {"FWD": 4, "MID": 5, "DEF": 6, "GKP": 6},
    "assist": 3,
    "clean_sheet": {"FWD": 0, "MID": 1, "DEF": 4, "GKP": 4},
    "saves_per_3": 1,
}


def expected_points_per_gw(
    row: pd.Series, fixture_mult: float, season_gw: int | None = None
) -> float:
    pos = row["position_name"]
    xg90 = float(row.get("expected_goals_per_90", 0) or 0)
    xa90 = float(row.get("expected_assists_per_90", 0) or 0)
    cs90 = float(row.get("clean_sheets_per_90", 0) or 0)
    sv90 = float(row.get("saves_per_90", 0) or 0)
    form = float(row.get("form", 0) or 0)

    pmins = availability_mult(row, season_gw=season_gw)

    if float(row.get("minutes", 0) or 0) < 180:
        xg90 *= 0.35
        xa90 *= 0.35
        cs90 *= 0.7

    goals_pts = xg90 * pmins * SCORING["goal"].get(pos, 4) * fixture_mult
    assists_pts = xa90 * pmins * SCORING["assist"] * fixture_mult

    if pos in ("DEF", "GKP"):
        cs_pts = cs90 * pmins * SCORING["clean_sheet"][pos] * (fixture_mult**0.5)
    elif pos == "MID":
        cs_pts = cs90 * pmins * SCORING["clean_sheet"]["MID"] * (fixture_mult**0.5)
    else:
        cs_pts = 0.0

    sv_pts = (sv90 * pmins) / 3.0 * SCORING["saves_per_3"] if pos == "GKP" else 0.0

    total = goals_pts + assists_pts + cs_pts + sv_pts
    total *= 1.0 + min(0.20, form / 40.0)
    return float(total)


def horizon_expected_points(
    players: pd.DataFrame,
    fx_mults: pd.DataFrame,
    horizon_gws: list[int],
    weights: list[float],
) -> pd.DataFrame:
    ep_rows = []
    for _, p in players.iterrows():
        pid = p["id"]
        row_mults = (
            fx_mults[fx_mults["id"] == pid].set_index("gw")["fixture_mult"].to_dict()
        )
        ep_by_gw, total = {}, 0.0
        for gw, w in zip(horizon_gws, weights):
            mult = float(row_mults.get(gw, 1.0))
            ep = expected_points_per_gw(p, mult, season_gw=gw)
            ep_by_gw[gw] = ep
            total += ep * w
        ep_by_gw["ep_horizon"] = total
        ep_by_gw["id"] = pid
        ep_rows.append(ep_by_gw)
    return pd.DataFrame(ep_rows)


# =========================
# Live table (BBC only) + mapping
# =========================
def _http_get(url: str, timeout: int = 20) -> str | None:
    sess = requests.Session()
    retries = Retry(
        total=3, backoff_factor=0.6, status_forcelist=(429, 500, 502, 503, 504)
    )
    sess.mount("https://", HTTPAdapter(max_retries=retries))
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        r = sess.get(url, timeout=timeout, verify=certifi.where(), headers=headers)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _parse_bbc_table(html: str) -> pd.DataFrame | None:
    """
    Parse the MAIN BBC Premier League table.
    Ensures exactly 20 clubs; returns columns ['Rank','Club'].
    """
    try:
        tables = pd.read_html(html)
    except Exception:
        return None

    best = None
    for t in tables:
        df = t.copy()
        cols_lc = [str(c).lower() for c in df.columns]

        # BBC usually exposes columns like: ['Pos','Team','P','W','D','L','F','A','GD','Pts',...]
        has_team = any(c in ("team", "club") for c in cols_lc)
        has_pts = any("pt" in c for c in cols_lc)  # pts/points
        if not has_team:
            continue

        # Standardize names
        rename = {}
        for c in df.columns:
            lc = str(c).lower()
            if lc in ("team", "club"):
                rename[c] = "Club"
            if lc in ("pos", "position", "#", "rank"):
                rename[c] = "Pos"
            if "pt" in lc:
                rename[c] = "Pts"
        df = df.rename(columns=rename)

        if "Club" not in df.columns:
            continue

        # Keep only club name column; derive order as rank if needed
        out = df[["Club"]].copy()
        out["Club"] = (
            out["Club"].astype(str).str.replace(r"\s+\d+$", "", regex=True).str.strip()
        )

        # Remove header/footer rows the parser might have picked up
        # Filter obvious junk rows (empty/NaN/duplicated header rows)
        out = out[out["Club"].str.len() > 0]
        out = out[~out["Club"].str.contains("Form", case=False)]
        out = out[~out["Club"].str.contains("Fixtures|Results", case=False)]

        # Deduplicate while keeping order
        out = out.drop_duplicates(subset=["Club"], keep="first").reset_index(drop=True)

        if len(out) == 20:
            out["Rank"] = np.arange(1, 21)
            best = out[["Rank", "Club"]]
            break

    return best


def get_live_table() -> pd.DataFrame:
    """BBC-only live standings. Returns 20 rows with ['Rank','Club']."""
    url = "https://www.bbc.com/sport/football/premier-league/table"
    html = _http_get(url)
    if not html:
        print("⚠️ [get_live_table] BBC fetch failed; no live ranks.")
        return pd.DataFrame(columns=["Rank", "Club"]).astype({"Rank": "Int64"})
    df = _parse_bbc_table(html)
    if df is None or df.empty or len(df) != 20:
        print("⚠️ [get_live_table] BBC parse failed; no live ranks.")
        return pd.DataFrame(columns=["Rank", "Club"]).astype({"Rank": "Int64"})
    print("✅ [get_live_table] Live ranks from BBC.")
    return df


# Canonical mappings → FPL names (covers all 20 teams)
GENERIC_TO_FPL = {
    "Arsenal": "Arsenal",
    "Manchester City": "Man City",
    "AFC Bournemouth": "Bournemouth",
    "Bournemouth": "Bournemouth",
    "Liverpool": "Liverpool",
    "Chelsea": "Chelsea",
    "Tottenham Hotspur": "Spurs",
    "Tottenham": "Spurs",
    "Sunderland": "Sunderland",
    "Crystal Palace": "Crystal Palace",
    "Manchester United": "Man Utd",
    "Man United": "Man Utd",
    "Manchester Utd": "Man Utd",
    "Brighton & Hove Albion": "Brighton",
    "Brighton and Hove Albion": "Brighton",
    "Aston Villa": "Aston Villa",
    "Everton": "Everton",
    "Brentford": "Brentford",
    "Newcastle United": "Newcastle",
    "Newcastle": "Newcastle",
    "Fulham": "Fulham",
    "Leeds United": "Leeds",
    "Leeds": "Leeds",
    "Burnley": "Burnley",
    "Nottingham Forest": "Nott'm Forest",
    "Nottingham": "Nott'm Forest",
    "West Ham United": "West Ham",
    "West Ham": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Wolverhampton": "Wolves",
    "Wolves": "Wolves",
    "Man City": "Man City",
}

ABBR_TO_FPL = {
    "ARS": "Arsenal",
    "MNC": "Man City",
    "BOU": "Bournemouth",
    "LIV": "Liverpool",
    "CHE": "Chelsea",
    "TOT": "Spurs",
    "SUN": "Sunderland",
    "CRY": "Crystal Palace",
    "MAN": "Man Utd",
    "BHA": "Brighton",
    "AVL": "Aston Villa",
    "EVE": "Everton",
    "BRE": "Brentford",
    "NEW": "Newcastle",
    "FUL": "Fulham",
    "LEE": "Leeds",
    "BUR": "Burnley",
    "NFO": "Nott'm Forest",
    "WHU": "West Ham",
    "WOL": "Wolves",
}


def _map_name_to_fpl(name: str, fpl_names: list[str]) -> str | None:
    if name in GENERIC_TO_FPL:
        cand = GENERIC_TO_FPL[name]
        if cand in fpl_names:
            return cand
    if name in ABBR_TO_FPL:
        cand = ABBR_TO_FPL[name]
        if cand in fpl_names:
            return cand
    if name in fpl_names:
        return name
    hit = get_close_matches(name, fpl_names, n=1, cutoff=0.6)
    return hit[0] if hit else None


def build_live_rank_map(teams_df: pd.DataFrame) -> dict:
    """
    Build {FPL_team_name: live_rank} from BBC standings.
    Ensures all 20 clubs are handled (mapping + fuzzy as last resort).
    """
    table = get_live_table()
    fpl_names = teams_df["name"].tolist()
    ranks: dict[str, int] = {}
    for _, r in table.iterrows():
        club_raw = str(r["Club"]).strip()
        fpl_name = _map_name_to_fpl(club_raw, fpl_names)
        if not fpl_name:
            fpl_name = _map_name_to_fpl(club_raw.upper(), fpl_names)  # try abbr
        if fpl_name:
            ranks[fpl_name] = int(r["Rank"])
    return ranks


# =========================
# Adjusted difficulty (live ranks + FPL strength)
# =========================
def adjusted_fixture_multiplier(
    teams_df: pd.DataFrame,
    opp_id: int,
    is_home: bool,
    live_rank_map: dict,
    w_fpl: float = 0.4,
    w_rank: float = 0.6,
    clip_min: float = 0.65,
    clip_max: float = 1.55,
) -> float:
    row = teams_df.loc[teams_df["id"] == opp_id].iloc[0]
    opp_name = row["name"]
    live_rank = live_rank_map.get(opp_name, None)

    s = float(row["strength_overall_away"] if is_home else row["strength_overall_home"])
    fpl_power = (s - 1.0) / 4.0  # 1..5 → 0..1

    if live_rank is None or pd.isna(live_rank):
        rank_power = fpl_power
    else:
        N = teams_df.shape[0]
        rank_power = (N - int(live_rank) + 1) / N

    opp_power = w_fpl * fpl_power + w_rank * rank_power

    s_home = teams_df["strength_overall_home"].astype(float)
    s_away = teams_df["strength_overall_away"].astype(float)
    mean_fpl_power = (
        ((s_home - 1.0) / 4.0).mean() + ((s_away - 1.0) / 4.0).mean()
    ) / 2.0
    league_avg_power = w_fpl * mean_fpl_power + w_rank * 0.5

    mult = float(np.clip(league_avg_power / max(1e-6, opp_power), clip_min, clip_max))
    return mult


def build_adjusted_fixture_multipliers(
    players_df: pd.DataFrame,
    fixtures_df: pd.DataFrame,
    teams_df: pd.DataFrame,
    horizon_gws: list[int],
    live_ranks: dict,
) -> pd.DataFrame:
    rows = []
    fx_by_gw = {g: fixtures_df[fixtures_df["event"] == g] for g in horizon_gws}

    for _, p in players_df.iterrows():
        tid = int(p["team_id"])
        for gw in horizon_gws:
            fx = fx_by_gw[gw]
            match = fx[(fx["team_h"] == tid) | (fx["team_a"] == tid)]
            if match.empty:
                mult = 1.0
            else:
                f = match.iloc[0]
                is_away = f["team_a"] == tid
                opp_id = int(f["team_h"] if is_away else f["team_a"])
                mult = adjusted_fixture_multiplier(
                    teams_df, opp_id, is_home=not is_away, live_rank_map=live_ranks
                )
            rows.append({"id": p["id"], "gw": gw, "fixture_mult": mult})
    return pd.DataFrame(rows)
