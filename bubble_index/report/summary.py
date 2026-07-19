"""Latest-score summary helpers."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..factors import Factor

logger = logging.getLogger(__name__)


def risk_label(score: float) -> tuple[str, str]:
    if pd.isna(score):
        return "数据不足", "#64748b"
    if score >= 85:
        return "极端泡沫风险", "#991b1b"
    if score >= 75:
        return "高泡沫风险", "#dc2626"
    if score >= 60:
        return "明显偏热", "#f59e0b"
    if score >= 40:
        return "中性", "#10b981"
    return "偏冷", "#059669"


def factor_reason(factor: Factor, score: float) -> str:
    if pd.isna(score):
        return "该因子当前数据不足，未参与总分计算。"
    if score >= 80:
        return factor.hot_text
    if score >= 60:
        return factor.warm_text
    return factor.cool_text


def latest_complete_row(data: pd.DataFrame) -> pd.Series:
    complete = data.dropna(subset=["bubble_score"])
    if complete.empty:
        logger.error("No complete bubble score found in scored data")
        raise ValueError("Not enough data to calculate a bubble score")
    return complete.iloc[-1]


def previous_complete_row(data: pd.DataFrame) -> pd.Series | None:
    complete = data.dropna(subset=["bubble_score"])
    if len(complete) < 2:
        return None
    return complete.iloc[-2]


def build_summary(
    latest: pd.Series, factors: list[Factor], previous: pd.Series | None = None
) -> dict[str, object]:
    logger.debug("Building summary for %s", latest.name)
    label, color = risk_label(float(latest["bubble_score"]))
    factor_items = []
    for factor in factors:
        if factor.score_column not in latest.index:
            continue
        raw = latest.get(factor.raw_column, np.nan)
        score = latest.get(factor.score_column, np.nan)
        previous_score = (
            previous.get(factor.score_column, np.nan)
            if previous is not None and factor.score_column in previous.index
            else np.nan
        )
        factor_items.append(
            {
                "key": factor.key,
                "name": factor.name,
                "weight": factor.weight,
                "raw_value": None if pd.isna(raw) else float(raw),
                "display_value": factor.value_formatter(raw),
                "score": None if pd.isna(score) else round(float(score), 1),
                "previous_score": None
                if pd.isna(previous_score)
                else round(float(previous_score), 1),
                "reason": factor_reason(factor, score),
            }
        )
    return {
        "date": latest.name.strftime("%Y-%m-%d"),
        "previous_date": None if previous is None else previous.name.strftime("%Y-%m-%d"),
        "bubble_score": round(float(latest["bubble_score"]), 1),
        "risk_label": label,
        "risk_color": color,
        "active_factor_count": int(latest["active_factor_count"]),
        "factors": factor_items,
    }
