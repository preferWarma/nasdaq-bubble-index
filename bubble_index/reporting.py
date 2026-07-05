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


def svg_line_chart(data: pd.DataFrame, width: int = 920, height: int = 320) -> str:
    series = data["bubble_score"].dropna().tail(2520)
    if series.empty:
        return ""

    pad_left, pad_top, pad_right, pad_bottom = 42, 18, 18, 34
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    values = series.to_numpy()
    xs = np.linspace(pad_left, pad_left + plot_w, len(values))
    ys = pad_top + (100 - values) / 100 * plot_h
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))

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

    start_label = series.index[0].strftime("%Y-%m")
    end_label = series.index[-1].strftime("%Y-%m-%d")
    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Bubble score history">
  <rect width="{width}" height="{height}" fill="white" />
  {''.join(rects)}
  {''.join(grid)}
  <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="3" />
  <text x="{pad_left}" y="{height - 10}" font-size="12" fill="#475569">{start_label}</text>
  <text x="{width - 110}" y="{height - 10}" font-size="12" fill="#475569">{end_label}</text>
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
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nasdaq 泡沫指数报告</title>
  <style>
    body {{
      margin: 0;
      background: #f8fafc;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 32px 18px 48px;
    }}
    .hero {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 28px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .meta {{ color: #64748b; margin-bottom: 22px; }}
    .score-row {{
      display: grid;
      grid-template-columns: 220px 1fr;
      gap: 24px;
      align-items: center;
    }}
    .score {{
      font-size: 88px;
      line-height: 1;
      font-weight: 800;
      color: {color};
    }}
    .label {{
      display: inline-block;
      padding: 6px 12px;
      border-radius: 999px;
      color: white;
      background: {color};
      font-weight: 700;
    }}
    .chart {{
      margin-top: 24px;
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      overflow: hidden;
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
      margin-top: 18px;
      color: #64748b;
      font-size: 14px;
      line-height: 1.6;
    }}
    @media (max-width: 720px) {{
      .score-row, .factors {{ grid-template-columns: 1fr; }}
      .score {{ font-size: 72px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Nasdaq 泡沫指数</h1>
      <div class="meta">数据日期：{summary["date"]} · 参与因子：{summary["active_factor_count"]} 个</div>
      <div class="score-row">
        <div>
          <div class="score">{score}</div>
          <div class="label">{html.escape(str(summary["risk_label"]))}</div>
        </div>
        <div>
          <p>这个分数用历史分位数把趋势、涨幅、相对强弱、波动率、利率、流动性和杠杆合成到 0-100 区间。分数越高，代表市场状态越接近历史上的高热区。</p>
          <p>它不是买卖信号，更适合做仓位温度计：帮助判断是否该降低追涨、提高止盈纪律，或等待更好的风险补偿。</p>
        </div>
      </div>
    </section>
    <section class="chart">{chart}</section>
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
