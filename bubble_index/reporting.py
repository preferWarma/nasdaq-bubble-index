"""Summary, chart, and file output rendering."""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .factors import FACTORS, Factor

logger = logging.getLogger(__name__)

BUBBLE_STAGE_YEARS = (2007, 2018, 2020, 2021, 2022)
BUBBLE_STAGE_NOTES = {
    2007: "金融危机前夕",
    2018: "紧缩/科技股回撤",
    2020: "疫情冲击前",
    2021: "成长股泡沫",
    2022: "加息杀估值",
}
HISTORICAL_REFERENCE_STAGES = (
    (2000, "互联网泡沫"),
    *((year, BUBBLE_STAGE_NOTES[year]) for year in BUBBLE_STAGE_YEARS),
)


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


def scaled_index_series(data: pd.DataFrame, primary_col: str, proxy_col: str) -> pd.Series:
    primary = pd.to_numeric(data.get(primary_col, pd.Series(index=data.index)), errors="coerce")
    proxy = pd.to_numeric(data.get(proxy_col, pd.Series(index=data.index)), errors="coerce")
    if proxy.notna().any():
        overlap = pd.concat([primary, proxy.replace(0, np.nan)], axis=1).dropna()
        ratio = float((overlap.iloc[:, 0] / overlap.iloc[:, 1]).median()) if not overlap.empty else 1.0
        primary = primary.combine_first(proxy * ratio)
    return primary


def gauge_angle(score: float) -> float:
    clamped = float(np.clip(score, 0, 100))
    return 210 - clamped / 100 * 240


def point_from_angle(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    radians = np.deg2rad(angle)
    return cx + radius * float(np.cos(radians)), cy - radius * float(np.sin(radians))


def gauge_point(cx: float, cy: float, radius: float, score: float) -> tuple[float, float]:
    return point_from_angle(cx, cy, radius, gauge_angle(score))


def gauge_arc_points(cx: float, cy: float, radius: float, start: float, end: float) -> str:
    scores = np.linspace(start, end, 34)
    return " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (gauge_point(cx, cy, radius, score) for score in scores)
    )


def svg_score_gauge(score: float, color: str, width: int = 470, height: int = 330) -> str:
    cx, cy = 235, 220
    arc_radius = 142
    needle_x, needle_y = gauge_point(cx, cy, 118, score)
    score_text = format_score(score)

    bands = [
        (0.7, 39.3, "#18b981"),
        (40.7, 59.3, "#14b8a6"),
        (60.7, 79.3, "#f59e0b"),
        (80.7, 89.3, "#dc2626"),
        (90.7, 99.3, "#b91c1c"),
    ]
    band_markup = []
    for start, end, band_color in bands:
        band_markup.append(
            f'<polyline points="{gauge_arc_points(cx, cy, arc_radius, start, end)}" '
            f'fill="none" stroke="{band_color}" stroke-width="30" stroke-linecap="butt" />'
        )

    ticks = []
    for tick in range(0, 101, 2):
        inner_radius = 102 if tick % 10 == 0 else 112
        outer_radius = 124
        x1, y1 = gauge_point(cx, cy, inner_radius, tick)
        x2, y2 = gauge_point(cx, cy, outer_radius, tick)
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#94a3b8" stroke-width="{1.8 if tick % 10 == 0 else 0.9}" />'
        )

    labels = []
    for tick in (0, 20, 40, 60, 80, 90, 100):
        x, y = gauge_point(cx, cy, 181, tick)
        label_color = "#b91c1c" if tick >= 90 else "#111827"
        labels.append(
            f'<text x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle" '
            f'font-size="19" font-weight="800" fill="{label_color}">{tick}</text>'
        )

    return f"""
<svg class="score-gauge" viewBox="0 0 {width} {height}" role="img" aria-label="Bubble score gauge">
  <rect width="{width}" height="{height}" fill="white" />
  {''.join(band_markup)}
  <circle cx="{cx}" cy="{cy}" r="115" fill="white" />
  {''.join(ticks)}
  {''.join(labels)}
  <line x1="{cx}" y1="{cy}" x2="{needle_x:.1f}" y2="{needle_y:.1f}"
    stroke="{html.escape(color)}" stroke-width="9" stroke-linecap="round" />
  <circle cx="{cx}" cy="{cy}" r="23" fill="white" stroke="#111827" stroke-width="6" />
  <circle cx="{cx}" cy="{cy}" r="13" fill="#111827" />
  <text x="{cx}" y="284" text-anchor="middle" font-size="44" font-weight="800" fill="{html.escape(color)}">{score_text}</text>
  <text x="{cx}" y="313" text-anchor="middle" font-size="20" font-weight="800" fill="#64748b">分</text>
</svg>
"""


