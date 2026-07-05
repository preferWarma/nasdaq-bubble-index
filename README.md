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
- `report.html`：可视化报告

## 分数解释

| 分数 | 状态 |
|---:|---|
| 0-40 | 偏冷 |
| 40-60 | 中性 |
| 60-75 | 明显偏热 |
| 75-85 | 高泡沫风险 |
| 85-100 | 极端泡沫风险 |

## 当前因子

| 因子 | 权重 | 说明 |
|---|---:|---|
| 估值水平 | 16% | 优先用 PE/PS；没有时用 Nasdaq/GDP 和 Nasdaq/M2 代理 |
| 价格偏离长期均线 | 13% | Nasdaq 100 相对 200 日均线的偏离 |
| 过去一年涨幅 | 10% | Nasdaq 100 252 个交易日收益率 |
| 纳指相对标普强弱 | 8% | Nasdaq 100 / S&P 500 的一年变化 |
| QQQ/SPY 长历史强弱 | 10% | Yahoo QQQ / SPY 的一年变化 |
| 龙头集中度 | 10% | 优先用 top10 权重；没有时用巨头篮子相对 QQQ 的强弱代理 |
| 投机情绪 | 10% | 优先用 equity put/call；没有时用 QQQ 成交量强度和 ARKK/QQQ 代理 |
| 低波动自满程度 | 7% | VIX 低分位反向计分 |
| 利率压力 | 6% | 10 年期美债收益率历史分位 |
| M2 流动性增速 | 4% | M2 同比增速历史分位 |
| 融资杠杆增速 | 6% | FINRA 融资余额同比增速历史分位 |

所有单因子都先转成滚动历史分位数，再按权重合成。若某个数据源缺失，工具会自动用剩余可用因子重新归一化权重。

## 注意

这只是研究辅助工具，不是投资建议。泡沫分数高不代表市场马上下跌，分数低也不代表没有风险。更合理的用法是辅助仓位纪律、定投节奏和止盈策略。
