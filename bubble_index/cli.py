"""Command-line interface for the Nasdaq bubble index."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .data_sources import load_live_data, load_offline_sample
from .factors import default_factor_weights_path, load_factors
from .logging_config import configure_logging, default_log_config_path
from .reporting import write_outputs
from .scoring import compute_scores
from .weight_optimization import (
    WeightOptimizationConfig,
    optimize_factor_weights,
    write_weight_optimization_outputs,
)

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate a free-data Nasdaq bubble index.")
    parser.add_argument("--start", default="1986-01-01", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--out", default="output", help="Output directory.")
    parser.add_argument(
        "--window-years",
        type=int,
        default=20,
        help="Rolling percentile window in trading years.",
    )
    parser.add_argument(
        "--factor-weights",
        default=str(default_factor_weights_path()),
        help="Path to factor weights JSON config.",
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
    parser.add_argument(
        "--log-config",
        default=str(default_log_config_path()),
        help="Path to logging config file.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Override the configured logging level.",
    )
    parser.add_argument(
        "--optimize-weights",
        action="store_true",
        help="Run random search plus walk-forward validation for the 6 group weights.",
    )
    parser.add_argument(
        "--weight-search-trials",
        type=int,
        default=2000,
        help="Number of random weight candidates to evaluate when optimizing.",
    )
    parser.add_argument(
        "--weight-search-seed",
        type=int,
        default=42,
        help="Random seed for weight optimization.",
    )
    parser.add_argument(
        "--wf-train-years",
        type=int,
        default=10,
        help="Walk-forward training window length in years.",
    )
    parser.add_argument(
        "--wf-validation-years",
        type=int,
        default=3,
        help="Walk-forward validation window length in years.",
    )
    parser.add_argument(
        "--wf-step-years",
        type=int,
        default=1,
        help="Walk-forward window step length in years.",
    )
    parser.add_argument(
        "--weight-min",
        type=float,
        default=0.03,
        help="Minimum allowed weight for each factor group during optimization.",
    )
    parser.add_argument(
        "--weight-max",
        type=float,
        default=0.40,
        help="Maximum allowed weight for each factor group during optimization.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_config, args.log_level)

    logger.info("Starting Nasdaq bubble index run")
    logger.info(
        "Start date=%s, output=%s, window_years=%s",
        args.start,
        args.out,
        args.window_years,
    )
    factors = load_factors(args.factor_weights)
    logger.info("Loaded %d factor weights from %s", len(factors), args.factor_weights)

    if args.offline_sample:
        logger.info("Loading deterministic offline sample data")
        raw = load_offline_sample(args.start)
    else:
        logger.info("Loading live public data")
        raw = load_live_data(
            args.start,
            include_margin=not args.no_finra,
            include_yahoo=not args.no_yahoo,
            valuation_csv=args.valuation_csv,
            concentration_csv=args.concentration_csv,
            put_call_csv=args.put_call_csv,
        )
    logger.info("Raw data ready: rows=%d, columns=%d", len(raw), len(raw.columns))

    scored = compute_scores(raw, factors=factors, window_years=args.window_years)
    paths = write_outputs(scored, Path(args.out), factors=factors)
    summary = json.loads(paths["latest"].read_text(encoding="utf-8"))

    optimization_paths = {}
    if args.optimize_weights:
        optimization_config = WeightOptimizationConfig(
            trials=args.weight_search_trials,
            seed=args.weight_search_seed,
            train_years=args.wf_train_years,
            validation_years=args.wf_validation_years,
            step_years=args.wf_step_years,
            min_weight=args.weight_min,
            max_weight=args.weight_max,
        )
        optimization = optimize_factor_weights(scored, factors, optimization_config)
        optimization_paths = write_weight_optimization_outputs(optimization, Path(args.out))
        recommended_weights = optimization["recommended"]["weights"]
        logger.info("Recommended optimized weights: %s", recommended_weights)

    logger.info(
        "Run complete: score=%s, label=%s, data_date=%s",
        summary["bubble_score"],
        summary["risk_label"],
        summary["date"],
    )

    print(f"Nasdaq bubble score: {summary['bubble_score']} ({summary['risk_label']})")
    print(f"Data date: {summary['date']}")
    for name, path in paths.items():
        print(f"{name}: {path}")
    for name, path in optimization_paths.items():
        print(f"{name}: {path}")