def previous_score_caption(data: pd.DataFrame) -> str:
    series = data["bubble_score"].dropna()
    if len(series) < 2:
        return "上一交易日：暂无数据"
    previous_date = series.index[-2].strftime("%Y-%m-%d")
    previous_score = format_score(float(series.iloc[-2]))
    return f"上一交易日：{previous_date} · {previous_score}分"


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


def historical_reference_cards(data: pd.DataFrame) -> list[dict[str, object]]:
    bubble_series = data["bubble_score"].dropna()
    nasdaq_series = scaled_index_series(data, "nasdaq", "qqq_close").dropna()
    if bubble_series.empty:
        return []

    cards: list[dict[str, object]] = []
    for year, title in HISTORICAL_REFERENCE_STAGES:
        year_slice = bubble_series[bubble_series.index.year == year]
        if year_slice.empty:
            logger.debug("No historical reference data for %s", year)
            continue
        point_date = year_slice.idxmax()
        six_month_start = point_date - pd.DateOffset(months=6)
        six_month_slice = bubble_series.loc[six_month_start:point_date]
        six_month_high = float(six_month_slice.max()) if not six_month_slice.empty else np.nan
        cards.append(
            {
                "title": f"{year}{title}",
                "date": point_date.strftime("%Y-%m-%d"),
                "score": float(year_slice.loc[point_date]),
                "six_month_high": six_month_high,
                "drawdown": future_max_drawdown(nasdaq_series, point_date),
            }
        )
    return cards


def render_reference_section(data: pd.DataFrame) -> str:
    cards = historical_reference_cards(data)
    if not cards:
        return ""

    card_markup = []
    for card in cards:
        card_markup.append(
            f"""
      <section class="reference-card">
        <div class="reference-title">{html.escape(str(card["title"]))}</div>
        <div class="reference-date">{html.escape(str(card["date"]))}</div>
        <div class="reference-metrics">
          <div>
            <div class="metric-label">过去6个月最高分</div>
            <div class="metric-value">{format_score(float(card["six_month_high"]))}<span>分</span></div>
          </div>
          <div>
            <div class="metric-label">后续最大回撤</div>
            <div class="metric-value">{format_signed_percent(card["drawdown"])}</div>
          </div>
        </div>
      </section>
"""
        )

    return f"""
    <section class="reference-section">
      <div class="section-title">历史泡沫参照</div>
      <div class="section-subtitle">用历史泡沫高点帮助理解当前分数所处位置</div>
      <div class="reference-grid">
        {''.join(card_markup)}
      </div>
      <div class="reference-note">参照含义：分数接近历史泡沫阶段时，需要重点关注后续大幅回撤风险。</div>
    </section>
"""


