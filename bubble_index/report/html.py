"""Full HTML report rendering."""

from __future__ import annotations

import html
import logging

import pandas as pd

from .charts import interactive_chart_bootstrap, render_interactive_charts
from .formatting import format_score
from .gauge import svg_score_gauge
from .sections import previous_score_caption, render_backtest_section, render_reference_section
from .summary import risk_label

logger = logging.getLogger(__name__)


def manual_refresh_bootstrap() -> str:
    return """
  <script>
    (function () {
      const refreshParam = "_report_refresh";
      const currentUrl = new URL(window.location.href);
      if (currentUrl.searchParams.has(refreshParam) && window.history.replaceState) {
        currentUrl.searchParams.delete(refreshParam);
        window.history.replaceState(null, "", currentUrl.toString());
      }

      const refreshButton = document.querySelector("[data-refresh-report]");
      if (!refreshButton) {
        return;
      }

      refreshButton.addEventListener("click", function () {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.set(refreshParam, Date.now().toString());
        refreshButton.disabled = true;
        refreshButton.querySelector(".refresh-label").textContent = "刷新中";
        window.location.replace(nextUrl.toString());
      });
    })();
  </script>
"""


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
        previous_score = format_score(factor.get("previous_score"))
        active_inputs = factor.get("active_inputs") or []
        active_input_chips = "".join(
            f'<span class="factor-input-chip">{html.escape(str(item))}</span>'
            for item in active_inputs
        )
        if not active_input_chips:
            active_input_chips = '<span class="factor-input-empty">数据不足</span>'
        candidate_text = " · ".join(str(item) for item in factor.get("input_candidates") or [])
        factor_cards.append(
            f"""
      <section class="factor">
        <div class="factor-head">
          <div class="factor-title">特征 {idx} · {html.escape(str(factor["name"]))}</div>
          <div class="factor-weight">权重 {float(factor["weight"]) * 100:.1f}%</div>
        </div>
        <div class="factor-score" style="color:{card_color}">{score_value if score_value is not None else "NA"} 分</div>
        <div class="factor-previous">上一交易日分数：{html.escape(previous_score)} 分</div>
        <div class="factor-value">当前值：{html.escape(str(factor["display_value"]))}</div>
        <p class="factor-reason">{html.escape(str(factor["reason"]))}</p>
        <div class="factor-inputs">
          <span class="factor-input-label">本期采用</span>
          <div class="factor-input-list">{active_input_chips}</div>
        </div>
        <details class="factor-method">
          <summary>指标来源与计算规则</summary>
          <div class="factor-method-body">
            <div><strong>候选指标</strong><span>{html.escape(candidate_text)}</span></div>
            <div><strong>数据来源</strong><span>{html.escape(str(factor.get("source_text") or ""))}</span></div>
            <div><strong>计算方式</strong><span>{html.escape(str(factor.get("calculation_text") or ""))}</span></div>
          </div>
        </details>
      </section>
"""
        )

    charts = render_interactive_charts(data)
    chart_bootstrap = interactive_chart_bootstrap() if charts else ""
    refresh_bootstrap = manual_refresh_bootstrap()
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
    .header-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .brand {{
      color: #94a3b8;
      font-size: 18px;
      font-weight: 700;
    }}
    .refresh-report {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid #e2e8f0;
      border-radius: 999px;
      background: #ffffff;
      color: #334155;
      padding: 8px 13px;
      font: inherit;
      font-size: 14px;
      font-weight: 800;
      line-height: 1;
      cursor: pointer;
      box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
    }}
    .refresh-report:hover {{
      border-color: #cbd5e1;
      color: #0f172a;
    }}
    .refresh-report:disabled {{
      cursor: wait;
      opacity: 0.72;
    }}
    .refresh-icon {{
      display: inline-block;
      font-size: 15px;
      line-height: 1;
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
    .backtest-explain {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 18px;
      margin-top: 18px;
      padding-top: 15px;
      border-top: 1px solid #e5e7eb;
      color: #475569;
      font-size: 13px;
      line-height: 1.5;
    }}
    .backtest-explain p {{
      margin: 0;
    }}
    .backtest-explain strong {{
      color: #0f172a;
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
    .chart-range-controls {{
      display: grid;
      grid-template-columns: repeat(2, minmax(130px, 1fr)) auto;
      gap: 8px;
      align-items: end;
      min-width: min(100%, 430px);
    }}
    .chart-range-controls label {{
      display: grid;
      gap: 4px;
      color: #64748b;
      font-size: 12px;
      font-weight: 900;
    }}
    .chart-range-controls input {{
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #dbe3ef;
      border-radius: 7px;
      background: #ffffff;
      color: #0f172a;
      padding: 7px 8px;
      font: inherit;
      font-size: 13px;
      font-weight: 800;
      min-height: 34px;
    }}
    .chart-range-controls input:focus {{
      outline: 2px solid rgba(37, 99, 235, 0.18);
      border-color: #93c5fd;
    }}
    .chart-range-controls button {{
      border: 1px solid #dbe3ef;
      border-radius: 7px;
      background: #ffffff;
      color: #334155;
      padding: 8px 11px;
      font: inherit;
      font-size: 13px;
      font-weight: 900;
      min-height: 34px;
      cursor: pointer;
    }}
    .chart-range-controls button:hover {{
      border-color: #cbd5e1;
      color: #0f172a;
    }}
    .chart-range-message {{
      grid-column: 1 / -1;
      min-height: 15px;
      color: #b91c1c;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.25;
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
    .factor-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}
    .factor-title {{ color: #334155; font-weight: 800; }}
    .factor-score {{ margin-top: 12px; font-size: 32px; font-weight: 800; }}
    .factor-previous {{ margin-top: 2px; color: #64748b; font-size: 13px; font-weight: 800; }}
    .factor-weight {{
      flex: 0 0 auto;
      color: #475569;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .factor-value {{ margin-top: 4px; color: #64748b; }}
    .factor-reason {{ margin: 10px 0 0; line-height: 1.55; }}
    .factor-inputs {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: start;
      gap: 9px;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid #edf1f5;
    }}
    .factor-input-label {{
      padding-top: 3px;
      color: #64748b;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .factor-input-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      min-width: 0;
    }}
    .factor-input-chip {{
      border: 1px solid #dbe4ec;
      border-radius: 6px;
      background: #f8fafc;
      color: #334155;
      padding: 3px 7px;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.35;
    }}
    .factor-input-empty {{
      color: #94a3b8;
      font-size: 12px;
      font-weight: 700;
    }}
    .factor-method {{
      margin-top: 10px;
      border-top: 1px solid #edf1f5;
      color: #475569;
    }}
    .factor-method summary {{
      padding: 10px 0 0;
      color: #334155;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }}
    .factor-method summary::marker {{ color: #94a3b8; }}
    .factor-method-body {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
      padding: 11px 12px;
      border-left: 3px solid #cbd5e1;
      background: #f8fafc;
      font-size: 12px;
      line-height: 1.55;
    }}
    .factor-method-body div {{
      display: grid;
      grid-template-columns: 58px minmax(0, 1fr);
      gap: 8px;
    }}
    .factor-method-body strong {{ color: #334155; }}
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
      .interactive-chart-head {{
        flex-direction: column;
      }}
      .chart-range-controls {{
        width: 100%;
      }}
    }}
    @media (max-width: 720px) {{
      main {{
        padding: 18px 12px 40px;
      }}
      .poster-head {{
        padding: 8px 10px 18px;
      }}
      .header-bar {{
        align-items: flex-start;
      }}
      .brand {{
        font-size: 14px;
      }}
      .refresh-report {{
        padding: 7px 10px;
        font-size: 13px;
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
      .backtest-metrics,
      .backtest-explain {{
        grid-template-columns: 1fr;
      }}
      .interactive-chart-section {{
        padding: 14px 8px 12px;
      }}
      .chart-range-controls {{
        grid-template-columns: 1fr 1fr;
      }}
      .chart-range-controls button {{
        grid-column: 1 / -1;
      }}
      .bubble-echart {{
        height: 330px;
      }}
      .index-echart {{
        height: 380px;
      }}
      .factor-method-body div {{
        grid-template-columns: 1fr;
        gap: 2px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="poster-head">
      <div class="header-bar">
        <div class="brand">Nasdaq Bubble Index</div>
        <button class="refresh-report" type="button" data-refresh-report title="重新加载最新已部署报告">
          <span class="refresh-icon" aria-hidden="true">↻</span>
          <span class="refresh-label">刷新报告</span>
        </button>
      </div>
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
  {refresh_bootstrap}
  {chart_bootstrap}
</body>
</html>
"""
