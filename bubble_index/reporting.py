"""Summary, chart, and file output rendering."""

from __future__ import annotations

import html
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .backtesting import build_backtest_summary
from .factors import Factor

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
STATIC_ASSET_FILES = ("echarts.min.js",)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def static_assets_dir() -> Path:
    return project_root() / "static"


def copy_static_assets(out_dir: Path) -> None:
    source_dir = static_assets_dir()
    target_dir = out_dir / "static"
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in STATIC_ASSET_FILES:
        source = source_dir / filename
        if not source.exists():
            logger.warning("Static asset missing, interactive charts may not load: %s", source)
            continue
        shutil.copy2(source, target_dir / filename)


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


def format_plain_percent(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value * 100:.1f}%"


def format_decimal(value: float | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


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


def render_backtest_section(backtest_summary: dict[str, object] | None) -> str:
    if not backtest_summary:
        return ""

    model = backtest_summary.get("model")
    if not isinstance(model, dict):
        return ""

    top_decile = model.get("top_decile", {})
    score_ge_75 = model.get("score_ge_75", {})
    if not isinstance(top_decile, dict):
        top_decile = {}
    if not isinstance(score_ge_75, dict):
        score_ge_75 = {}
    model_card = f"""
      <section class="backtest-card">
        <div class="backtest-card-title">{html.escape(str(model.get("label", "模型")))}</div>
        <div class="backtest-metrics">
          <div>
            <span>相关性</span>
            <strong>{format_decimal(model.get("score_to_future_drawdown_severity_corr"), 2)}</strong>
          </div>
          <div>
            <span>Top 10% 后续回撤</span>
            <strong>{format_signed_percent(top_decile.get("avg_future_max_drawdown"))}</strong>
          </div>
          <div>
            <span>Top 10% 大跌命中率</span>
            <strong>{format_plain_percent(top_decile.get("hit_rate_25pct_drawdown"))}</strong>
          </div>
          <div>
            <span>75分以上样本</span>
            <strong>{score_ge_75.get("count", 0)}</strong>
          </div>
        </div>
      </section>
"""

    stage_rows = []
    for stage in model.get("stage_peaks", []):
        if not isinstance(stage, dict):
            continue
        stage_rows.append(
            f"""
        <tr>
          <td>{stage.get("year", "")}</td>
          <td>{html.escape(str(stage.get("label", "")))}</td>
          <td>{html.escape(str(stage.get("peak_date", "")))}</td>
          <td>{format_decimal(stage.get("score"), 1)}</td>
          <td>{format_signed_percent(stage.get("future_max_drawdown"))}</td>
        </tr>
"""
        )

    stage_table = ""
    if stage_rows:
        stage_table = f"""
      <div class="backtest-table-wrap">
        <table class="backtest-table">
          <thead>
            <tr>
              <th>年份</th>
              <th>说明</th>
              <th>分组方案峰值日</th>
              <th>峰值分数</th>
              <th>后续3年最大回撤</th>
            </tr>
          </thead>
          <tbody>{''.join(stage_rows)}</tbody>
        </table>
      </div>
"""

    return f"""
    <section class="backtest-section">
      <div class="section-title">回测摘要</div>
      <div class="section-subtitle">月度样本，观察分数与未来 {backtest_summary.get("future_window_years", 3)} 年 Nasdaq 最大回撤的关系</div>
      <div class="backtest-grid">{model_card}</div>
      {stage_table}
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


def chart_number(value: float | int | None, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def script_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render_stage_chips(stages: list[dict[str, object]]) -> str:
    chips = []
    for stage in stages:
        chips.append(
            f"""
        <span class="stage-chip">
          <strong>{html.escape(str(stage["year"]))}</strong>
          {html.escape(str(stage["note"]))}
          <span>{html.escape(str(stage["date"]))} · {format_decimal(stage["score"], 1)}分</span>
        </span>
"""
        )
    return "".join(chips)


def interactive_chart_payload(data: pd.DataFrame) -> dict[str, object] | None:
    bubble_series = trim_to_recent_years(data["bubble_score"].dropna(), years=20)
    if bubble_series.empty:
        return None

    frame = pd.DataFrame(
        {
            "bubble": data["bubble_score"],
            "sp500": scaled_index_series(data, "sp500", "spy_close"),
            "nasdaq": scaled_index_series(data, "nasdaq", "qqq_close"),
        },
        index=data.index,
    )
    frame = trim_frame_to_range(frame, bubble_series.index[0], bubble_series.index[-1])
    frame = frame.dropna(subset=["bubble", "sp500", "nasdaq"])
    if frame.empty:
        return None

    stages = []
    for year, point_date, score in find_stage_points(bubble_series):
        if point_date < frame.index[0] or point_date > frame.index[-1]:
            continue
        position = nearest_index_position(frame.index, point_date)
        row = frame.iloc[position]
        stages.append(
            {
                "year": year,
                "note": BUBBLE_STAGE_NOTES.get(year, ""),
                "date": frame.index[position].strftime("%Y-%m-%d"),
                "score": chart_number(score, 1),
                "sp500": chart_number(row["sp500"], 2),
                "nasdaq": chart_number(row["nasdaq"], 2),
            }
        )

    return {
        "dates": [date.strftime("%Y-%m-%d") for date in frame.index],
        "bubble": [chart_number(value, 2) for value in frame["bubble"]],
        "sp500": [chart_number(value, 2) for value in frame["sp500"]],
        "nasdaq": [chart_number(value, 2) for value in frame["nasdaq"]],
        "stages": stages,
    }


def render_interactive_charts(data: pd.DataFrame) -> str:
    payload = interactive_chart_payload(data)
    if not payload:
        return ""
    stages = payload.get("stages", [])
    stage_chips = render_stage_chips(stages) if isinstance(stages, list) else ""
    return f"""
    <section class="chart interactive-chart-section">
      <div class="interactive-chart-head">
        <div>
          <div class="interactive-chart-title">泡沫分数与指数走势</div>
          <div class="interactive-chart-subtitle">20 年窗口</div>
        </div>
      </div>
      <div id="bubble-score-chart" class="echart bubble-echart"></div>
      <div id="market-index-chart" class="echart index-echart"></div>
      <div class="stage-chip-row">{stage_chips}</div>
      <div id="chart-fallback" class="chart-fallback" hidden>交互图表脚本未加载。</div>
      <script id="bubble-chart-data" type="application/json">{script_json(payload)}</script>
    </section>
"""


def interactive_chart_bootstrap() -> str:
    return """
  <script src="static/echarts.min.js"></script>
  <script>
    (function () {
      const dataNode = document.getElementById("bubble-chart-data");
      const bubbleNode = document.getElementById("bubble-score-chart");
      const indexNode = document.getElementById("market-index-chart");
      if (!dataNode || !bubbleNode || !indexNode) return;

      const fallbackNode = document.getElementById("chart-fallback");
      if (!window.echarts) {
        if (fallbackNode) fallbackNode.hidden = false;
        return;
      }

      const chartData = JSON.parse(dataNode.textContent);
      const stages = chartData.stages || [];
      const stageByDate = new Map(stages.map((stage) => [stage.date, stage]));
      const numberFormatter = new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 1
      });

      function formatNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "NA";
        return numberFormatter.format(Number(value));
      }

      function stageText(date) {
        const stage = stageByDate.get(date);
        if (!stage) return "";
        return `<br/><span style="color:#b91c1c;font-weight:700">${stage.year} ${stage.note}</span>`;
      }

      function stageLines(showLabel) {
        return stages.map((stage) => ({
          name: `${stage.year} ${stage.note}`,
          xAxis: stage.date,
          label: {
            show: Boolean(showLabel),
            formatter: String(stage.year),
            color: "#b91c1c",
            fontWeight: 800,
            fontSize: 11
          }
        }));
      }

      function finiteValues(series, startIndex, endIndex) {
        const values = [];
        for (let index = startIndex; index <= endIndex; index += 1) {
          const value = Number(series[index]);
          if (Number.isFinite(value)) values.push(value);
        }
        return values;
      }

      function paddedRange(values, options) {
        if (!values.length) return { min: null, max: null };
        const settings = Object.assign({
          padding: 0.08,
          minPadding: 0,
          minimumSpan: 1,
          digits: 0,
          hardMin: null,
          hardMax: null
        }, options || {});
        let min = Math.min(...values);
        let max = Math.max(...values);
        let span = max - min;
        if (span <= 0) {
          span = Math.max(Math.abs(max) * 0.02, settings.minimumSpan);
        }
        let lower = min - Math.max(span * settings.padding, settings.minPadding);
        let upper = max + Math.max(span * settings.padding, settings.minPadding);
        if ((upper - lower) < settings.minimumSpan) {
          const middle = (upper + lower) / 2;
          lower = middle - settings.minimumSpan / 2;
          upper = middle + settings.minimumSpan / 2;
        }
        if (settings.hardMin !== null) lower = Math.max(settings.hardMin, lower);
        if (settings.hardMax !== null) upper = Math.min(settings.hardMax, upper);
        const factor = Math.pow(10, settings.digits);
        return {
          min: Math.floor(lower * factor) / factor,
          max: Math.ceil(upper * factor) / factor
        };
      }

      function zoomToIndexes(start, end) {
        const lastIndex = Math.max(chartData.dates.length - 1, 0);
        const startIndex = Math.max(0, Math.min(lastIndex, Math.floor(lastIndex * start / 100)));
        const endIndex = Math.max(startIndex, Math.min(lastIndex, Math.ceil(lastIndex * end / 100)));
        return { startIndex, endIndex };
      }

      function extractZoom(params) {
        const zoom = params && params.batch && params.batch.length ? params.batch[0] : (params || {});
        return {
          start: Number.isFinite(zoom.start) ? zoom.start : currentZoom.start,
          end: Number.isFinite(zoom.end) ? zoom.end : currentZoom.end
        };
      }

      function applyVisibleAxisRange(start, end) {
        const { startIndex, endIndex } = zoomToIndexes(start, end);
        const fullRange = start <= 0.05 && end >= 99.95;
        const bubbleRange = fullRange
          ? { min: 0, max: 100 }
          : paddedRange(finiteValues(chartData.bubble, startIndex, endIndex), {
              padding: 0.18,
              minPadding: 1.5,
              minimumSpan: 8,
              digits: 1,
              hardMin: 0,
              hardMax: 100
            });
        const sp500Range = paddedRange(finiteValues(chartData.sp500, startIndex, endIndex), {
          padding: 0.08,
          minimumSpan: 100,
          digits: 0
        });
        const nasdaqRange = paddedRange(finiteValues(chartData.nasdaq, startIndex, endIndex), {
          padding: 0.08,
          minimumSpan: 250,
          digits: 0
        });

        bubbleChart.setOption({ yAxis: { min: bubbleRange.min, max: bubbleRange.max } });
        indexChart.setOption({
          yAxis: [
            { min: sp500Range.min, max: sp500Range.max },
            { min: nasdaqRange.min, max: nasdaqRange.max }
          ]
        });
      }

      function dispatchZoom(targetChart, start, end, zoomIndexes) {
        for (const dataZoomIndex of zoomIndexes) {
          targetChart.dispatchAction({ type: "dataZoom", dataZoomIndex, start, end });
        }
      }

      let currentZoom = { start: 0, end: 100 };
      let syncingZoom = false;

      function handleZoom(params, targetChart, targetZoomIndexes) {
        const zoom = extractZoom(params);
        currentZoom = zoom;
        applyVisibleAxisRange(zoom.start, zoom.end);
        if (syncingZoom) return;
        syncingZoom = true;
        dispatchZoom(targetChart, zoom.start, zoom.end, targetZoomIndexes);
        syncingZoom = false;
      }

      const bubbleStagePoints = stages.map((stage) => ({
        name: `${stage.year} ${stage.note}`,
        coord: [stage.date, stage.score],
        value: stage.score,
        symbol: "circle",
        symbolSize: 9,
        itemStyle: { color: "#b91c1c", borderColor: "#ffffff", borderWidth: 2 },
        label: { show: false }
      }));

      const sp500StagePoints = stages.map((stage) => ({
        name: `${stage.year} ${stage.note}`,
        coord: [stage.date, stage.sp500],
        value: stage.sp500,
        symbolSize: 8,
        itemStyle: { color: "#0f8f83", borderColor: "#ffffff", borderWidth: 2 },
        label: { show: false }
      }));

      const nasdaqStagePoints = stages.map((stage) => ({
        name: `${stage.year} ${stage.note}`,
        coord: [stage.date, stage.nasdaq],
        value: stage.nasdaq,
        symbolSize: 8,
        itemStyle: { color: "#d99a22", borderColor: "#ffffff", borderWidth: 2 },
        label: { show: false }
      }));

      const commonXAxis = {
        type: "category",
        boundaryGap: false,
        data: chartData.dates,
        axisLabel: { color: "#64748b", hideOverlap: true },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { lineStyle: { color: "#cbd5e1" } }
      };

      const commonToolbox = {
        right: 12,
        top: 6,
        itemSize: 15,
        feature: {
          dataZoom: {
            yAxisIndex: "none",
            title: { zoom: "区域缩放", back: "还原缩放" }
          },
          restore: { title: "重置" },
          saveAsImage: { title: "保存图片", pixelRatio: 2 }
        }
      };

      const verticalMarkLine = {
        symbol: "none",
        silent: true,
        lineStyle: { color: "#b91c1c", type: "dashed", opacity: 0.26, width: 1 },
        label: { show: false },
        data: stageLines(false)
      };

      const bubbleChart = echarts.init(bubbleNode, null, { renderer: "canvas" });
      const indexChart = echarts.init(indexNode, null, { renderer: "canvas" });

      bubbleChart.setOption({
        animation: false,
        color: ["#2563eb"],
        grid: { left: 46, right: 24, top: 42, bottom: 58, containLabel: true },
        toolbox: commonToolbox,
        tooltip: {
          trigger: "axis",
          confine: true,
          axisPointer: { type: "cross" },
          formatter: function (params) {
            const point = params[0];
            const date = point.axisValue;
            return `${date}<br/>泡沫分数：<b>${formatNumber(point.data)}</b>${stageText(date)}`;
          }
        },
        xAxis: commonXAxis,
        yAxis: {
          type: "value",
          min: 0,
          max: 100,
          axisLabel: { color: "#64748b" },
          axisLine: { lineStyle: { color: "#cbd5e1" } },
          splitLine: { lineStyle: { color: "#e2e8f0" } }
        },
        dataZoom: [{ type: "inside", filterMode: "none", throttle: 50 }],
        series: [{
          name: "泡沫分数",
          type: "line",
          data: chartData.bubble,
          showSymbol: false,
          lineStyle: { width: 2.6, color: "#2563eb" },
          markArea: {
            silent: true,
            data: [
              [{ yAxis: 85, itemStyle: { color: "rgba(254, 226, 226, 0.72)" } }, { yAxis: 100 }],
              [{ yAxis: 75, itemStyle: { color: "rgba(255, 237, 213, 0.72)" } }, { yAxis: 85 }],
              [{ yAxis: 60, itemStyle: { color: "rgba(254, 243, 199, 0.72)" } }, { yAxis: 75 }],
              [{ yAxis: 40, itemStyle: { color: "rgba(236, 253, 245, 0.72)" } }, { yAxis: 60 }],
              [{ yAxis: 0, itemStyle: { color: "rgba(240, 253, 244, 0.72)" } }, { yAxis: 40 }]
            ]
          },
          markLine: verticalMarkLine,
          markPoint: { data: bubbleStagePoints }
        }]
      });

      indexChart.setOption({
        animation: false,
        color: ["#0f8f83", "#d99a22"],
        grid: { left: 58, right: 68, top: 54, bottom: 92, containLabel: true },
        legend: {
          top: 12,
          left: 16,
          textStyle: { color: "#334155", fontWeight: 800 }
        },
        toolbox: commonToolbox,
        tooltip: {
          trigger: "axis",
          confine: true,
          axisPointer: { type: "cross" },
          formatter: function (params) {
            const date = params[0].axisValue;
            const lines = params.map((point) => (
              `${point.marker}${point.seriesName}：<b>${formatNumber(point.data)}</b>`
            ));
            return `${date}<br/>${lines.join("<br/>")}${stageText(date)}`;
          }
        },
        xAxis: commonXAxis,
        yAxis: [
          {
            type: "value",
            name: "S&P 500",
            scale: true,
            axisLabel: { color: "#64748b" },
            axisLine: { lineStyle: { color: "#cbd5e1" } },
            splitLine: { lineStyle: { color: "#e2e8f0" } }
          },
          {
            type: "value",
            name: "Nasdaq",
            scale: true,
            axisLabel: { color: "#b7791f" },
            axisLine: { lineStyle: { color: "#d99a22" } },
            splitLine: { show: false }
          }
        ],
        dataZoom: [
          { type: "inside", filterMode: "none", throttle: 50 },
          {
            type: "slider",
            filterMode: "none",
            height: 24,
            bottom: 22,
            borderColor: "#e2e8f0",
            fillerColor: "rgba(37, 99, 235, 0.12)",
            handleStyle: { color: "#2563eb" },
            textStyle: { color: "#64748b" }
          }
        ],
        series: [
          {
            name: "S&P 500（左轴）",
            type: "line",
            data: chartData.sp500,
            yAxisIndex: 0,
            showSymbol: false,
            lineStyle: { width: 2.5 },
            markLine: verticalMarkLine,
            markPoint: { data: sp500StagePoints }
          },
          {
            name: "Nasdaq（右轴）",
            type: "line",
            data: chartData.nasdaq,
            yAxisIndex: 1,
            showSymbol: false,
            lineStyle: { width: 2.5 },
            markPoint: { data: nasdaqStagePoints }
          }
        ]
      });

      bubbleChart.on("dataZoom", function (params) {
        handleZoom(params, indexChart, [0, 1]);
      });
      indexChart.on("dataZoom", function (params) {
        handleZoom(params, bubbleChart, [0]);
      });
      applyVisibleAxisRange(currentZoom.start, currentZoom.end);

      const resizeCharts = function () {
        bubbleChart.resize();
        indexChart.resize();
      };
      window.addEventListener("resize", resizeCharts);
      setTimeout(resizeCharts, 0);
    })();
  </script>