def svg_line_chart(data: pd.DataFrame, width: int = 920, height: int = 440) -> str:
    series = trim_to_recent_years(data["bubble_score"].dropna(), years=20)
    if series.empty:
        return ""

    pad_left, pad_top, pad_right, pad_bottom = 42, 28, 18, 124
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    plot_bottom = pad_top + plot_h
    axis_y = plot_bottom + 8
    values = series.to_numpy()
    xs = np.linspace(pad_left, pad_left + plot_w, len(values))
    ys = pad_top + (100 - values) / 100 * plot_h
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    stage_points = find_stage_points(series)

    bands = [
        (85, 100, "#fee2e2"),
        (75, 85, "#ffedd5"),
        (60, 75, "#fef3c7"),
        (40, 60, "#ecfdf5"),
        (0, 40, "#f0fdf4"),
    ]
    rects = []
    for low, high, color in bands:
        y_top = pad_top + (100 - high) / 100 * plot_h
        y_bottom = pad_top + (100 - low) / 100 * plot_h
        rects.append(
            f'<rect x="{pad_left}" y="{y_top:.1f}" width="{plot_w}" '
            f'height="{y_bottom - y_top:.1f}" fill="{color}" />'
        )

    grid = []
    for tick in [0, 20, 40, 60, 75, 85, 100]:
        y = pad_top + (100 - tick) / 100 * plot_h
        grid.append(
            f'<line x1="{pad_left}" x2="{pad_left + plot_w}" y1="{y:.1f}" y2="{y:.1f}" '
            'stroke="#cbd5e1" stroke-dasharray="4 4" />'
        )
        grid.append(
            f'<text x="10" y="{y + 4:.1f}" font-size="12" fill="#475569">{tick}</text>'
        )

    x_axis = [
        f'<line x1="{pad_left}" x2="{pad_left + plot_w}" y1="{axis_y:.1f}" y2="{axis_y:.1f}" '
        'stroke="#94a3b8" stroke-width="1" />'
    ]
    for position, label, anchor_type in x_axis_ticks(series):
        x = float(xs[position])
        anchor = {"start": "start", "end": "end"}.get(anchor_type, "middle")
        x_axis.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{axis_y:.1f}" y2="{axis_y + 5:.1f}" '
            'stroke="#94a3b8" stroke-width="1" />'
        )
        x_axis.append(
            f'<text x="{x:.1f}" y="{axis_y + 18:.1f}" text-anchor="{anchor}" '
            f'font-size="11" fill="#475569">{html.escape(label)}</text>'
        )

    annotations = []
    legend_items = []
    for idx, (year, point_date, score) in enumerate(stage_points):
        point_idx = series.index.get_loc(point_date)
        x = float(xs[point_idx])
        y = pad_top + (100 - score) / 100 * plot_h
        label_x = min(max(x, pad_left + 28), pad_left + plot_w - 28)
        label_y = pad_top + 14 + (idx % 3) * 15
        label = f"{year} {score:.1f}"
        date_label = point_date.strftime("%Y-%m-%d")
        note = BUBBLE_STAGE_NOTES.get(year)
        note_label = f"（{note}）" if note else ""
        legend_items.append(f"{year}{note_label}: {date_label} / {score:.1f}")
        annotations.append(
            f"""
  <g class="stage-marker">
    <title>{year}{note_label} stage coordinate: {date_label}, {score:.1f}</title>
    <line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_top}" y2="{pad_top + plot_h}"
      stroke="#64748b" stroke-width="1" stroke-dasharray="3 4" opacity="0.45" />
    <line x1="{label_x:.1f}" y1="{label_y + 4:.1f}" x2="{x:.1f}" y2="{y - 7:.1f}"
      stroke="#475569" stroke-width="1" opacity="0.65" />
    <circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="#0f172a" stroke="white" stroke-width="1.6" />
    <text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle"
      font-size="11" font-weight="700" fill="#0f172a">{label}</text>
  </g>
"""
        )

    legend = []
    if legend_items:
        legend_lines = [
            " · ".join(legend_items[start : start + 2])
            for start in range(0, len(legend_items), 2)
        ]
        for idx, line in enumerate(legend_lines):
            prefix = "阶段峰值坐标：" if idx == 0 else ""
            legend.append(
                f'<text x="{pad_left}" y="{axis_y + 46 + idx * 16}" font-size="11" fill="#334155">'
                f'{prefix}{html.escape(line)}</text>'
            )
    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Bubble score history">
  <rect width="{width}" height="{height}" fill="white" />
  {''.join(rects)}
  {''.join(grid)}
  <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="3" />
  {''.join(annotations)}
  {''.join(x_axis)}
  {''.join(legend)}
