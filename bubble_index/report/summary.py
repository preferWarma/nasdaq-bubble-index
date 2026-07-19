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


def _available_inputs(
    row: pd.Series, candidates: tuple[tuple[str, str], ...]
) -> list[str]:
    return [
        label
        for label, column in candidates
        if column in row.index and not pd.isna(row.get(column))
    ]


def active_factor_inputs(row: pd.Series, factor: Factor) -> list[str]:
    """Describe the bottom-level indicators used by the current factor score."""
    if factor.key == "valuation":
        direct_columns = (("PE", "nasdaq_pe"), ("PS", "nasdaq_ps"))
        if any(column in row.index for _, column in direct_columns):
            return _available_inputs(row, direct_columns)
        return _available_inputs(
            row,
            (("Nasdaq / GDP", "nasdaq_to_gdp"), ("Nasdaq / M2", "nasdaq_to_m2")),
        )
    if factor.key == "trend_momentum":
        return _available_inputs(
            row,
            (
                ("偏离 200 日均线", "trend_score"),
                ("过去一年涨幅", "return_score"),
            ),
        )
    if factor.key == "style_crowding":
        preferred = _available_inputs(row, (("QQQ / SPY 一年变化", "qqq_spy_score"),))
        return preferred or _available_inputs(
            row, (("Nasdaq / S&P 500 一年变化", "relative_score"),)
        )
    if factor.key == "concentration":
        if "top10_weight" in row.index:
            return _available_inputs(row, (("Top 10 权重", "concentration_score"),))
        return _available_inputs(
            row,
            (
                ("巨头篮子 / QQQ", "mega_cap_relative"),
                ("巨头篮子 / QQQ 一年变化", "mega_cap_relative_1y"),
            ),
        )
    if factor.key == "sentiment_speculation":
        inputs = _available_inputs(row, (("VIX 低波动", "complacency_score"),))
        if "equity_put_call" in row.index:
            return _available_inputs(row, (("股票 Put/Call", "speculation_score"),)) + inputs
        return _available_inputs(
            row,
            (
                ("QQQ 成交量强度", "qqq_volume_intensity"),
                ("ARKK / QQQ", "arkk_qqq"),
                ("ARKK / QQQ 一年变化", "arkk_qqq_1y"),
            ),
        ) + inputs
    if factor.key == "macro_fragility":
        return _available_inputs(
            row,
            (
                ("10 年期美债收益率", "rate_pressure_score"),
                ("M2 同比", "liquidity_score"),
                ("融资余额同比", "margin_score"),
            ),
        )
    return []


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
                "active_inputs": active_factor_inputs(latest, factor),
                "input_candidates": list(factor.input_candidates),
                "source_text": factor.source_text,
                "calculation_text": factor.calculation_text,
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
