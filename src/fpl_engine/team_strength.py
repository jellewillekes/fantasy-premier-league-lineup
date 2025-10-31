from __future__ import annotations
import pandas as pd
import numpy as np

def compute_team_strength(matches_df: pd.DataFrame, standings_df: pd.DataFrame,
                          clip: tuple[float, float] = (0.75, 1.25)) -> pd.DataFrame:
    """
    Returns: DataFrame with columns: team, atk_home, atk_away, def_home, def_away
    Uses football-data.org matches to compute GF/GA per match by venue and blends a small standings prior.
    """
    if matches_df is None or matches_df.empty:
        return pd.DataFrame(columns=["team","atk_home","atk_away","def_home","def_away"])

    df = matches_df.dropna(subset=["homeTeam","awayTeam"]).copy()
    # Only FINISHED matches for GF/GA
    fin = df[df["status"] == "FINISHED"].copy()

    # Home stats
    home = fin.groupby("homeTeam").agg(
        games=("match_id", "count"),
        gf=("score_full_home", "mean"),
        ga=("score_full_away", "mean"),
    ).rename_axis("team").reset_index()
    home["venue"] = "home"

    # Away stats
    away = fin.groupby("awayTeam").agg(
        games=("match_id", "count"),
        gf=("score_full_away", "mean"),
        ga=("score_full_home", "mean"),
    ).rename_axis("team").reset_index()
    away["venue"] = "away"

    agg = pd.concat([home, away], ignore_index=True)
    if agg.empty:
        # no finished matches yet; return neutral strengths
        teams = pd.unique(df[["homeTeam","awayTeam"]].values.ravel("K"))
        return pd.DataFrame({"team": teams, "atk_home":1.0,"atk_away":1.0,"def_home":1.0,"def_away":1.0})

    league_gf = agg["gf"].mean()
    league_ga = agg["ga"].mean()

    # attack: higher gf better (>1), defense: lower ga better (>1)
    agg["atk"] = (agg["gf"] / max(1e-6, league_gf)).clip(*clip)
    agg["def"] = (max(1e-6, league_ga) / agg["ga"]).replace([np.inf, -np.inf], 1.0).clip(*clip)

    atk = agg.pivot(index="team", columns="venue", values="atk").rename(columns={"home":"atk_home","away":"atk_away"})
    ddf = agg.pivot(index="team", columns="venue", values="def").rename(columns={"home":"def_home","away":"def_away"})
    out = atk.join(ddf, how="outer").reset_index()

    # Blend with small prior from standings (points per game)
    if standings_df is not None and not standings_df.empty:
        tbl = standings_df.copy()
        tbl["ppg"] = tbl["points"] / tbl["played"].replace(0, 1)
        tbl["prior"] = (tbl["ppg"] / tbl["ppg"].mean()).clip(*clip)
        out = out.merge(tbl[["team","prior"]], on="team", how="left")
        for col in ["atk_home","atk_away","def_home","def_away"]:
            out[col] = 0.85*out[col].fillna(1.0) + 0.15*out["prior"].fillna(1.0)
        out = out.drop(columns=["prior"], errors="ignore")

    return out.fillna(1.0)
