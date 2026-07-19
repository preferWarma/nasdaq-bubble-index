"""Factor definitions and value formatters."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Factor:
    key: str
    name: str
    raw_column: str
    score_column: str
    value_formatter: Callable[[float], str]
    hot_text: str
    warm_text: str
    cool_text: str
    input_candidates: tuple[str, ...]
    source_text: str
    calculation_text: str
    weight: float = 0.0

    def with_weight(self, weight: float) -> "Factor":
        return replace(self, weight=weight)


def fmt_pct(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value * 100:.2f}%"


def fmt_number(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:,.2f}"


def fmt_score(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.1f} 分"


FACTOR_TEMPLATES = [
    Factor(
        key="valuation",
        name="估值水平",
        raw_column="valuation_proxy",
        score_column="valuation_score",
        value_formatter=fmt_number,
        hot_text="估值或估值代理指标处于历史高分位，资产价格相对基本面偏贵。",
        warm_text="估值或估值代理指标偏高，未来收益率的安全垫变薄。",
        cool_text="估值或估值代理指标不极端，估值泡沫压力较低。",
        input_candidates=("PE", "PS", "Nasdaq / GDP", "Nasdaq / M2"),
        source_text="PE、PS 来自可选估值 CSV；Nasdaq、GDP、M2 来自 FRED。",
        calculation_text="优先计算 PE、PS 的 20 年滚动分位并等权平均；两者均缺失时，改用 Nasdaq/GDP 与 Nasdaq/M2 的分位均值。",
    ),
    Factor(
        key="trend_momentum",
        name="趋势动量过热",
        raw_column="trend_momentum_proxy",
        score_column="trend_momentum_score",
        value_formatter=fmt_score,
        hot_text="均线偏离和过去一年涨幅共同处于高分位，趋势交易较拥挤。",
        warm_text="趋势动量偏强，市场预期和追涨交易已有升温。",
        cool_text="趋势动量不极端，价格过热压力较低。",
        input_candidates=("Nasdaq 偏离 200 日均线", "Nasdaq 过去一年涨幅"),
        source_text="Nasdaq 100 指数来自 FRED。",
        calculation_text="分别计算均线偏离和过去一年涨幅的 20 年滚动分位，再对两项分位分等权平均。",
    ),
    Factor(
        key="style_crowding",
        name="成长风格拥挤",
        raw_column="style_crowding_proxy",
        score_column="style_crowding_score",
        value_formatter=fmt_pct,
        hot_text="成长风格相对大盘明显跑赢，科技成长配置拥挤度偏高。",
        warm_text="成长风格相对偏强，风格溢价已有一定积累。",
        cool_text="成长风格相对强弱不极端，风格拥挤度较低。",
        input_candidates=("QQQ / SPY 一年变化", "Nasdaq / S&P 500 一年变化"),
        source_text="QQQ、SPY 来自 Yahoo；Nasdaq 100、S&P 500 来自 FRED。",
        calculation_text="优先使用 QQQ/SPY 相对强弱的一年变化分位；缺失时回退到 Nasdaq/S&P 500 的一年变化分位。",
    ),
    Factor(
        key="concentration",
        name="龙头集中度",
        raw_column="concentration_proxy",
        score_column="concentration_score",
        value_formatter=fmt_pct,
        hot_text="龙头集中度或巨头相对强弱处于高分位，指数对少数大市值公司的依赖较强。",
        warm_text="龙头集中度或巨头相对强弱偏高，市场结构略显拥挤。",
        cool_text="龙头集中度压力不高，市场结构相对均衡。",
        input_candidates=("Top 10 权重", "巨头篮子 / QQQ", "巨头篮子 / QQQ 一年变化"),
        source_text="Top 10 权重来自可选集中度 CSV；巨头股票与 QQQ 来自 Yahoo。",
        calculation_text="优先使用 Top 10 权重的 20 年滚动分位；缺失时，平均巨头篮子相对 QQQ 的水平分位与一年变化分位。",
    ),
    Factor(
        key="sentiment_speculation",
        name="情绪投机",
        raw_column="sentiment_speculation_proxy",
        score_column="sentiment_speculation_score",
        value_formatter=fmt_score,
        hot_text="投机代理指标和低波动自满信号偏热，短期追涨资金较活跃。",
        warm_text="情绪投机因子偏热，需要留意追涨拥挤和风险定价过低。",
        cool_text="情绪投机信号不极端，短线泡沫压力较低。",
        input_candidates=(
            "股票 Put/Call",
            "VIX",
            "QQQ 成交量强度",
            "ARKK / QQQ",
            "ARKK / QQQ 一年变化",
        ),
        source_text="Put/Call 来自可选情绪 CSV，VIX 来自 FRED，QQQ 与 ARKK 来自 Yahoo。",
        calculation_text="Put/Call 越低、VIX 越低，反向分位分越高；缺少 Put/Call 时用 QQQ 成交量强度和 ARKK/QQQ 代理投机程度，再与低 VIX 自满分等权平均。",
    ),
    Factor(
        key="macro_fragility",
        name="宏观/杠杆脆弱性",
        raw_column="macro_fragility_proxy",
        score_column="macro_fragility_score",
        value_formatter=fmt_score,
        hot_text="利率、流动性或融资杠杆信号显示市场脆弱性偏高。",
        warm_text="宏观和杠杆环境对高估值资产有一定约束。",
        cool_text="宏观和杠杆脆弱性不高，对泡沫的助推或刺破压力较弱。",
        input_candidates=("10 年期美债收益率", "M2 同比", "融资余额同比"),
        source_text="10 年期美债与 M2 来自 FRED，融资余额来自 FINRA。",
        calculation_text="分别计算利率、M2 同比和融资余额同比的 20 年滚动分位，再对当期可用项等权平均。",
    ),
]


def default_factor_weights_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "factor_weights.json"


def load_factor_weights(path: str | Path | None = None) -> dict[str, float]:
    weights_path = Path(path) if path else default_factor_weights_path()
    logger.info("Loading factor weights: %s", weights_path)
    payload = json.loads(weights_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Factor weights config must be a JSON object: {weights_path}")
    raw_weights = payload.get("weights", payload)
    if not isinstance(raw_weights, dict):
        raise ValueError(f"Factor weights config must contain a weights object: {weights_path}")

    definition_keys = {factor.key for factor in FACTOR_TEMPLATES}
    configured_keys = set(raw_weights)
    missing = sorted(definition_keys - configured_keys)
    unknown = sorted(configured_keys - definition_keys)
    if missing:
        raise ValueError(f"Factor weights config missing keys: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Factor weights config has unknown keys: {', '.join(unknown)}")

    weights = {}
    for key, value in raw_weights.items():
        try:
            weight = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Factor weight must be numeric for {key}: {value}") from exc
        if weight < 0:
            raise ValueError(f"Factor weight must be non-negative for {key}: {weight}")
        weights[key] = weight

    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("At least one factor weight must be positive")
    return weights


def build_factors(weights: dict[str, float]) -> list[Factor]:
    return [factor.with_weight(weights[factor.key]) for factor in FACTOR_TEMPLATES]


def load_factors(path: str | Path | None = None) -> list[Factor]:
    return build_factors(load_factor_weights(path))