</svg>
"""


def svg_index_chart(data: pd.DataFrame, width: int = 920, height: int = 520) -> str:
    bubble_series = trim_to_recent_years(data["bubble_score"].dropna(), years=20)
    if bubble_series.empty:
        return ""

    frame = pd.DataFrame(
        {
            "sp500": scaled_index_series(data, "sp500", "spy_close"),
            "nasdaq": scaled_index_series(data, "nasdaq", "qqq_close"),
        },
        index=data.index,
    ).dropna()
    frame = trim_frame_to_range(frame, bubble_series.index[0], bubble_series.index[-1])
    if frame.empty:
        return ""

    stage_points = find_stage_points(bubble_series)

    pad_left, pad_top, pad_right, pad_bottom = 70, 148, 74, 116
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    plot_bottom = pad_top + plot_h
    axis_y = plot_bottom + 8
    xs = np.linspace(pad_left, pad_left + plot_w, len(frame))

    sp500_max = float(frame["sp500"].max()) * 1.08
    nasdaq_max = float(frame["nasdaq"].max()) * 1.08
    if sp500_max <= 0 or nasdaq_max <= 0:
        return ""

    sp500_y = pad_top + (1 - frame["sp500"].to_numpy() / sp500_max) * plot_h
    nasdaq_y = pad_top + (1 - frame["nasdaq"].to_numpy() / nasdaq_max) * plot_h
    sp500_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, sp500_y))
    nasdaq_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, nasdaq_y))

    grid = []
    for fraction in np.linspace(0, 1, 5):
        y = pad_top + (1 - fraction) * plot_h
        sp500_label = format_axis_number(sp500_max * fraction)
        nasdaq_label = format_axis_number(nasdaq_max * fraction)
        grid.append(
            f'<line x1="{pad_left}" x2="{pad_left + plot_w}" y1="{y:.1f}" y2="{y:.1f}" '
            'stroke="#e2e8f0" stroke-width="1" />'
        )
        grid.append(
            f'<text x="{pad_left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#64748b">{html.escape(sp500_label)}</text>'
        )
        grid.append(
            f'<text x="{pad_left + plot_w + 10}" y="{y + 4:.1f}" text-anchor="start" '
            f'font-size="11" fill="#b7791f">{html.escape(nasdaq_label)}</text>'
        )

    x_axis = [
        f'<line x1="{pad_left}" x2="{pad_left + plot_w}" y1="{axis_y:.1f}" y2="{axis_y:.1f}" '
        'stroke="#94a3b8" stroke-width="1" />'
    ]
    for position, label, anchor_type in x_axis_ticks(frame["sp500"]):
        x = float(xs[position])
        anchor = {"start": "start", "end": "end"}.get(anchor_type, "middle")
        x_axis.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{axis_y:.1f}" y2="{axis_y + 5:.1f}" '
            'stroke="#94a3b8" stroke-width="1" />'
        )
        x_axis.append(
            f'<text x="{x:.1f}" y="{axis_y + 18:.1f}" text-anchor="{anchor}" '
            f'font-size="11" fill="#475569">{html.escape(label)}</text>'
        )

    markers = []
    coordinate_items = []
    for idx, (year, point_date, score) in enumerate(stage_points):
        if point_date < frame.index[0] or point_date > frame.index[-1]:
            continue
        position = nearest_index_position(frame.index, point_date)
        x = float(xs[position])
        row = frame.iloc[position]
        sp500_value = float(row["sp500"])
        nasdaq_value = float(row["nasdaq"])
        sp500_marker_y = pad_top + (1 - sp500_value / sp500_max) * plot_h
        nasdaq_marker_y = pad_top + (1 - nasdaq_value / nasdaq_max) * plot_h
        note = BUBBLE_STAGE_NOTES.get(year)
        note_label = f"（{note}）" if note else ""
        date_label = frame.index[position].strftime("%Y-%m-%d")
        label_x = min(max(x, pad_left + 90), pad_left + plot_w - 90)
        label_y = 76 + idx * 14
        coordinate_items.append(
            f"{year}{note_label}: {date_label} / S&P {format_axis_number(sp500_value)} / Nasdaq {format_axis_number(nasdaq_value)}"
        )
        markers.append(
            f"""
  <g class="index-stage-marker">
    <title>{year}{note_label}: {date_label}, S&P {sp500_value:.2f}, Nasdaq {nasdaq_value:.2f}, bubble {score:.1f}</title>
    <line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_top}" y2="{plot_bottom}"
      stroke="#b91c1c" stroke-width="1" stroke-dasharray="5 7" opacity="0.28" />
    <line x1="{label_x:.1f}" y1="{label_y + 5:.1f}" x2="{x:.1f}" y2="{pad_top + 5:.1f}"
      stroke="#b91c1c" stroke-width="1" opacity="0.35" />
    <circle cx="{x:.1f}" cy="{sp500_marker_y:.1f}" r="4.8" fill="#0f8f83" stroke="white" stroke-width="1.6" />
    <circle cx="{x:.1f}" cy="{nasdaq_marker_y:.1f}" r="4.8" fill="#d99a22" stroke="white" stroke-width="1.6" />
    <text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle"
      font-size="11" font-weight="800" fill="#b91c1c">{year}{html.escape(note_label)}</text>
  </g>
