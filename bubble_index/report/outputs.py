"""File output writer for generated reports."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from ..backtesting import build_backtest_summary
from ..factors import Factor
from .assets import copy_static_assets
from .html import render_html_report
from .summary import build_summary, latest_complete_row, previous_complete_row

logger = logging.getLogger(__name__)


def write_outputs(data: pd.DataFrame, out_dir: Path, factors: list[Factor]) -> dict[str, Path]:
    logger.info("Writing outputs to %s", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_static_assets(out_dir)
    latest = latest_complete_row(data)
    previous = previous_complete_row(data)
    summary = build_summary(latest, factors, previous)
    logger.info(
        "Latest complete score: date=%s, score=%s, label=%s",
        summary["date"],
        summary["bubble_score"],
        summary["risk_label"],
    )

    history_path = out_dir / "bubble_history.csv"
    latest_path = out_dir / "latest.json"
    backtest_path = out_dir / "backtest_summary.json"
    report_path = out_dir / "report.html"

    data.to_csv(history_path, index_label="date")
    logger.info("Wrote history CSV: %s", history_path)
    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote latest JSON: %s", latest_path)
    backtest_summary = build_backtest_summary(data)
    backtest_path.write_text(
        json.dumps(backtest_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Wrote backtest JSON: %s", backtest_path)
    report_path.write_text(render_html_report(data, summary, backtest_summary), encoding="utf-8")
    logger.info("Wrote HTML report: %s", report_path)

    return {
        "history": history_path,
        "latest": latest_path,
        "backtest": backtest_path,
        "report": report_path,
    }
