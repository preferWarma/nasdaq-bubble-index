"""Factor definitions and value formatters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

@dataclass(frozen=True)
class Factor:
    key: str
    name: str
    weight: float
    raw_column: str
    score_column: str
    value_formatter: Callable[[float], str]
    hot_text: str
    warm_text: str
    cool_text: str


def fmt_pct(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value * 100:.2f}%"


def fmt_number(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:,.2f}"


def fmt_yield(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.2f}%"


FACTORS = [
    Factor(
        key="valuation",
        name="估值水平",
        weight=0.16,
        raw_column="valuation_proxy",
        score_column="valuation_score",
        value_formatter=fmt_number,
        hot_text="估值或估值代理指标处于历史高分位，资产价格相对基本面偏贵。",
        warm_text="估值或估值代理指标偏高，未来收益率的安全垫变薄。",
        cool_text="估值或估值代理指标不极端，估值泡沫压力较低。",
    ),
    Factor(
        key="trend",
        name="价格偏离长期均线",
        weight=0.13,
        raw_column="trend_deviation",
        score_column="trend_score",
        value_formatter=fmt_pct,
        hot_text="价格显著高于 200 日均线，趋势过热信号偏强。",
        warm_text="价格高于长期均线，趋势偏热但还不是极端状态。",
        cool_text="价格相对长期均线不拥挤，趋势泡沫压力较低。",
    ),
    Factor(
        key="return_1y",
        name="过去一年涨幅",
        weight=0.10,
        raw_column="nasdaq_1y_return",
        score_column="return_score",
        value_formatter=fmt_pct,
        hot_text="过去一年涨幅处于历史高分位，追涨情绪值得警惕。",
        warm_text="过去一年收益偏强，市场预期已经不低。",
        cool_text="过去一年涨幅不极端，动量风险较低。",
    ),
    Factor(
        key="relative_strength",
        name="纳指相对标普强弱",
        weight=0.08,
        raw_column="relative_strength_1y",
        score_column="relative_score",
        value_formatter=fmt_pct,
        hot_text="Nasdaq 相对 S&P 500 大幅跑赢，科技成长风格较拥挤。",
        warm_text="Nasdaq 相对大盘偏强，成长风格有一定拥挤度。",
        cool_text="Nasdaq 相对大盘没有明显过热。",
    ),
    Factor(
        key="qqq_spy_long",
        name="QQQ/SPY 长历史强弱",
        weight=0.10,
        raw_column="qqq_spy_1y",
        score_column="qqq_spy_score",
        value_formatter=fmt_pct,
        hot_text="QQQ 相对 SPY 的一年强弱处于高分位，成长风格相对大盘明显拥挤。",
        warm_text="QQQ 相对 SPY 偏强，科技成长风格已有一定溢价。",
        cool_text="QQQ 相对 SPY 不极端，风格拥挤度较低。",
    ),
    Factor(
        key="concentration",
        name="龙头集中度",
        weight=0.10,
        raw_column="concentration_proxy",
        score_column="concentration_score",
        value_formatter=fmt_pct,
        hot_text="龙头集中度或巨头相对强弱处于高分位，指数对少数大市值公司的依赖较强。",
        warm_text="龙头集中度或巨头相对强弱偏高，市场结构略显拥挤。",
        cool_text="龙头集中度压力不高，市场结构相对均衡。",
    ),
    Factor(
        key="speculation",
        name="投机情绪",
        weight=0.10,
        raw_column="speculation_proxy",
        score_column="speculation_score",
        value_formatter=fmt_number,
        hot_text="期权或投机代理指标处于高分位，短期追涨资金较活跃。",
        warm_text="投机情绪偏热，需要留意追涨拥挤。",
        cool_text="投机情绪不极端，短线泡沫压力较低。",
    ),
    Factor(
        key="complacency",
        name="低波动自满程度",
        weight=0.07,
        raw_column="vix",
        score_column="complacency_score",
        value_formatter=fmt_number,
        hot_text="VIX 处于较低历史分位，市场可能存在乐观或自满情绪。",
        warm_text="波动率不高，风险定价偏平静。",
        cool_text="波动率不低，市场没有明显自满。",
    ),
    Factor(
        key="rate_pressure",
        name="利率压力",
        weight=0.06,
        raw_column="dgs10",
        score_column="rate_pressure_score",
        value_formatter=fmt_yield,
        hot_text="10 年期美债收益率处于高分位，高估值资产的折现压力较强。",
        warm_text="利率水平偏高，对长久期成长资产有一定约束。",
        cool_text="利率压力不高，对估值的压制较弱。",
    ),
    Factor(
        key="liquidity",
        name="M2 流动性增速",
        weight=0.04,
        raw_column="m2_yoy",
        score_column="liquidity_score",
        value_formatter=fmt_pct,
        hot_text="M2 同比增速处于高分位，流动性对风险资产较友好。",
        warm_text="M2 增速偏高，流动性环境有一定支撑。",
        cool_text="M2 增速不高，流动性泡沫助推较弱。",
    ),
    Factor(
        key="margin",
        name="融资杠杆增速",
        weight=0.06,
        raw_column="margin_debt_yoy",
        score_column="margin_score",
        value_formatter=fmt_pct,
        hot_text="FINRA 融资余额同比增速处于高分位，杠杆追涨风险上升。",
        warm_text="融资余额同比偏强，杠杆资金有一定升温。",
        cool_text="融资余额同比不高，杠杆泡沫压力较低。",
    ),
]
