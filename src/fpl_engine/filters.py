# src/fpl_engine/filters.py
from __future__ import annotations
import pandas as pd


def filter_min_sixty(players_df: pd.DataFrame, min_matches: int = 5) -> pd.DataFrame:
    """
    Keep only players who played at least `min_matches` matches
    and averaged at least 60 minutes per match.
    (Pure pandas filter — no network calls or caching.)
    """
    df = players_df.copy()

    # Ensure numeric
    df["starts"] = pd.to_numeric(df.get("starts"), errors="coerce").fillna(0)
    df["minutes"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(0)

    # Compute average minutes per start (avoid div/0)
    df["avg_minutes_per_start"] = df["minutes"] / df["starts"].replace(0, pd.NA)

    # Keep only players with enough starts and good avg minutes
    mask = (df["starts"] >= min_matches) & (df["avg_minutes_per_start"] >= 60)

    return df.loc[mask].reset_index(drop=True)
