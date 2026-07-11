"""HTML sections for historical references and backtests."""

from __future__ import annotations

import html
import logging

import numpy as np
import pandas as pd

from .constants import HISTORICAL_REFERENCE_STAGES
from .formatting import format_decimal, format_plain_percent, format_score, format_signed_percent
from .time_series import future_max_drawdown, scaled_index_series

logger = logging.getLogger(__name__)


def format_score_points(value: float | int | None) -> str:
    text = format_score(value)
    return "NA" if text == "NA" else f"{text} 分"


def previous_score_caption(data: pd.DataFrame) -> str:
    series = data["bubble_score"].dropna()
    if len(series) < 2:
        return "上一交易日：暂无数据"
    previous_date = series.index[-2].strftime("%Y-%m-%d")
    previous_score = format_score(float(series.iloc[-2]))
    return f"上一交易日：{previous_date} · {previous_score}分"


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
    future_years = backtest_summary.get("future_window_years", 3)
    top_decile_threshold = top_decile.get("score_threshold")
    model_card = f"""
      <section class="backtest-card">
        <div class="backtest-card-title">{html.escape(str(model.get("label", "模型")))}</div>
        <div class="backtest-metrics">
          <div>
            <span>相关性</span>
            <strong>{format_decimal(model.get("score_to_future_drawdown_severity_corr"), 2)}</strong>
          </div>
          <div>
            <span>Top 10% 分数门槛</span>
            <strong>{format_score_points(top_decile_threshold)}</strong>
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
        <div class="backtest-explain">
          <p><strong>相关性</strong>：分数与未来 {future_years} 年最大回撤严重程度的相关性；越接近 1，代表高分越容易对应后续深回撤。</p>
          <p><strong>Top 10%</strong>：将月末样本按泡沫分数排序后取最高 10%，本次门槛为 {format_score_points(top_decile_threshold)}。</p>
          <p><strong>后续回撤</strong>：Top 10% 高分月份之后 {future_years} 年 Nasdaq 最大回撤的平均值；负值越大，代表后续压力越明显。</p>
          <p><strong>大跌命中率</strong>：Top 10% 高分月份中，未来 {future_years} 年出现 25% 以上最大回撤的比例。</p>
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
      <div class="section-subtitle">月度样本，观察分数与未来 {future_years} 年 Nasdaq 最大回撤的关系</div>
      <div class="backtest-grid">{model_card}</div>
      {stage_table}
    </section>
"""
