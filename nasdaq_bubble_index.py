#!/usr/bin/env python3
"""Build a free-data Nasdaq bubble index report.

The default live mode pulls public FRED CSV data and FINRA margin data. Use
--offline-sample to exercise the full pipeline without network access.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FINRA_MARGIN_XLSX_URL = (
    "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
)
YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    "?period1={period1}&period2={period2}&interval=1d&events=history"
)
MEGA_CAP_TICKERS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO")


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


def read_url_bytes_with_curl(url: str, timeout: int) -> bytes:
    completed = subprocess.run(
        [
            "curl",
            "--http1.1",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            str(timeout),
            url,
        ],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def read_url_bytes_with_urllib(url: str, timeout: int) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "nasdaq-bubble-index/1.0",
            "Accept": "text/csv,application/json,application/vnd.ms-excel,*/*",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def read_url_bytes(url: str, timeout: int = 30) -> bytes:
    if "fred.stlouisfed.org" in url:
        try:
            return read_url_bytes_with_curl(url, timeout)
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            pass

    try:
        return read_url_bytes_with_urllib(url, timeout)
    except Exception as exc:
        try:
            return read_url_bytes_with_curl(url, timeout)
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as curl_exc:
            raise RuntimeError(
                f"Failed to download {url} with urllib and curl fallback: {curl_exc}"
            ) from exc


def fetch_fred_series(series_id: str, start: str) -> pd.Series:
    url = FRED_CSV_URL.format(series_id=series_id)
    raw = read_url_bytes(url)
    data = pd.read_csv(BytesIO(raw), na_values=["."])
    if "observation_date" not in data.columns or series_id not in data.columns:
        raise ValueError(f"Unexpected FRED CSV format for {series_id}")

    series = data.set_index(pd.to_datetime(data["observation_date"]))[series_id]
    series = pd.to_numeric(series, errors="coerce")
    series = series.loc[pd.Timestamp(start) :]
    series.name = series_id.lower()
    return series


def fetch_yahoo_history(ticker: str, start: str, end: date | None = None) -> pd.DataFrame:
    start_ts = int(pd.Timestamp(start, tz="UTC").timestamp())
    end_ts = int(pd.Timestamp(end or date.today(), tz="UTC").timestamp()) + 86400
    url = YAHOO_CHART_URL.format(ticker=ticker, period1=start_ts, period2=end_ts)
    raw = read_url_bytes(url)
    payload = json.loads(raw)
    result = payload.get("chart", {}).get("result") or []
    if not result:
        error = payload.get("chart", {}).get("error")
        raise ValueError(f"Yahoo returned no data for {ticker}: {error}")

    block = result[0]
    timestamps = block.get("timestamp") or []
    quote = (block.get("indicators", {}).get("quote") or [{}])[0]
    adjclose = (block.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
    close = adjclose or quote.get("close")
    if not timestamps or close is None:
        raise ValueError(f"Yahoo response missing price data for {ticker}")

    index = pd.to_datetime(timestamps, unit="s").normalize()
    out = pd.DataFrame(index=index)
    key = ticker.lower().replace("-", "_")
    out[f"{key}_close"] = pd.to_numeric(pd.Series(close, index=index), errors="coerce")
    if "volume" in quote:
        out[f"{key}_volume"] = pd.to_numeric(
            pd.Series(quote["volume"], index=index), errors="coerce"
        )
    return out.loc[pd.Timestamp(start) :]


def load_optional_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Optional CSV not found: {csv_path}")
    frame = pd.read_csv(csv_path)
    date_col = next((col for col in frame.columns if col.lower() == "date"), None)
    if date_col is None:
        raise ValueError(f"Optional CSV must contain a date column: {csv_path}")
    frame = frame.rename(columns={col: col.strip().lower() for col in frame.columns})
    frame = frame.set_index(pd.to_datetime(frame["date"])).drop(columns=["date"])
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.sort_index()


def join_daily(frame: pd.DataFrame, extra: pd.DataFrame, ffill: bool = True) -> pd.DataFrame:
    if extra.empty:
        return frame
    aligned = extra.reindex(frame.index.union(extra.index)).sort_index()
    if ffill:
        aligned = aligned.ffill()
    aligned = aligned.reindex(frame.index)
    return frame.join(aligned, how="left")


def parse_finra_month(value: object) -> pd.Timestamp | pd.NaT:
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    for fmt in ("%b-%y", "%b-%Y", "%Y-%m", "%Y-%m-%d"):
        try:
            return pd.to_datetime(text, format=fmt) + pd.offsets.MonthEnd(0)
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed + pd.offsets.MonthEnd(0)


def fetch_finra_margin(start: str) -> pd.DataFrame:
    raw = read_url_bytes(FINRA_MARGIN_XLSX_URL)
    sheets = pd.read_excel(BytesIO(raw), sheet_name=None, header=None)

    table = None
    for frame in sheets.values():
        for idx, row in frame.iterrows():
            row_text = " ".join(str(item) for item in row.dropna().tolist())
            if ("Month/Year" in row_text or "Year-Month" in row_text) and "Debit Balances" in row_text:
                headers = frame.iloc[idx].ffill().astype(str).tolist()
                table = frame.iloc[idx + 1 :].copy()
                table.columns = headers
                break
        if table is not None:
            break

    if table is None:
        raise ValueError("Could not find FINRA margin table in workbook")

    month_col = next(col for col in table.columns if "Month/Year" in col or "Year-Month" in col)
    debit_col = next(col for col in table.columns if "Debit Balances" in col)
    cash_col = next(col for col in table.columns if "Cash Accounts" in col)
    margin_credit_col = next(
        col for col in table.columns if "Securities Margin Accounts" in col and col != debit_col
    )

    out = pd.DataFrame(
        {
            "margin_debt": pd.to_numeric(
                table[debit_col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            ).to_numpy(),
            "cash_credit": pd.to_numeric(
                table[cash_col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            ).to_numpy(),
            "margin_credit": pd.to_numeric(
                table[margin_credit_col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            ).to_numpy(),
        },
        index=table[month_col].map(parse_finra_month),
    )
    out = out.dropna(how="all")
    out = out[~out.index.isna()].sort_index()
    out = out.loc[pd.Timestamp(start) :]
    out["margin_debt_yoy"] = out["margin_debt"].pct_change(12)
    out["margin_cash_ratio"] = (out["cash_credit"] + out["margin_credit"]) / out[
        "margin_debt"
    ]
    return out


def load_live_data(
    start: str,
    include_margin: bool = True,
    include_yahoo: bool = True,
    valuation_csv: str | None = None,
    concentration_csv: str | None = None,
    put_call_csv: str | None = None,
) -> pd.DataFrame:
    fred_ids = {
        "nasdaq": "NASDAQ100",
        "sp500": "SP500",
        "vix": "VIXCLS",
        "dgs10": "DGS10",
        "m2": "M2SL",
        "gdp": "GDP",
    }
    series = {name: fetch_fred_series(series_id, start) for name, series_id in fred_ids.items()}
    frame = pd.concat(series.values(), axis=1, sort=True).sort_index()
    frame.columns = list(series.keys())
    frame = frame.ffill()

    if include_yahoo:
        yahoo_tickers = ("QQQ", "SPY", "ARKK", *MEGA_CAP_TICKERS)
        yahoo_frames = []
        for ticker in yahoo_tickers:
            try:
                yahoo_frames.append(fetch_yahoo_history(ticker, start))
            except (URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
                print(f"WARNING: Yahoo data skipped for {ticker}: {exc}")
        if yahoo_frames:
            yahoo_data = pd.concat(yahoo_frames, axis=1, sort=True).sort_index()
            frame = join_daily(frame, yahoo_data, ffill=True)

    if include_margin:
        try:
            margin = fetch_finra_margin(start)
            frame = join_daily(frame, margin, ffill=True)
        except (URLError, TimeoutError, ValueError, StopIteration, OSError) as exc:
            print(f"WARNING: FINRA margin data skipped: {exc}")

    for optional_path in (valuation_csv, concentration_csv, put_call_csv):
        optional_data = load_optional_csv(optional_path)
        frame = join_daily(frame, optional_data, ffill=True)

    return frame


def load_offline_sample(start: str) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, end=date.today())
    rng = np.random.default_rng(7)
    t = np.arange(len(dates))
    base = 1000 * np.exp(t / 2600) * (1 + 0.12 * np.sin(t / 260))
    noise = np.exp(np.cumsum(rng.normal(0, 0.008, len(dates))))
    nasdaq = base * noise
    sp500 = 900 * np.exp(t / 3300) * np.exp(np.cumsum(rng.normal(0, 0.005, len(dates))))
    vix = np.clip(22 + 8 * np.sin(t / 180) + rng.normal(0, 3, len(dates)), 9, 65)
    dgs10 = np.clip(3.0 + 1.2 * np.sin(t / 500) + rng.normal(0, 0.08, len(dates)), 0.5, 6)
    m2 = 7000 * np.exp(t / 3600) * (1 + 0.04 * np.sin(t / 400))
    gdp = 14000 * np.exp(t / 4200) * (1 + 0.02 * np.sin(t / 520))
    margin = 250000 * np.exp(t / 3200) * (1 + 0.18 * np.sin(t / 340))
    qqq = nasdaq / nasdaq[0] * 45
    spy = sp500 / sp500[0] * 95
    arkk = qqq * (1 + 0.45 * np.sin(t / 300)) * np.exp(np.cumsum(rng.normal(0, 0.007, len(dates))))
    qqq_volume = 45_000_000 * (1 + 0.25 * np.sin(t / 90)) * np.exp(
        rng.normal(0, 0.18, len(dates))
    )

    frame = pd.DataFrame(
        {
            "nasdaq": nasdaq,
            "sp500": sp500,
            "vix": vix,
            "dgs10": dgs10,
            "m2": m2,
            "gdp": gdp,
            "margin_debt": margin,
            "qqq_close": qqq,
            "spy_close": spy,
            "arkk_close": arkk,
            "qqq_volume": qqq_volume,
        },
        index=dates,
    )
    for idx, ticker in enumerate(MEGA_CAP_TICKERS):
        drift = 1 + 0.08 * idx
        frame[f"{ticker.lower()}_close"] = qqq * drift * (
            1 + 0.22 * np.sin(t / (240 + idx * 15))
        )
    frame["margin_debt_yoy"] = frame["margin_debt"].pct_change(252)
    return frame


def rolling_percentile(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    def score(values: np.ndarray) -> float:
        valid = values[~np.isnan(values)]
        if len(valid) < min_periods:
            return np.nan
        last = valid[-1]
        return float(np.sum(valid <= last) / len(valid) * 100)

    return series.rolling(window=window, min_periods=min_periods).apply(score, raw=True)


def normalize_percent_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return np.where(numeric > 1.5, numeric / 100, numeric)


def first_existing_column(data: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    return next((name for name in names if name in data.columns), None)


def compute_scores(frame: pd.DataFrame, window_years: int = 10) -> pd.DataFrame:
    data = frame.copy().sort_index()
    window = int(window_years * 252)
    min_periods = min(756, max(126, window // 3))

    data["nasdaq_200dma"] = data["nasdaq"].rolling(200, min_periods=160).mean()
    data["trend_deviation"] = data["nasdaq"] / data["nasdaq_200dma"] - 1
    data["nasdaq_1y_return"] = data["nasdaq"].pct_change(252)
    data["relative_strength"] = data["nasdaq"] / data["sp500"]
    data["relative_strength_1y"] = data["relative_strength"].pct_change(252)
    data["m2_yoy"] = data["m2"].pct_change(252)

    if "gdp" in data.columns:
        data["nasdaq_to_gdp"] = data["nasdaq"] / data["gdp"]
    if "m2" in data.columns:
        data["nasdaq_to_m2"] = data["nasdaq"] / data["m2"]

    if {"qqq_close", "spy_close"}.issubset(data.columns):
        data["qqq_spy"] = data["qqq_close"] / data["spy_close"]
        data["qqq_spy_1y"] = data["qqq_spy"].pct_change(252)

    mega_cols = [f"{ticker.lower()}_close" for ticker in MEGA_CAP_TICKERS]
    mega_cols = [col for col in mega_cols if col in data.columns]
    if mega_cols and "qqq_close" in data.columns:
        normalized = pd.DataFrame(index=data.index)
        for col in mega_cols:
            first = data[col].dropna()
            if not first.empty:
                normalized[col] = data[col] / first.iloc[0]
        qqq_base = data["qqq_close"].dropna()
        if not normalized.empty and not qqq_base.empty:
            data["mega_cap_basket"] = normalized.mean(axis=1)
            data["mega_cap_relative"] = data["mega_cap_basket"] / (
                data["qqq_close"] / qqq_base.iloc[0]
            )
            data["mega_cap_relative_1y"] = data["mega_cap_relative"].pct_change(252)

    if {"arkk_close", "qqq_close"}.issubset(data.columns):
        data["arkk_qqq"] = data["arkk_close"] / data["qqq_close"]
        data["arkk_qqq_1y"] = data["arkk_qqq"].pct_change(252)
    if "qqq_volume" in data.columns:
        data["qqq_volume_intensity"] = data["qqq_volume"] / data["qqq_volume"].rolling(
            252, min_periods=160
        ).mean()

    pe_col = first_existing_column(data, ("nasdaq_pe", "pe", "pe_ratio"))
    ps_col = first_existing_column(data, ("nasdaq_ps", "ps", "price_to_sales", "ps_ratio"))
    if pe_col:
        data["nasdaq_pe"] = data[pe_col]
    if ps_col:
        data["nasdaq_ps"] = data[ps_col]

    top10_col = first_existing_column(data, ("top10_weight", "nasdaq_top10_weight"))
    if top10_col:
        data["top10_weight"] = normalize_percent_series(data[top10_col])

    put_call_col = first_existing_column(
        data, ("equity_put_call", "put_call", "equity_put_call_ratio")
    )
    if put_call_col:
        data["equity_put_call"] = data[put_call_col]

    data["trend_score"] = rolling_percentile(data["trend_deviation"], window, min_periods)
    data["return_score"] = rolling_percentile(data["nasdaq_1y_return"], window, min_periods)
    data["relative_score"] = rolling_percentile(
        data["relative_strength_1y"], window, min_periods
    )
    data["complacency_score"] = 100 - rolling_percentile(data["vix"], window, min_periods)
    data["rate_pressure_score"] = rolling_percentile(data["dgs10"], window, min_periods)
    data["liquidity_score"] = rolling_percentile(data["m2_yoy"], window, min_periods)

    valuation_scores = []
    if "nasdaq_pe" in data.columns:
        valuation_scores.append(rolling_percentile(data["nasdaq_pe"], window, min_periods))
    if "nasdaq_ps" in data.columns:
        valuation_scores.append(rolling_percentile(data["nasdaq_ps"], window, min_periods))
    if not valuation_scores:
        if "nasdaq_to_gdp" in data.columns:
            valuation_scores.append(rolling_percentile(data["nasdaq_to_gdp"], window, min_periods))
        if "nasdaq_to_m2" in data.columns:
            valuation_scores.append(rolling_percentile(data["nasdaq_to_m2"], window, min_periods))
    if valuation_scores:
        data["valuation_score"] = pd.concat(valuation_scores, axis=1).mean(axis=1)
        if "nasdaq_pe" in data.columns:
            data["valuation_proxy"] = data["nasdaq_pe"]
        elif "nasdaq_ps" in data.columns:
            data["valuation_proxy"] = data["nasdaq_ps"]
        elif "nasdaq_to_gdp" in data.columns:
            data["valuation_proxy"] = data["nasdaq_to_gdp"]

    if "qqq_spy_1y" in data.columns:
        data["qqq_spy_score"] = rolling_percentile(data["qqq_spy_1y"], window, min_periods)

    if "top10_weight" in data.columns:
        data["concentration_proxy"] = data["top10_weight"]
        data["concentration_score"] = rolling_percentile(data["top10_weight"], window, min_periods)
    elif "mega_cap_relative_1y" in data.columns:
        concentration_scores = []
        if "mega_cap_relative" in data.columns:
            concentration_scores.append(
                rolling_percentile(data["mega_cap_relative"], window, min_periods)
            )
        data["concentration_proxy"] = data["mega_cap_relative_1y"]
        concentration_scores.append(
            rolling_percentile(data["mega_cap_relative_1y"], window, min_periods)
        )
        data["concentration_score"] = pd.concat(concentration_scores, axis=1).mean(axis=1)

    speculation_scores = []
    if "equity_put_call" in data.columns:
        speculation_scores.append(100 - rolling_percentile(data["equity_put_call"], window, min_periods))
        data["speculation_proxy"] = data["equity_put_call"]
    else:
        if "qqq_volume_intensity" in data.columns:
            speculation_scores.append(
                rolling_percentile(data["qqq_volume_intensity"], window, min_periods)
            )
            data["speculation_proxy"] = data["qqq_volume_intensity"]
        if "arkk_qqq_1y" in data.columns:
            if "arkk_qqq" in data.columns:
                speculation_scores.append(rolling_percentile(data["arkk_qqq"], window, min_periods))
                data["speculation_proxy"] = data["arkk_qqq"]
            speculation_scores.append(rolling_percentile(data["arkk_qqq_1y"], window, min_periods))
            if "speculation_proxy" not in data.columns:
                data["speculation_proxy"] = data["arkk_qqq_1y"]
    if speculation_scores:
        data["speculation_score"] = pd.concat(speculation_scores, axis=1).mean(axis=1)

    if "margin_debt_yoy" in data.columns:
        data["margin_score"] = rolling_percentile(data["margin_debt_yoy"], window, min_periods)

    score_cols = [factor.score_column for factor in FACTORS if factor.score_column in data.columns]
    weighted_sum = pd.Series(0.0, index=data.index)
    active_weight = pd.Series(0.0, index=data.index)
    for factor in FACTORS:
        if factor.score_column not in data.columns:
            continue
        available = data[factor.score_column].notna()
        weighted_sum = weighted_sum + data[factor.score_column].fillna(0) * factor.weight
        active_weight = active_weight + available.astype(float) * factor.weight

    data["bubble_score"] = np.where(active_weight > 0, weighted_sum / active_weight, np.nan)
    data["active_factor_count"] = data[score_cols].notna().sum(axis=1)
    return data


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
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_complete_row(data)
    summary = build_summary(latest)

    history_path = out_dir / "bubble_history.csv"
    latest_path = out_dir / "latest.json"
    report_path = out_dir / "report.html"

    data.to_csv(history_path, index_label="date")
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_html_report(data, summary), encoding="utf-8")

    return {
        "history": history_path,
        "latest": latest_path,
        "report": report_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate a free-data Nasdaq bubble index.")
    parser.add_argument("--start", default="2006-01-01", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--out", default="output", help="Output directory.")
    parser.add_argument(
        "--window-years",
        type=int,
        default=10,
        help="Rolling percentile window in trading years.",
    )
    parser.add_argument(
        "--offline-sample",
        action="store_true",
        help="Use deterministic sample data instead of downloading live data.",
    )
    parser.add_argument(
        "--no-finra",
        action="store_true",
        help="Skip FINRA margin data in live mode.",
    )
    parser.add_argument(
        "--no-yahoo",
        action="store_true",
        help="Skip Yahoo historical ETF and stock data in live mode.",
    )
    parser.add_argument(
        "--valuation-csv",
        help="Optional CSV with date plus pe/ps or nasdaq_pe/nasdaq_ps columns.",
    )
    parser.add_argument(
        "--concentration-csv",
        help="Optional CSV with date plus top10_weight column.",
    )
    parser.add_argument(
        "--put-call-csv",
        help="Optional CSV with date plus equity_put_call column.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.offline_sample:
        raw = load_offline_sample(args.start)
    else:
        raw = load_live_data(
            args.start,
            include_margin=not args.no_finra,
            include_yahoo=not args.no_yahoo,
            valuation_csv=args.valuation_csv,
            concentration_csv=args.concentration_csv,
            put_call_csv=args.put_call_csv,
        )

    scored = compute_scores(raw, window_years=args.window_years)
    paths = write_outputs(scored, Path(args.out))
    summary = json.loads(paths["latest"].read_text(encoding="utf-8"))

    print(f"Nasdaq bubble score: {summary['bubble_score']} ({summary['risk_label']})")
    print(f"Data date: {summary['date']}")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
