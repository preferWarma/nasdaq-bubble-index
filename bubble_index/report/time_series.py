"""Time-series utilities used by report rendering."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .constants import BUBBLE_STAGE_YEARS

logger = logging.getLogger(__name__)


def find_stage_points(
    series: pd.Series, years: tuple[int, ...] = BUBBLE_STAGE_YEARS
) -> list[tuple[int, pd.Timestamp, float]]:
    points = []
    for year in years:
        year_slice = series[series.index.year == year]
        if year_slice.empty:
            logger.warning("No bubble score available for chart annotation year: %s", year)
            continue
        point_date = year_slice.idxmax()
        points.append((year, point_date, float(year_slice.loc[point_date])))
    return points


def trim_to_recent_years(series: pd.Series, years: int = 20) -> pd.Series:
    if series.empty:
        return series
    cutoff = series.index[-1] - pd.DateOffset(years=years)
    return series.loc[series.index >= cutoff]


def trim_frame_to_range(
    data: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    return data.loc[(data.index >= start) & (data.index <= end)]


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


def x_axis_ticks(series: pd.Series) -> list[tuple[int, str, str]]:
    index = series.index
    first = index[0]
    last = index[-1]
    ticks = [(0, first.strftime("%Y-%m"), "start")]
    used_positions = {0}

    target = first + pd.DateOffset(years=3)
    while target < last:
        position = nearest_index_position(index, target)
        if position not in used_positions and position != len(index) - 1:
            ticks.append((position, index[position].strftime("%Y"), "middle"))
            used_positions.add(position)
        target += pd.DateOffset(years=3)

    ticks.append((len(index) - 1, last.strftime("%Y-%m-%d"), "end"))
    return ticks


def scaled_index_series(data: pd.DataFrame, primary_col: str, proxy_col: str) -> pd.Series:
    primary = pd.to_numeric(data.get(primary_col, pd.Series(index=data.index)), errors="coerce")
    proxy = pd.to_numeric(data.get(proxy_col, pd.Series(index=data.index)), errors="coerce")
    if proxy.notna().any():
        overlap = pd.concat([primary, proxy.replace(0, np.nan)], axis=1).dropna()
        ratio = float((overlap.iloc[:, 0] / overlap.iloc[:, 1]).median()) if not overlap.empty else 1.0
        primary = primary.combine_first(proxy * ratio)
    return primary


def future_max_drawdown(series: pd.Series, point_date: pd.Timestamp, years: int = 3) -> float | None:
    prices = series.dropna()
    if prices.empty:
        return None
    position = nearest_index_position(prices.index, point_date)
    start_date = prices.index[position]
    window = prices.loc[start_date : start_date + pd.DateOffset(years=years)]
    if len(window) < 2:
        return None
    drawdowns = window / window.cummax() - 1
    return float(drawdowns.min())
