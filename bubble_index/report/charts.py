"""Static and interactive chart rendering for the report."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd

from .constants import BUBBLE_STAGE_NOTES
from .formatting import chart_number, format_axis_number, format_decimal, script_json
from .time_series import (
    find_stage_points,
    nearest_index_position,
    scaled_index_series,
    trim_frame_to_range,
    trim_to_recent_years,
    x_axis_ticks,
)


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

      function indexToPercent(index) {
        const lastIndex = Math.max(chartData.dates.length - 1, 0);
        if (!lastIndex) return 0;
        return Math.max(0, Math.min(100, index / lastIndex * 100));
      }

      function zoomValueToIndex(value, fallback) {
        if (value === null || value === undefined) return fallback;
        const dateIndex = chartData.dates.indexOf(String(value));
        if (dateIndex >= 0) return dateIndex;
        const numeric = finiteNumber(value);
        if (Number.isFinite(numeric)) {
          const index = Math.round(numeric);
          if (index >= 0 && index < chartData.dates.length) return index;
        }
        return fallback;
      }

      function finiteNumber(value) {
        if (value === null || value === undefined || value === "") return null;
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : null;
      }

      function zoomPayload(params) {
        if (!params || !Array.isArray(params.batch) || !params.batch.length) return params || {};
        return params.batch.find((item) => (
          finiteNumber(item.start) !== null ||
          finiteNumber(item.end) !== null ||
          item.startValue !== undefined ||
          item.endValue !== undefined
        )) || params.batch[0] || {};
      }

      function extractZoom(params) {
        const zoom = zoomPayload(params);
        let start = finiteNumber(zoom.start);
        let end = finiteNumber(zoom.end);
        if (start === null || end === null) {
          const currentIndexes = zoomToIndexes(currentZoom.start, currentZoom.end);
          const startIndex = zoomValueToIndex(zoom.startValue, currentIndexes.startIndex);
          const endIndex = zoomValueToIndex(zoom.endValue, currentIndexes.endIndex);
          if (zoom.startValue !== undefined || zoom.endValue !== undefined) {
            start = indexToPercent(Math.min(startIndex, endIndex));
            end = indexToPercent(Math.max(startIndex, endIndex));
          }
        }
        return {
          start: start === null ? currentZoom.start : start,
          end: end === null ? currentZoom.end : end
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

      function resetZoom() {
        currentZoom = { start: 0, end: 100 };
        applyVisibleAxisRange(currentZoom.start, currentZoom.end);
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

      bubbleChart.on("datazoom", function (params) {
        handleZoom(params, indexChart, [0, 1]);
      });
      indexChart.on("datazoom", function (params) {
        handleZoom(params, bubbleChart, [0]);
      });
      bubbleChart.on("restore", resetZoom);
      indexChart.on("restore", resetZoom);
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
