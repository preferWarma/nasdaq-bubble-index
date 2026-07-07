"""Factor engineering and bubble score calculation."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .constants import MEGA_CAP_TICKERS
from .factors import Factor

logger = logging.getLogger(__name__)


def rolling_percentile(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    def score(values: np.ndarray) -> float:
        valid = values[~np.isnan(values)]
        if len(valid) < min_periods:
            return np.nan
        last = valid[-1]
        return float(np.sum(valid <= last) / len(valid) * 100)

    return series.rolling(window=window, min_periods=min_periods).apply(score, raw=True)


def normalize_percent_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return np.where(numeric > 1.5, numeric / 100, numeric)


def first_existing_column(data: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in data.columns), None)


def mean_existing_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    existing = [column for column in columns if column in data.columns]
    if not existing:
        return pd.Series(np.nan, index=data.index)
    return data[existing].mean(axis=1)


def first_available_series(data: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    existing = [column for column in columns if column in data.columns]
    if not existing:
        return pd.Series(np.nan, index=data.index)
    series = data[existing[0]]
    for column in existing[1:]:
        series = series.combine_first(data[column])
    return series


def weighted_factor_score(
    data: pd.DataFrame, factors: list[Factor]
) -> tuple[pd.Series, pd.Series]:
    score_cols = [factor.score_column for factor in factors if factor.score_column in data.columns]
    logger.debug("Available score columns: %s", score_cols)
    weighted_sum = pd.Series(0.0, index=data.index)
    active_weight = pd.Series(0.0, index=data.index)
    for factor in factors:
        if factor.score_column not in data.columns:
            continue
        available = data[factor.score_column].notna()
        weighted_sum = weighted_sum + data[factor.score_column].fillna(0) * factor.weight
        active_weight = active_weight + available.astype(float) * factor.weight

    score = pd.Series(np.nan, index=data.index)
    score.loc[active_weight > 0] = weighted_sum.loc[active_weight > 0] / active_weight.loc[
        active_weight > 0
    ]
    active_factor_count = data[score_cols].notna().sum(axis=1) if score_cols else pd.Series(0, index=data.index)
    return score, active_factor_count


def compute_scores(
    frame: pd.DataFrame, factors: list[Factor], window_years: int = 20
) -> pd.DataFrame:
    logger.info("Computing factor scores")
    data = frame.copy().sort_index()
    window = int(window_years * 252)
    min_periods = min(756, max(126, window // 3))
    logger.debug("Score window=%d trading days, min_periods=%d", window, min_periods)

    data["nasdaq_200dma"] = data["nasdaq"].rolling(200, min_periods=160).mean()
    data["trend_deviation"] = data["nasdaq"] / data["nasdaq_200dma"] - 1
    data["nasdaq_1y_return"] = data["nasdaq"].pct_change(252)
    data["relative_strength"] = data["nasdaq"] / data["sp500"]
    data["relative_strength_1y"] = data["relative_strength"].pct_change(252)
    data["m2_yoy"] = data["m2"].pct_change(252)

    if "gdp" in data.columns:
        data["nasdaq_to_gdp"] = data["nasdaq"] / data["gdp"]
    if "m2" in data.columns:
        data["nasdaq_to_m2"] = data["nasdaq"] / data["m2"]

    if {"qqq_close", "spy_close"}.issubset(data.columns):
        data["qqq_spy"] = data["qqq_close"] / data["spy_close"]
        data["qqq_spy_1y"] = data["qqq_spy"].pct_change(252)

    mega_cols = [f"{ticker.lower()}_close" for ticker in MEGA_CAP_TICKERS]
    mega_cols = [col for col in mega_cols if col in data.columns]
    if mega_cols and "qqq_close" in data.columns:
        normalized = pd.DataFrame(index=data.index)
        for col in mega_cols:
            first = data[col].dropna()
            if not first.empty:
                normalized[col] = data[col] / first.iloc[0]
        qqq_base = data["qqq_close"].dropna()
        if not normalized.empty and not qqq_base.empty:
            data["mega_cap_basket"] = normalized.mean(axis=1)
            data["mega_cap_relative"] = data["mega_cap_basket"] / (
                data["qqq_close"] / qqq_base.iloc[0]
            )
            data["mega_cap_relative_1y"] = data["mega_cap_relative"].pct_change(252)

    if {"arkk_close", "qqq_close"}.issubset(data.columns):
        data["arkk_qqq"] = data["arkk_close"] / data["qqq_close"]
        data["arkk_qqq_1y"] = data["arkk_qqq"].pct_change(252)
    if "qqq_volume" in data.columns:
        data["qqq_volume_intensity"] = data["qqq_volume"] / data["qqq_volume"].rolling(
            252, min_periods=160
        ).mean()

    pe_col = first_existing_column(data, ("nasdaq_pe", "pe", "pe_ratio"))
    ps_col = first_existing_column(data, ("nasdaq_ps", "ps", "price_to_sales", "ps_ratio"))
    if pe_col:
        logger.info("Using PE column for valuation: %s", pe_col)
        data["nasdaq_pe"] = data[pe_col]
    if ps_col:
        logger.info("Using PS column for valuation: %s", ps_col)
        data["nasdaq_ps"] = data[ps_col]

    top10_col = first_existing_column(data, ("top10_weight", "nasdaq_top10_weight"))
    if top10_col:
        logger.info("Using top10 concentration column: %s", top10_col)
        data["top10_weight"] = normalize_percent_series(data[top10_col])

    put_call_col = first_existing_column(
        data, ("equity_put_call", "put_call", "equity_put_call_ratio")
    )
    if put_call_col:
        logger.info("Using put/call sentiment column: %s", put_call_col)
        data["equity_put_call"] = data[put_call_col]

    data["trend_score"] = rolling_percentile(data["trend_deviation"], window, min_periods)
    data["return_score"] = rolling_percentile(data["nasdaq_1y_return"], window, min_periods)
    data["relative_score"] = rolling_percentile(
        data["relative_strength_1y"], window, min_periods
    )
    data["complacency_score"] = 100 - rolling_percentile(data["vix"], window, min_periods)
    data["rate_pressure_score"] = rolling_percentile(data["dgs10"], window, min_periods)
    data["liquidity_score"] = rolling_percentile(data["m2_yoy"], window, min_periods)

    valuation_scores = []
    if "nasdaq_pe" in data.columns:
        valuation_scores.append(rolling_percentile(data["nasdaq_pe"], window, min_periods))
    if "nasdaq_ps" in data.columns:
        valuation_scores.append(rolling_percentile(data["nasdaq_ps"], window, min_periods))
    if not valuation_scores:
        if "nasdaq_to_gdp" in data.columns:
            valuation_scores.append(rolling_percentile(data["nasdaq_to_gdp"], window, min_periods))
        if "nasdaq_to_m2" in data.columns:
            valuation_scores.append(rolling_percentile(data["nasdaq_to_m2"], window, min_periods))
    if valuation_scores:
        data["valuation_score"] = pd.concat(valuation_scores, axis=1).mean(axis=1)
        if "nasdaq_pe" in data.columns:
            data["valuation_proxy"] = data["nasdaq_pe"]
        elif "nasdaq_ps" in data.columns:
            data["valuation_proxy"] = data["nasdaq_ps"]
        elif "nasdaq_to_gdp" in data.columns:
            data["valuation_proxy"] = data["nasdaq_to_gdp"]

    if "qqq_spy_1y" in data.columns:
        data["qqq_spy_score"] = rolling_percentile(data["qqq_spy_1y"], window, min_periods)

    if "top10_weight" in data.columns:
        data["concentration_proxy"] = data["top10_weight"]
        data["concentration_score"] = rolling_percentile(data["top10_weight"], window, min_periods)
    elif "mega_cap_relative_1y" in data.columns:
        concentration_scores = []
        if "mega_cap_relative" in data.columns:
            concentration_scores.append(
                rolling_percentile(data["mega_cap_relative"], window, min_periods)
            )
        data["concentration_proxy"] = data["mega_cap_relative_1y"]
        concentration_scores.append(
            rolling_percentile(data["mega_cap_relative_1y"], window, min_periods)
        )
        data["concentration_score"] = pd.concat(concentration_scores, axis=1).mean(axis=1)

    speculation_scores = []
    if "equity_put_call" in data.columns:
        speculation_scores.append(100 - rolling_percentile(data["equity_put_call"], window, min_periods))
        data["speculation_proxy"] = data["equity_put_call"]
    else:
        if "qqq_volume_intensity" in data.columns:
            speculation_scores.append(
                rolling_percentile(data["qqq_volume_intensity"], window, min_periods)
            )
            data["speculation_proxy"] = data["qqq_volume_intensity"]
        if "arkk_qqq_1y" in data.columns:
            if "arkk_qqq" in data.columns:
                speculation_scores.append(rolling_percentile(data["arkk_qqq"], window, min_periods))
                data["speculation_proxy"] = data["arkk_qqq"]
            speculation_scores.append(rolling_percentile(data["arkk_qqq_1y"], window, min_periods))
            if "speculation_proxy" not in data.columns:
                data["speculation_proxy"] = data["arkk_qqq_1y"]
    if speculation_scores:
        data["speculation_score"] = pd.concat(speculation_scores, axis=1).mean(axis=1)

    if "margin_debt_yoy" in data.columns:
        data["margin_score"] = rolling_percentile(data["margin_debt_yoy"], window, min_periods)

    data["trend_momentum_score"] = mean_existing_columns(data, ("trend_score", "return_score"))
    data["trend_momentum_proxy"] = data["trend_momentum_score"]
    data["style_crowding_score"] = first_available_series(
        data, ("qqq_spy_score", "relative_score")
    )
    data["style_crowding_proxy"] = first_available_series(
        data, ("qqq_spy_1y", "relative_strength_1y")
    )
    data["sentiment_speculation_score"] = mean_existing_columns(
        data, ("speculation_score", "complacency_score")
    )
    data["sentiment_speculation_proxy"] = data["sentiment_speculation_score"]
    data["macro_fragility_score"] = mean_existing_columns(
        data, ("rate_pressure_score", "liquidity_score", "margin_score")
    )
    data["macro_fragility_proxy"] = data["macro_fragility_score"]

    data["bubble_score"], data["active_factor_count"] = weighted_factor_score(data, factors)
    latest_scores = data.dropna(subset=["bubble_score"])
    if latest_scores.empty:
        logger.warning("Score calculation complete, but no complete bubble score is available")
    else:
        latest = latest_scores.iloc[-1]
        logger.info(
            "Score calculation complete: latest_date=%s, score=%.1f, active_groups=%d",
            latest.name.strftime("%Y-%m-%d"),
            float(latest["bubble_score"]),
            int(latest["active_factor_count"]),
        )
    return data