"""


def build_summary(latest: pd.Series, factors: list[Factor]) -> dict[str, object]:
    logger.debug("Building summary for %s", latest.name)
    label, color = risk_label(float(latest["bubble_score"]))
    factor_items = []
    for factor in factors:
        if factor.score_column not in latest.index:
            continue
        raw = latest.get(factor.raw_column, np.nan)
        score = latest.get(factor.score_column, np.nan)
        factor_items.append(
            {
                "key": factor.key,
                "name": factor.name,
                "weight": factor.weight,
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
        "factors": factor_items,
    }


def render_html_report(
    data: pd.DataFrame,
    summary: dict[str, object],
    backtest_summary: dict[str, object] | None = None,
) -> str:
    logger.debug("Rendering HTML report for %s", summary["date"])
    score = summary["bubble_score"]
    color = summary["risk_color"]
    score_text = format_score(float(score))
    gauge = svg_score_gauge(float(score), str(color))
    previous_caption = previous_score_caption(data)
    reference_section = render_reference_section(data)
    backtest_section = render_backtest_section(backtest_summary)
    factor_cards = []
    for idx, factor in enumerate(summary["factors"], start=1):
        score_value = factor["score"]
        card_color = risk_label(float(score_value))[1] if score_value is not None else "#64748b"
        factor_cards.append(
            f"""
      <section class="factor">
        <div class="factor-title">特征 {idx} · {html.escape(str(factor["name"]))}</div>
        <div class="factor-score" style="color:{card_color}">{score_value if score_value is not None else "NA"} 分</div>
        <div class="factor-weight">权重：{float(factor["weight"]) * 100:.1f}%</div>
        <div class="factor-value">当前值：{html.escape(str(factor["display_value"]))}</div>
        <p>{html.escape(str(factor["reason"]))}</p>
      </section>
