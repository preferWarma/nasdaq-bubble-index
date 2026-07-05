"""Data loading for live public sources and deterministic offline samples."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .constants import FRED_CSV_URL, FINRA_MARGIN_XLSX_URL, MEGA_CAP_TICKERS, YAHOO_CHART_URL

logger = logging.getLogger(__name__)


def read_url_bytes_with_curl(url: str, timeout: int) -> bytes:
    logger.debug("Downloading with curl: %s", url)
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
    logger.debug("Downloading with urllib: %s", url)
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
        ) as exc:
            logger.debug("FRED curl download failed, trying urllib: %s", exc)
            pass

    try:
        return read_url_bytes_with_urllib(url, timeout)
    except Exception as exc:
        logger.warning("urllib download failed, falling back to curl: %s", url)
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
    logger.info("Fetching FRED series: %s", series_id)
    url = FRED_CSV_URL.format(series_id=series_id)
    raw = read_url_bytes(url)
    data = pd.read_csv(BytesIO(raw), na_values=["."])
    if "observation_date" not in data.columns or series_id not in data.columns:
        raise ValueError(f"Unexpected FRED CSV format for {series_id}")

    series = data.set_index(pd.to_datetime(data["observation_date"]))[series_id]
    series = pd.to_numeric(series, errors="coerce")
    series = series.loc[pd.Timestamp(start) :]
    series.name = series_id.lower()
    logger.debug(
        "FRED series %s loaded: rows=%d, first=%s, last=%s",
        series_id,
        len(series),
        series.index.min(),
        series.index.max(),
    )
    return series


def fetch_yahoo_history(ticker: str, start: str, end: date | None = None) -> pd.DataFrame:
    logger.info("Fetching Yahoo history: %s", ticker)
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
    out = out.loc[pd.Timestamp(start) :]
    logger.debug("Yahoo history %s loaded: rows=%d, columns=%s", ticker, len(out), list(out.columns))
    return out


def load_optional_csv(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    csv_path = Path(path)
    logger.info("Loading optional CSV: %s", csv_path)
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
    logger.debug("Optional CSV loaded: %s rows=%d columns=%s", csv_path, len(frame), list(frame.columns))
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
    logger.info("Fetching FINRA margin data")
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
    logger.debug("FINRA margin data loaded: rows=%d, first=%s, last=%s", len(out), out.index.min(), out.index.max())
    return out


def load_live_data(
    start: str,
    include_margin: bool = True,
    include_yahoo: bool = True,
    valuation_csv: str | None = None,
    concentration_csv: str | None = None,
    put_call_csv: str | None = None,
) -> pd.DataFrame:
    logger.info("Loading live data from public sources")
    fred_ids = {
        "nasdaq": "NASDAQ100",
        "sp500": "SP500",
        "vix": "VIXCLS",
        "dgs10": "DGS10",
        "m2": "M2SL",
        "gdp": "GDP",
    }
    logger.info("Fetching %d FRED series", len(fred_ids))
    series = {name: fetch_fred_series(series_id, start) for name, series_id in fred_ids.items()}
    frame = pd.concat(series.values(), axis=1, sort=True).sort_index()
    frame.columns = list(series.keys())
    frame = frame.ffill()
    logger.info("FRED data ready: rows=%d, columns=%d", len(frame), len(frame.columns))

    if include_yahoo:
        yahoo_tickers = ("QQQ", "SPY", "ARKK", *MEGA_CAP_TICKERS)
        yahoo_frames = []
        logger.info("Fetching Yahoo data for %d tickers", len(yahoo_tickers))
        for ticker in yahoo_tickers:
            try:
                yahoo_frames.append(fetch_yahoo_history(ticker, start))
            except (
                URLError,
                TimeoutError,
                RuntimeError,
                ValueError,
                OSError,
                json.JSONDecodeError,
            ) as exc:
                logger.warning("Yahoo data skipped for %s: %s", ticker, exc)
        if yahoo_frames:
            yahoo_data = pd.concat(yahoo_frames, axis=1, sort=True).sort_index()
            frame = join_daily(frame, yahoo_data, ffill=True)
            logger.info("Yahoo data joined: rows=%d, columns=%d", len(frame), len(frame.columns))
        else:
            logger.warning("No Yahoo data was loaded")
    else:
        logger.info("Yahoo data skipped by CLI flag")

    if include_margin:
        try:
            margin = fetch_finra_margin(start)
            frame = join_daily(frame, margin, ffill=True)
            logger.info("FINRA margin data joined")
        except (URLError, TimeoutError, RuntimeError, ValueError, StopIteration, OSError) as exc:
            logger.warning("FINRA margin data skipped: %s", exc)
    else:
        logger.info("FINRA margin data skipped by CLI flag")

    for optional_path in (valuation_csv, concentration_csv, put_call_csv):
        optional_data = load_optional_csv(optional_path)
        frame = join_daily(frame, optional_data, ffill=True)

    logger.info("Live data load complete: rows=%d, columns=%d", len(frame), len(frame.columns))
    return frame


def load_offline_sample(start: str) -> pd.DataFrame:
    logger.info("Generating offline sample data from %s to %s", start, date.today())
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
    logger.info("Offline sample ready: rows=%d, columns=%d", len(frame), len(frame.columns))
    return frame