"""
        )

    coordinates = []
    if coordinate_items:
        coordinate_lines = [
            " · ".join(coordinate_items[start : start + 2])
            for start in range(0, len(coordinate_items), 2)
        ]
        for idx, line in enumerate(coordinate_lines):
            prefix = "阶段日期指数坐标：" if idx == 0 else ""
            coordinates.append(
                f'<text x="{pad_left}" y="{axis_y + 46 + idx * 16}" font-size="11" fill="#334155">'
                f'{prefix}{html.escape(line)}</text>'
            )

    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="S&P 500 and Nasdaq history">
  <rect width="{width}" height="{height}" fill="white" />
  <text x="{pad_left}" y="26" font-size="14" font-weight="800" fill="#0f172a">S&P 500 与 Nasdaq 指数</text>
  <g class="index-legend">
    <circle cx="{pad_left + 8}" cy="44" r="4" fill="#0f8f83" />
    <text x="{pad_left + 18}" y="48" font-size="12" font-weight="800" fill="#0f8f83">S&P 500（左轴）</text>
    <circle cx="{pad_left + 142}" cy="44" r="4" fill="#d99a22" />
    <text x="{pad_left + 152}" y="48" font-size="12" font-weight="800" fill="#b7791f">Nasdaq（右轴）</text>
  </g>
  <line x1="{pad_left}" x2="{pad_left + plot_w}" y1="62" y2="62" stroke="#e2e8f0" stroke-width="1" />
  {''.join(grid)}
  <text x="20" y="{pad_top + plot_h / 2:.1f}" transform="rotate(-90 20 {pad_top + plot_h / 2:.1f})"
    text-anchor="middle" font-size="12" font-weight="700" fill="#64748b">S&P 500</text>
  <text x="{width - 20}" y="{pad_top + plot_h / 2:.1f}" transform="rotate(90 {width - 20} {pad_top + plot_h / 2:.1f})"
    text-anchor="middle" font-size="12" font-weight="700" fill="#b7791f">Nasdaq</text>
  <polyline points="{sp500_points}" fill="none" stroke="#0f8f83" stroke-width="3" />
  <polyline points="{nasdaq_points}" fill="none" stroke="#d99a22" stroke-width="3" />
  {''.join(markers)}
  {''.join(x_axis)}
  {''.join(coordinates)}
</svg>
"""


def build_summary(latest: pd.Series) -> dict[str, object]:
    logger.debug("Building summary for %s", latest.name)
    label, color = risk_label(float(latest["bubble_score"]))
    factors = []
    for factor in FACTORS:
        if factor.score_column not in latest.index:
            continue
        raw = latest.get(factor.raw_column, np.nan)
        score = latest.get(factor.score_column, np.nan)
        factors.append(
            {
                "key": factor.key,
                "name": factor.name,
                "raw_value": None if pd.isna(raw) else float(raw),
                "display_value": factor.value_formatter(raw),
                "score": None if pd.isna(score) else round(float(score), 1),
                "reason": factor_reason(factor, score),
            }
        )
    return {
        "date": latest.name.strftime("%Y-%m-%d"),
        "bubble_score": round(float(latest["bubble_score"]), 1),
        "risk_label": label,
        "risk_color": color,
        "active_factor_count": int(latest["active_factor_count"]),
        "factors": factors,
    }


