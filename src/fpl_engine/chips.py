from __future__ import annotations
import pandas as pd


def plan_chips(fixtures_df: pd.DataFrame) -> dict:
    """
    Lightweight chips planner. Expects FPL fixtures with 'event' (GW) and status.
    """
    # Identify DGWs: teams appearing twice in same GW
    dgw = (
        fixtures_df.groupby(["event", "team_h"])
        .size()
        .reset_index(name="cnt_h")
        .merge(
            fixtures_df.groupby(["event", "team_a"]).size().reset_index(name="cnt_a"),
            left_on=["event", "team_h"],
            right_on=["event", "team_a"],
            how="outer",
        )
        .fillna(0)
    )
    # Simple heuristics
    likely_dgw_weeks = sorted(
        fixtures_df.groupby("event")
        .apply(
            lambda x: int(
                (
                    x.duplicated(subset=["team_h"]).any()
                    or x.duplicated(subset=["team_a"]).any()
                )
            )
        )
        .loc[lambda s: s == 1]
        .index.tolist()
    )
    likely_bgw_weeks = sorted(
        fixtures_df.groupby("event")
        .size()
        .loc[lambda s: s < s.median() * 0.7]
        .index.tolist()
    )
    return {"dgw_weeks": likely_dgw_weeks, "bgw_weeks": likely_bgw_weeks}
