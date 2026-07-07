# Nasdaq Bubble Index

一个免费数据源版本的纳斯达克泡沫指数计算工具。它会自动拉取公开数据、计算 0-100 分的泡沫温度、输出历史 CSV、今日 JSON 和 HTML 报告。

## 数据源

- FRED：`NASDAQ100`、`SP500`、`VIXCLS`、`DGS10`、`M2SL`
- FINRA：`margin-statistics.xlsx`
- Yahoo Finance chart 接口：`QQQ`、`SPY`、`ARKK`、若干 Nasdaq 龙头个股历史价格和成交量

FRED 用于指数、波动率、利率、GDP 和流动性；FINRA 用于融资余额。FINRA 是月度数据，工具会向前填充到每日频率。Yahoo 数据用于补充 QQQ/SPY 长历史相对强弱、龙头集中度代理和投机情绪代理。

## 快速开始

```bash
python -m pip install -r requirements.txt
python nasdaq_bubble_index.py
```

默认会从 1986 年开始拉取可用数据，并使用 20 年滚动窗口计算历史分位数。

因子权重默认从 `config/factor_weights.json` 读取。你也可以传入另一份权重配置：

```bash
python nasdaq_bubble_index.py --factor-weights config/factor_weights.json
```

配置文件需要包含全部 6 个分组因子的 key：

```json
{
  "valuation": 0.25,
  "trend_momentum": 0.20,
  "style_crowding": 0.15,
  "concentration": 0.15,
  "sentiment_speculation": 0.15,
  "macro_fragility": 0.10
}
```

如果你有更好的免费或付费历史数据，可以用 CSV 替换代理因子：

```bash
python nasdaq_bubble_index.py \
  --valuation-csv data/valuation.csv \
  --concentration-csv data/concentration.csv \
  --put-call-csv data/put_call.csv
```

CSV 需要包含 `date` 列。估值 CSV 支持 `pe`、`ps`、`nasdaq_pe`、`nasdaq_ps`；集中度 CSV 支持 `top10_weight`；期权情绪 CSV 支持 `equity_put_call`。

当前环境无法访问外部金融网站时，可以先运行离线样例验证完整流程：

```bash
python nasdaq_bubble_index.py --offline-sample
```

输出文件默认在 `output/`：

- `bubble_history.csv`：每日因子与总分
- `latest.json`：最新分数和解释
- `backtest_summary.json`：6 组因子方案的回测摘要
- `report.html`：可视化报告

## 分数解释

| 分数 | 状态 |
|---:|---|
| 0-40 | 偏冷 |
| 40-60 | 中性 |
| 60-75 | 明显偏热 |
| 75-85 | 高泡沫风险 |
| 85-100 | 极端泡沫风险 |

## 当前分组因子

| 因子 | 配置 key | 默认权重 | 说明 |
|---|---|---:|---|
| 估值水平 | `valuation` | 25% | 优先用 PE/PS；没有时用 Nasdaq/GDP 和 Nasdaq/M2 代理 |
| 趋势动量过热 | `trend_momentum` | 20% | 价格偏离 200 日均线和过去一年涨幅的均值 |
| 成长风格拥挤 | `style_crowding` | 15% | 优先用 QQQ/SPY 一年强弱；缺失时回退到 Nasdaq/S&P 500 |
| 龙头集中度 | `concentration` | 15% | 优先用 top10 权重；没有时用巨头篮子相对 QQQ 的强弱代理 |
| 情绪投机 | `sentiment_speculation` | 15% | 投机代理指标和低波动自满程度的均值 |
| 宏观/杠杆脆弱性 | `macro_fragility` | 10% | 10 年期美债、M2 同比和融资杠杆增速的均值 |

所有底层单因子都先转成 20 年滚动历史分位数，再按分组聚合，最后按分组权重合成。若某个数据源缺失，工具会自动用剩余可用分组重新归一化权重。

## 回测摘要

报告会用月度样本评估 6 组因子方案，观察分数与未来 3 年 Nasdaq 最大回撤的关系。`backtest_summary.json` 中包含：

- 分数与未来回撤严重程度的相关性
- Top 10% 高分月份的平均后续最大回撤
- 75 分以上和 85 分以上样本的后续大跌命中率
- 2000、2007、2018、2020、2021、2022 等历史阶段的峰值分数和后续回撤

## 注意

这只是研究辅助工具，不是投资建议。泡沫分数高不代表市场马上下跌，分数低也不代表没有风险。更合理的用法是辅助仓位纪律、定投节奏和止盈策略。
