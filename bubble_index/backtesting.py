"""Backtest helpers for the grouped bubble score."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BACKTEST_STAGE_REFERENCES = (
    (2000, "互联网泡沫"),
    (2007, "金融危机前夕"),
    (2018, "紧缩/科技股回撤"),
    (2020, "疫情冲击前"),
    (2021, "成长股泡沫"),
    (2022, "加息杀估值"),
)


def clean_float(value: float | int | None, digits: int = 4) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def scaled_index_series(data: pd.DataFrame, primary_col: str, proxy_col: str) -> pd.Series:
    primary = pd.to_numeric(data.get(primary_col, pd.Series(index=data.index)), errors="coerce")
    proxy = pd.to_numeric(data.get(proxy_col, pd.Series(index=data.index)), errors="coerce")
    if proxy.notna().any():
        overlap = pd.concat([primary, proxy.replace(0, np.nan)], axis=1).dropna()
        ratio = float((overlap.iloc[:, 0] / overlap.iloc[:, 1]).median()) if not overlap.empty else 1.0
        primary = primary.combine_first(proxy * ratio)
    return primary


def nearest_index_position(index: pd.DatetimeIndex, target: pd.Timestamp) -> int:
    position = int(index.searchsorted(target))
    if position <= 0:
        return 0
    if position >= len(index):
        return len(index) - 1
    before = position - 1
    after = position
    if abs(index[after] - target) < abs(target - index[before]):
        return after
    return before


def future_max_drawdown(
    prices: pd.Series,
    point_date: pd.Timestamp,
    years: int = 3,
    require_full_window: bool = False,
) -> float | None:
    prices = prices.dropna()
    if prices.empty:
        return None
    position = nearest_index_position(prices.index, point_date)
    start_date = prices.index[position]
    end_date = start_date + pd.DateOffset(years=years)
    window = prices.loc[start_date:end_date]
    if len(window) < 2:
        return None
    if require_full_window and window.index[-1] < end_date:
        return None
    drawdowns = window / window.cummax() - 1
    return float(drawdowns.min())


def monthly_last_frame(data: pd.DataFrame, score_column: str, prices: pd.Series) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "score": pd.to_numeric(data.get(score_column, pd.Series(index=data.index)), errors="coerce"),
            "price": prices,
        },
        index=data.index,
    ).dropna()
    if frame.empty:
        return frame
    return frame.resample("ME").last().dropna()


def future_drawdown_frame(
    data: pd.DataFrame, score_column: str, prices: pd.Series, years: int
) -> pd.DataFrame:
    monthly = monthly_last_frame(data, score_column, prices)
    if monthly.empty:
        return monthly

    drawdowns = []
    for point_date in monthly.index:
        drawdowns.append(
            future_max_drawdown(prices, point_date, years=years, require_full_window=True)
        )
    monthly["future_max_drawdown"] = drawdowns
    return monthly.dropna(subset=["future_max_drawdown"])


def threshold_summary(frame: pd.DataFrame, threshold: float) -> dict[str, object]:
    subset = frame[frame["score"] >= threshold]
    if subset.empty:
        return {
            "threshold": threshold,
            "count": 0,
            "avg_score": None,
            "avg_future_max_drawdown": None,
            "hit_rate_25pct_drawdown": None,
        }
    return {
        "threshold": threshold,
        "count": int(len(subset)),
        "avg_score": clean_float(subset["score"].mean(), 2),
        "avg_future_max_drawdown": clean_float(subset["future_max_drawdown"].mean(), 4),
        "hit_rate_25pct_drawdown": clean_float((subset["future_max_drawdown"] <= -0.25).mean(), 4),
    }


def top_quantile_summary(frame: pd.DataFrame, quantile: float = 0.9) -> dict[str, object]:
    if frame.empty:
        return {
            "quantile": quantile,
            "score_threshold": None,
            "count": 0,
            "avg_score": None,
            "avg_future_max_drawdown": None,
            "hit_rate_25pct_drawdown": None,
        }
    threshold = float(frame["score"].quantile(quantile))
    subset = frame[frame["score"] >= threshold]
    return {
        "quantile": quantile,
        "score_threshold": clean_float(threshold, 2),
        "count": int(len(subset)),
        "avg_score": clean_float(subset["score"].mean(), 2),
        "avg_future_max_drawdown": clean_float(subset["future_max_drawdown"].mean(), 4),
        "hit_rate_25pct_drawdown": clean_float((subset["future_max_drawdown"] <= -0.25).mean(), 4),
    }


def stage_peak_summary(
    data: pd.DataFrame, score_column: str, prices: pd.Series, years: int
) -> list[dict[str, object]]:
    score_series = pd.to_numeric(data.get(score_column, pd.Series(index=data.index)), errors="coerce")
    score_series = score_series.dropna()
    stages = []
    for year, label in BACKTEST_STAGE_REFERENCES:
        year_slice = score_series[score_series.index.year == year]
        if year_slice.empty:
            logger.debug("No backtest stage data for %s using %s", year, score_column)
            continue
        point_date = year_slice.idxmax()
        stages.append(
            {
                "year": year,
                "label": label,
                "peak_date": point_date.strftime("%Y-%m-%d"),
                "score": clean_float(year_slice.loc[point_date], 2),
                "future_max_drawdown": clean_float(
                    future_max_drawdown(prices, point_date, years=years), 4
                ),
            }
        )
    return stages


def model_backtest_summary(
    data: pd.DataFrame,
    score_column: str,
    label: str,
    prices: pd.Series,
    years: int,
) -> dict[str, object]:
    frame = future_drawdown_frame(data, score_column, prices, years)
    correlation = None
    if len(frame) >= 3:
        correlation = frame["score"].corr(-frame["future_max_drawdown"])

    return {
        "label": label,
        "score_column": score_column,
        "monthly_observations": int(len(frame)),
        "score_to_future_drawdown_severity_corr": clean_float(correlation, 4),
        "avg_future_max_drawdown_all_months": clean_float(
            frame["future_max_drawdown"].mean() if not frame.empty else None, 4
        ),
        "top_decile": top_quantile_summary(frame),
        "score_ge_75": threshold_summary(frame, 75),
        "score_ge_85": threshold_summary(frame, 85),
        "stage_peaks": stage_peak_summary(data, score_column, prices, years),
    }


def build_backtest_summary(data: pd.DataFrame, years: int = 3) -> dict[str, object]:
    logger.info("Building backtest summary")
    prices = scaled_index_series(data, "nasdaq", "qqq_close").dropna()
    return {
        "future_window_years": years,
        "evaluation_frequency": "month-end",
        "drawdown_target": "Nasdaq future maximum drawdown",
        "model": model_backtest_summary(data, "bubble_score", "6 组因子方案", prices, years),
    }
