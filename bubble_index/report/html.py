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
