"""Formatting helpers for report values."""

from __future__ import annotations

import json

import pandas as pd


def format_axis_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:.0f}"


def format_score(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    numeric = float(value)
    if abs(numeric - round(numeric)) < 0.05:
        return f"{numeric:.0f}"
    return f"{numeric:.1f}"


def format_signed_percent(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value * 100:+.1f}%"


def format_plain_percent(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value * 100:.1f}%"


def format_decimal(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


def chart_number(value: float | int | None, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def script_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