"""
        )

    charts = render_interactive_charts(data)
    chart_bootstrap = interactive_chart_bootstrap() if charts else ""
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
    .backtest-section {{
      margin-top: 26px;
      padding: 0 44px;
    }}
    .backtest-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 18px;
      margin-top: 20px;
    }}
    .backtest-card {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
    }}
    .backtest-card-title {{
      font-size: 22px;
      font-weight: 900;
    }}
    .backtest-metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .backtest-metrics span {{
      display: block;
      color: #64748b;
      font-size: 13px;
      font-weight: 800;
    }}
    .backtest-metrics strong {{
      display: block;
      margin-top: 4px;
      color: #0f172a;
      font-size: 24px;
      line-height: 1;
      font-weight: 900;
    }}
    .backtest-table-wrap {{
      margin-top: 18px;
      overflow-x: auto;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }}
    .backtest-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .backtest-table th,
    .backtest-table td {{
      padding: 11px 12px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      white-space: nowrap;
    }}
    .backtest-table th {{
      color: #64748b;
      font-size: 12px;
      font-weight: 900;
    }}
    .backtest-table tr:last-child td {{
      border-bottom: 0;
    }}
    .chart {{
      margin-top: 24px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      overflow: hidden;
    }}
    .interactive-chart-section {{
      padding: 18px 18px 16px;
    }}
    .interactive-chart-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      padding: 2px 4px 0;
    }}
    .interactive-chart-title {{
      color: #0f172a;
      font-size: 20px;
      font-weight: 900;
    }}
    .interactive-chart-subtitle {{
      margin-top: 3px;
      color: #64748b;
      font-size: 13px;
      font-weight: 800;
    }}
    .echart {{
      width: 100%;
      min-width: 0;
    }}
    .bubble-echart {{
      height: 360px;
      margin-top: 8px;
    }}
    .index-echart {{
      height: 420px;
      margin-top: 10px;
    }}
    .stage-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 2px 4px 0;
    }}
    .stage-chip {{
      display: inline-flex;
      align-items: baseline;
      gap: 6px;
      padding: 7px 10px;
      border: 1px solid #fee2e2;
      border-radius: 8px;
      background: #fff7f7;
      color: #991b1b;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.2;
    }}
    .stage-chip span {{
      color: #64748b;
      font-weight: 700;
    }}
    .chart-fallback {{
      margin: 12px 4px 0;
      color: #991b1b;
      font-size: 14px;
      font-weight: 800;
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
    .factor-weight {{ margin-top: 2px; color: #475569; font-size: 13px; font-weight: 700; }}
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
      .backtest-section {{
        padding: 0;
      }}
      .reference-grid,
      .backtest-grid,
      .factors {{
        grid-template-columns: 1fr;
      }}
      .interactive-chart-section {{
        padding: 14px 8px 12px;
      }}
      .bubble-echart {{
        height: 330px;
      }}
      .index-echart {{
        height: 380px;
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
    {backtest_section}
    {charts}
    <section class="factors">
      {''.join(factor_cards)}
    </section>
    <p class="note">说明：本工具只使用免费公开数据。FRED/F​INRA/Cboe 等来源可能存在发布时间差，月度数据会向前填充到每日频率。请把结果当作研究辅助，而不是投资建议。</p>
  </main>
  {chart_bootstrap}
</body>
</html>
"""


def write_outputs(data: pd.DataFrame, out_dir: Path, factors: list[Factor]) -> dict[str, Path]:
    logger.info("Writing outputs to %s", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_static_assets(out_dir)
    latest = latest_complete_row(data)
    summary = build_summary(latest, factors)
    logger.info(
        "Latest complete score: date=%s, score=%s, label=%s",
        summary["date"],
        summary["bubble_score"],
        summary["risk_label"],
    )

    history_path = out_dir / "bubble_history.csv"
    latest_path = out_dir / "latest.json"
    backtest_path = out_dir / "backtest_summary.json"
    report_path = out_dir / "report.html"

    data.to_csv(history_path, index_label="date")
    logger.info("Wrote history CSV: %s", history_path)
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote latest JSON: %s", latest_path)
    backtest_summary = build_backtest_summary(data)
    backtest_path.write_text(
        json.dumps(backtest_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Wrote backtest JSON: %s", backtest_path)
    report_path.write_text(render_html_report(data, summary, backtest_summary), encoding="utf-8")
    logger.info("Wrote HTML report: %s", report_path)

    return {
        "history": history_path,
        "latest": latest_path,
        "backtest": backtest_path,
        "report": report_path,
    }