def render_html_report(data: pd.DataFrame, summary: dict[str, object]) -> str:
    logger.debug("Rendering HTML report for %s", summary["date"])
    score = summary["bubble_score"]
    color = summary["risk_color"]
    score_text = format_score(float(score))
    gauge = svg_score_gauge(float(score), str(color))
    previous_caption = previous_score_caption(data)
    reference_section = render_reference_section(data)
    factor_cards = []
    for idx, factor in enumerate(summary["factors"], start=1):
        score_value = factor["score"]
        card_color = risk_label(float(score_value))[1] if score_value is not None else "#64748b"
        factor_cards.append(
            f"""
      <section class="factor">
        <div class="factor-title">特征 {idx} · {html.escape(str(factor["name"]))}</div>
        <div class="factor-score" style="color:{card_color}">{score_value if score_value is not None else "NA"} 分</div>
        <div class="factor-value">当前值：{html.escape(str(factor["display_value"]))}</div>
        <p>{html.escape(str(factor["reason"]))}</p>
      </section>
"""
        )

    chart = svg_line_chart(data)
    index_chart = svg_index_chart(data)
    index_chart_section = (
        f'<section class="chart secondary-chart">{index_chart}</section>' if index_chart else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Nasdaq 泡沫指数报告</title>
  <style>
    body {{
      margin: 0;
      background: #f6f8fb;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1060px;
      margin: 0 auto;
      padding: 34px 18px 52px;
    }}
    .poster-head {{
      padding: 10px 30px 22px;
      background: white;
    }}
    .brand {{
      text-align: right;
      color: #94a3b8;
      font-size: 18px;
      font-weight: 700;
    }}
    h1 {{
      margin: 20px 0 4px;
      text-align: center;
      font-size: 72px;
      line-height: 1.04;
      font-weight: 900;
    }}
    .subtitle {{
      text-align: center;
      color: #64748b;
      font-size: 27px;
      font-weight: 600;
    }}
    .title-rule {{
      position: relative;
      height: 2px;
      margin: 32px 0 0;
      background: #e5e7eb;
    }}
    .title-rule::before {{
      content: "";
      position: absolute;
      left: 0;
      top: -2px;
      width: 88px;
      height: 6px;
      background: #dc182f;
    }}
    .score-panel {{
      margin-top: 28px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 42px 44px 36px;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
      display: grid;
      grid-template-columns: minmax(300px, 0.95fr) minmax(430px, 1.05fr);
      gap: 28px;
      align-items: center;
    }}
    .score-kicker {{
      font-size: 48px;
      line-height: 1.1;
      font-weight: 900;
    }}
    .score-kicker-rule {{
      display: grid;
      grid-template-columns: 1fr 48px 1fr;
      gap: 24px;
      align-items: center;
      max-width: 360px;
      margin: 26px 0 20px;
    }}
    .score-kicker-rule::before,
    .score-kicker-rule::after {{
      content: "";
      height: 1px;
      background: #e5e7eb;
    }}
    .score-kicker-rule span {{
      height: 5px;
      background: #c9142a;
    }}
    .score-number {{
      display: flex;
      align-items: baseline;
      gap: 14px;
      color: {color};
    }}
    .score-number strong {{
      font-size: 150px;
      line-height: 1;
      font-weight: 900;
    }}
    .score-number span {{
      font-size: 48px;
      font-weight: 900;
    }}
    .previous {{
      margin-top: 14px;
      color: #64748b;
      font-size: 20px;
      font-weight: 800;
    }}
    .risk-pill {{
      display: inline-block;
      margin-top: 18px;
      padding: 8px 14px;
      border-radius: 999px;
      color: white;
      background: {color};
      font-weight: 700;
    }}
    .gauge-wrap {{
      display: flex;
      justify-content: center;
    }}
    .score-gauge {{
      width: 100%;
      max-width: 470px;
      height: auto;
      display: block;
    }}
    .reference-section {{
      margin-top: 26px;
      padding: 0 44px;
    }}
    .section-title {{
      font-size: 32px;
      font-weight: 900;
    }}
    .section-subtitle {{
      margin-top: 4px;
      color: #64748b;
      font-size: 17px;
      font-weight: 700;
    }}
    .reference-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-top: 20px;
    }}
    .reference-card {{
      position: relative;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 18px 22px 16px 34px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }}
    .reference-card::before {{
      content: "";
      position: absolute;
      left: 16px;
      top: 20px;
      width: 6px;
      height: 44px;
      border-radius: 6px;
      background: #dc182f;
    }}
    .reference-title {{
      font-size: 25px;
      line-height: 1.12;
      font-weight: 900;
    }}
    .reference-date {{
      margin-top: 5px;
      color: #64748b;
      font-size: 16px;
      font-weight: 800;
    }}
    .reference-metrics {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 20px;
      padding-top: 14px;
      border-top: 1px solid #e5e7eb;
    }}
    .metric-label {{
      color: #64748b;
      font-size: 15px;
      font-weight: 800;
    }}
    .metric-value {{
      margin-top: 3px;
      color: #c9142a;
      font-size: 29px;
      line-height: 1;
      font-weight: 900;
    }}
    .metric-value span {{
      margin-left: 5px;
      color: #64748b;
      font-size: 14px;
    }}
    .reference-note {{
      margin-top: 16px;
      text-align: center;
      color: #64748b;
      font-size: 15px;
      font-weight: 700;
    }}
    .chart {{
      margin-top: 24px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      overflow: hidden;
    }}
    .secondary-chart {{
      margin-top: 16px;
    }}
    .factors {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}
    .factor {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px;
    }}
    .factor-title {{ color: #334155; font-weight: 700; }}
    .factor-score {{ margin-top: 12px; font-size: 32px; font-weight: 800; }}
    .factor-value {{ margin-top: 4px; color: #64748b; }}
    .factor p {{ margin: 10px 0 0; line-height: 1.55; }}
    .note {{
      margin-top: 22px;
      color: #64748b;
      font-size: 14px;
      line-height: 1.6;
    }}
    @media (max-width: 920px) {{
      .score-panel {{
        grid-template-columns: 1fr;
      }}
      .score-left {{
        text-align: center;
      }}
      .score-kicker-rule {{
        margin-left: auto;
        margin-right: auto;
      }}
      .score-number {{
        justify-content: center;
      }}
    }}
    @media (max-width: 720px) {{
      main {{
        padding: 18px 12px 40px;
      }}
      .poster-head {{
        padding: 8px 10px 18px;
      }}
      .brand {{
        font-size: 14px;
      }}
      h1 {{
        font-size: 44px;
      }}
      .subtitle {{
        font-size: 18px;
      }}
      .score-panel {{
        padding: 28px 18px 26px;
      }}
      .score-kicker {{
        font-size: 34px;
      }}
      .score-number strong {{
        font-size: 96px;
      }}
      .score-number span {{
        font-size: 34px;
      }}
      .previous {{
        font-size: 15px;
      }}
      .reference-section {{
        padding: 0;
      }}
      .reference-grid,
      .factors {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="poster-head">
      <div class="brand">Nasdaq Bubble Index</div>
      <h1>美股泡沫评估</h1>
      <div class="subtitle">截至 {summary["date"]} 收盘</div>
      <div class="title-rule"></div>
    </header>
    <section class="score-panel">
      <div class="score-left">
        <div class="score-kicker">今日泡沫分数</div>
        <div class="score-kicker-rule"><span></span></div>
        <div class="score-number"><strong>{score_text}</strong><span>分</span></div>
        <div class="previous">{html.escape(previous_caption)}</div>
        <div class="risk-pill">{html.escape(str(summary["risk_label"]))} · {summary["active_factor_count"]} 个因子</div>
      </div>
      <div class="gauge-wrap">{gauge}</div>
    </section>
    {reference_section}
    <section class="chart">{chart}</section>
    {index_chart_section}
    <section class="factors">
      {''.join(factor_cards)}
    </section>
    <p class="note">说明：本工具只使用免费公开数据。FRED/F​INRA/Cboe 等来源可能存在发布时间差，月度数据会向前填充到每日频率。请把结果当作研究辅助，而不是投资建议。</p>
  </main>
</body>
</html>
"""


def write_outputs(data: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    logger.info("Writing outputs to %s", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_complete_row(data)
    summary = build_summary(latest)
    logger.info(
        "Latest complete score: date=%s, score=%s, label=%s",
        summary["date"],
        summary["bubble_score"],
        summary["risk_label"],
    )

    history_path = out_dir / "bubble_history.csv"
    latest_path = out_dir / "latest.json"
    report_path = out_dir / "report.html"

    data.to_csv(history_path, index_label="date")
    logger.info("Wrote history CSV: %s", history_path)
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote latest JSON: %s", latest_path)
    report_path.write_text(render_html_report(data, summary), encoding="utf-8")
    logger.info("Wrote HTML report: %s", report_path)

    return {
        "history": history_path,
        "latest": latest_path,
        "report": report_path,
    }
