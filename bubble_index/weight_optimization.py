"""Random search and walk-forward validation for factor group weights."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtesting import BACKTEST_STAGE_REFERENCES, future_max_drawdown, scaled_index_series
from .factors import Factor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeightOptimizationConfig:
    trials: int = 2000
    seed: int = 42
    train_years: int = 10
    validation_years: int = 3
    step_years: int = 1
    future_drawdown_years: int = 3
    min_weight: float = 0.03
    max_weight: float = 0.4
    top_quantile: float = 0.9
    drawdown_threshold: float = -0.25
    min_observations: int = 24
    top_candidates: int = 10


def clean_metric(value: float | int | None, digits: int = 4) -> float | None:
    if value is None or pd.isna(value) or not np.isfinite(float(value)):
        return None
    return round(float(value), digits)


def normalize_weight_values(values: np.ndarray) -> np.ndarray:
    total = float(np.sum(values))
    if total <= 0:
        raise ValueError("Weight values must contain at least one positive number")
    return values / total


def normalize_weight_dict(weights: dict[str, float], keys: list[str]) -> dict[str, float]:
    values = np.array([float(weights[key]) for key in keys], dtype=float)
    values = normalize_weight_values(values)
    return {key: float(value) for key, value in zip(keys, values)}


def validate_weight_bounds(config: WeightOptimizationConfig, factor_count: int) -> None:
    if config.trials < 1:
        raise ValueError("--weight-search-trials must be at least 1")
    if config.min_weight < 0:
        raise ValueError("--weight-min must be non-negative")
    if config.max_weight <= 0:
        raise ValueError("--weight-max must be positive")
    if config.min_weight > config.max_weight:
        raise ValueError("--weight-min cannot be greater than --weight-max")
    if config.min_weight * factor_count > 1:
        raise ValueError("Minimum weight is too high for the number of factors")
    if config.max_weight * factor_count < 1:
        raise ValueError("Maximum weight is too low for the number of factors")
    if not 0 < config.top_quantile < 1:
        raise ValueError("Top quantile must be between 0 and 1")


def generate_weight_candidates(
    factors: list[Factor], config: WeightOptimizationConfig
) -> list[dict[str, float]]:
    keys = [factor.key for factor in factors]
    validate_weight_bounds(config, len(keys))

    baseline = normalize_weight_dict({factor.key: factor.weight for factor in factors}, keys)
    baseline_values = np.array([baseline[key] for key in keys], dtype=float)
    rng = np.random.default_rng(config.seed)
    candidates = [baseline]
    seen = {tuple(round(baseline[key], 5) for key in keys)}
    attempts = 0
    max_attempts = max(config.trials * 80, 5000)

    while len(candidates) < config.trials + 1 and attempts < max_attempts:
        attempts += 1
        if attempts % 2:
            values = rng.dirichlet(np.ones(len(keys)))
        else:
            values = rng.dirichlet(baseline_values * 36 + 1)
        if np.any(values < config.min_weight) or np.any(values > config.max_weight):
            continue
        signature = tuple(round(float(value), 5) for value in values)
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append({key: float(value) for key, value in zip(keys, values)})

    if len(candidates) < config.trials + 1:
        logger.warning(
            "Generated %d/%d requested random candidates within bounds; "
            "consider widening --weight-min/--weight-max",
            len(candidates) - 1,
            config.trials,
        )
    logger.info("Generated %d weight candidates including baseline", len(candidates))
    return candidates


def monthly_future_drawdown_target(prices: pd.Series, years: int) -> pd.Series:
    monthly = pd.DataFrame({"price": prices.dropna()}).resample("ME").last().dropna()
    drawdowns = [
        future_max_drawdown(prices, point_date, years=years, require_full_window=True)
        for point_date in monthly.index
    ]
    return pd.Series(drawdowns, index=monthly.index, name="future_max_drawdown").dropna()


def monthly_score_matrix(
    data: pd.DataFrame,
    factors: list[Factor],
    candidates: list[dict[str, float]],
    chunk_size: int = 1000,
) -> pd.DataFrame:
    available_factors = [factor for factor in factors if factor.score_column in data.columns]
    if not available_factors:
        raise ValueError("No factor score columns are available for weight optimization")

    values = data[[factor.score_column for factor in available_factors]].to_numpy(dtype=float)
    valid = np.isfinite(values)
    safe_values = np.where(valid, values, 0.0)
    valid_float = valid.astype(float)

    pieces = []
    for start in range(0, len(candidates), chunk_size):
        stop = min(start + chunk_size, len(candidates))
        weight_matrix = np.array(
            [
                [candidate[factor.key] for candidate in candidates[start:stop]]
                for factor in available_factors
            ],
            dtype=float,
        )
        weighted_sum = np.einsum("ij,jk->ik", safe_values, weight_matrix)
        active_weight = np.einsum("ij,jk->ik", valid_float, weight_matrix)
        scores = np.full_like(weighted_sum, np.nan, dtype=float)
        np.divide(weighted_sum, active_weight, out=scores, where=active_weight > 0)
        chunk = pd.DataFrame(
            scores,
            index=data.index,
            columns=list(range(start, stop)),
        ).resample("ME").last()
        pieces.append(chunk)

    return pd.concat(pieces, axis=1).sort_index()


def positive_corr(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 3 or np.nanstd(left) <= 0 or np.nanstd(right) <= 0:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if np.isfinite(value) else None


def positive_spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 3:
        return None
    left_rank = pd.Series(left).rank(method="average").to_numpy(dtype=float)
    right_rank = pd.Series(right).rank(method="average").to_numpy(dtype=float)
    return positive_corr(left_rank, right_rank)


def stage_stability_summary(
    dates: pd.DatetimeIndex,
    scores: np.ndarray,
    drawdowns: np.ndarray,
    threshold: float,
) -> tuple[float | None, list[dict[str, Any]]]:
    if len(scores) == 0:
        return None, []

    years = dates.year
    stages = []
    components = []
    for year, label in BACKTEST_STAGE_REFERENCES:
        year_mask = years == year
        if not np.any(year_mask):
            continue
        year_positions = np.flatnonzero(year_mask)
        local_best = year_positions[int(np.nanargmax(scores[year_positions]))]
        score = float(scores[local_best])
        drawdown = float(drawdowns[local_best])
        percentile = float(np.mean(scores <= score))
        drawdown_hit = 1.0 if drawdown <= threshold else 0.0
        score_component = min(max(score / 85, 0), 1)
        component = 0.55 * score_component + 0.35 * percentile + 0.10 * drawdown_hit
        components.append(component)
        stages.append(
            {
                "year": int(year),
                "label": label,
                "peak_date": dates[local_best].strftime("%Y-%m-%d"),
                "score": clean_metric(score, 2),
                "score_percentile_in_window": clean_metric(percentile, 4),
                "future_max_drawdown": clean_metric(drawdown, 4),
                "hit_25pct_drawdown": bool(drawdown <= threshold),
            }
        )

    if not components:
        return None, stages
    return float(np.mean(components)), stages


def clipped_component(value: float | None, scale: float) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(np.clip(float(value) / scale, 0, 1))


def weighted_objective(components: dict[str, tuple[float, float | None]]) -> float | None:
    weighted_sum = 0.0
    active_weight = 0.0
    for weight, value in components.values():
        if value is None or pd.isna(value):
            continue
        weighted_sum += weight * float(np.clip(value, 0, 1))
        active_weight += weight
    if active_weight <= 0:
        return None
    return weighted_sum / active_weight


def evaluate_score_vector(
    dates: pd.DatetimeIndex,
    score_values: np.ndarray,
    drawdown_values: np.ndarray,
    config: WeightOptimizationConfig,
) -> dict[str, Any]:
    valid = np.isfinite(score_values) & np.isfinite(drawdown_values)
    dates = dates[valid]
    scores = score_values[valid].astype(float)
    drawdowns = drawdown_values[valid].astype(float)
    if len(scores) < config.min_observations:
        return {
            "objective": None,
            "observations": int(len(scores)),
            "stage_peaks": [],
        }

    severity = -drawdowns
    pearson = positive_corr(scores, severity)
    spearman = positive_spearman(scores, severity)
    top_threshold = float(np.nanquantile(scores, config.top_quantile))
    bottom_threshold = float(np.nanquantile(scores, 1 - config.top_quantile))
    top_mask = scores >= top_threshold
    bottom_mask = scores <= bottom_threshold
    top_drawdowns = drawdowns[top_mask]
    bottom_drawdowns = drawdowns[bottom_mask]
    top_severity = severity[top_mask]
    bottom_severity = severity[bottom_mask]
    all_avg_severity = float(np.nanmean(severity))
    top_avg_severity = float(np.nanmean(top_severity)) if len(top_severity) else np.nan
    bottom_avg_severity = (
        float(np.nanmean(bottom_severity)) if len(bottom_severity) else np.nan
    )
    severity_premium = top_avg_severity - all_avg_severity
    top_bottom_spread = top_avg_severity - bottom_avg_severity
    hit_rate = (
        float(np.mean(top_drawdowns <= config.drawdown_threshold))
        if len(top_drawdowns)
        else np.nan
    )
    stage_stability, stage_peaks = stage_stability_summary(
        dates,
        scores,
        drawdowns,
        config.drawdown_threshold,
    )

    objective = weighted_objective(
        {
            "pearson": (0.25, max(pearson or 0, 0)),
            "spearman": (0.2, max(spearman or 0, 0)),
            "severity_premium": (0.18, clipped_component(severity_premium, 0.15)),
            "top_bottom_spread": (0.12, clipped_component(top_bottom_spread, 0.2)),
            "top_hit_rate": (0.1, hit_rate),
            "stage_stability": (0.15, stage_stability),
        }
    )

    return {
        "objective": clean_metric(objective, 6),
        "observations": int(len(scores)),
        "score_to_drawdown_severity_corr": clean_metric(pearson, 4),
        "score_to_drawdown_severity_spearman": clean_metric(spearman, 4),
        "top_decile_score_threshold": clean_metric(top_threshold, 2),
        "top_decile_count": int(np.sum(top_mask)),
        "top_decile_avg_future_max_drawdown": clean_metric(
            float(np.nanmean(top_drawdowns)) if len(top_drawdowns) else None,
            4,
        ),
        "top_decile_hit_rate_25pct_drawdown": clean_metric(hit_rate, 4),
        "avg_future_max_drawdown_all_months": clean_metric(float(np.nanmean(drawdowns)), 4),
        "severity_premium_vs_all_months": clean_metric(severity_premium, 4),
        "severity_spread_vs_bottom_decile": clean_metric(top_bottom_spread, 4),
        "stage_stability": clean_metric(stage_stability, 4),
        "stage_count": int(len(stage_peaks)),
        "stage_peaks": stage_peaks,
    }


def build_walk_forward_folds(
    index: pd.DatetimeIndex,
    config: WeightOptimizationConfig,
) -> list[dict[str, pd.Timestamp]]:
    if index.empty:
        return []
    folds = []
    train_start = index.min()
    final_date = index.max()
    while train_start + pd.DateOffset(
        years=config.train_years + config.validation_years
    ) <= final_date:
        train_end = train_start + pd.DateOffset(years=config.train_years)
        validation_end = train_end + pd.DateOffset(years=config.validation_years)
        train_mask = (index >= train_start) & (index < train_end)
        validation_mask = (index >= train_end) & (index < validation_end)
        if train_mask.sum() >= config.min_observations and validation_mask.sum() >= config.min_observations:
            folds.append(
                {
                    "train_start": train_start,
                    "train_end": train_end,
                    "validation_start": train_end,
                    "validation_end": validation_end,
                }
            )
        train_start = train_start + pd.DateOffset(years=config.step_years)
    return folds


def evaluate_candidate_index(
    candidate_idx: int,
    scores: np.ndarray,
    drawdowns: np.ndarray,
    dates: pd.DatetimeIndex,
    mask: np.ndarray,
    config: WeightOptimizationConfig,
) -> dict[str, Any]:
    return evaluate_score_vector(
        dates[mask],
        scores[mask, candidate_idx],
        drawdowns[mask],
        config,
    )


def best_candidate_for_mask(
    scores: np.ndarray,
    drawdowns: np.ndarray,
    dates: pd.DatetimeIndex,
    mask: np.ndarray,
    config: WeightOptimizationConfig,
) -> tuple[int, dict[str, Any]]:
    best_idx = 0
    best_metrics = evaluate_candidate_index(
        0,
        scores,
        drawdowns,
        dates,
        mask,
        config,
    )
    best_score = -np.inf
    baseline_objective = best_metrics.get("objective")
    if baseline_objective is not None:
        best_score = float(baseline_objective)
    for candidate_idx in range(1, scores.shape[1]):
        metrics = evaluate_candidate_index(
            candidate_idx,
            scores,
            drawdowns,
            dates,
            mask,
            config,
        )
        objective = metrics.get("objective")
        objective_value = float(objective) if objective is not None else -np.inf
        if objective_value > best_score:
            best_idx = candidate_idx
            best_score = objective_value
            best_metrics = metrics
    return best_idx, best_metrics


def average_weights(
    selected_weights: list[dict[str, float]],
    keys: list[str],
    selection_scores: list[float],
) -> dict[str, float]:
    if not selected_weights:
        raise ValueError("Cannot average an empty list of selected weights")
    weights = np.array([[item[key] for key in keys] for item in selected_weights], dtype=float)
    scores = np.array(selection_scores, dtype=float)
    scores = np.where(np.isfinite(scores) & (scores > 0), scores, 0)
    if float(scores.sum()) <= 0:
        averaged = weights.mean(axis=0)
    else:
        averaged = np.average(weights, axis=0, weights=scores)
    averaged = normalize_weight_values(averaged)
    return {key: float(value) for key, value in zip(keys, averaged)}


def candidate_result_row(
    candidate_idx: int,
    weights: dict[str, float],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": int(candidate_idx),
        "objective": metrics.get("objective"),
        "weights": {key: clean_metric(value, 6) for key, value in weights.items()},
        "metrics": metrics,
    }


def optimize_factor_weights(
    data: pd.DataFrame,
    factors: list[Factor],
    config: WeightOptimizationConfig,
) -> dict[str, Any]:
    logger.info(
        "Starting random weight search: trials=%d, seed=%d, train=%dy, validation=%dy",
        config.trials,
        config.seed,
        config.train_years,
        config.validation_years,
    )
    keys = [factor.key for factor in factors]
    candidates = generate_weight_candidates(factors, config)
    prices = scaled_index_series(data, "nasdaq", "qqq_close").dropna()
    target = monthly_future_drawdown_target(prices, config.future_drawdown_years)
    if len(target) < config.min_observations:
        raise ValueError("Not enough monthly observations with future drawdown targets")

    monthly_scores = monthly_score_matrix(data, factors, candidates).reindex(target.index)
    dates = target.index
    drawdowns = target.to_numpy(dtype=float)
    scores = monthly_scores.to_numpy(dtype=float)
    folds = build_walk_forward_folds(dates, config)
    if not folds:
        raise ValueError("Not enough monthly history to build walk-forward folds")

    fold_results = []
    selected_weights = []
    selection_scores = []
    for fold_number, fold in enumerate(folds, start=1):
        train_mask = (dates >= fold["train_start"]) & (dates < fold["train_end"])
        validation_mask = (dates >= fold["validation_start"]) & (
            dates < fold["validation_end"]
        )
        best_idx, train_metrics = best_candidate_for_mask(
            scores,
            drawdowns,
            dates,
            train_mask,
            config,
        )
        validation_metrics = evaluate_candidate_index(
            best_idx,
            scores,
            drawdowns,
            dates,
            validation_mask,
            config,
        )
        selected_weights.append(candidates[best_idx])
        selection_score = validation_metrics.get("objective")
        selection_scores.append(float(selection_score) if selection_score is not None else 0.0)
        fold_results.append(
            {
                "fold": fold_number,
                "train_start": fold["train_start"].strftime("%Y-%m-%d"),
                "train_end": fold["train_end"].strftime("%Y-%m-%d"),
                "validation_start": fold["validation_start"].strftime("%Y-%m-%d"),
                "validation_end": fold["validation_end"].strftime("%Y-%m-%d"),
                "selected_candidate_id": int(best_idx),
                "selected_weights": {
                    key: clean_metric(value, 6) for key, value in candidates[best_idx].items()
                },
                "train_metrics": train_metrics,
                "validation_metrics": validation_metrics,
            }
        )
        logger.info(
            "Walk-forward fold %d/%d: selected candidate=%d, train_objective=%s, validation_objective=%s",
            fold_number,
            len(folds),
            best_idx,
            train_metrics.get("objective"),
            validation_metrics.get("objective"),
        )

    recommended_weights = average_weights(selected_weights, keys, selection_scores)
    recommended_scores = monthly_score_matrix(data, factors, [recommended_weights]).reindex(
        target.index
    )
    recommended_full_metrics = evaluate_score_vector(
        dates,
        recommended_scores.iloc[:, 0].to_numpy(dtype=float),
        drawdowns,
        config,
    )

    baseline_metrics = evaluate_candidate_index(
        0,
        scores,
        drawdowns,
        dates,
        np.ones(len(dates), dtype=bool),
        config,
    )

    full_candidate_rows = []
    for candidate_idx, weights in enumerate(candidates):
        metrics = evaluate_candidate_index(
            candidate_idx,
            scores,
            drawdowns,
            dates,
            np.ones(len(dates), dtype=bool),
            config,
        )
        full_candidate_rows.append(candidate_result_row(candidate_idx, weights, metrics))
    full_candidate_rows.sort(
        key=lambda item: float(item["objective"]) if item["objective"] is not None else -np.inf,
        reverse=True,
    )

    validation_objectives = [
        item["validation_metrics"].get("objective")
        for item in fold_results
        if item["validation_metrics"].get("objective") is not None
    ]
    train_objectives = [
        item["train_metrics"].get("objective")
        for item in fold_results
        if item["train_metrics"].get("objective") is not None
    ]
    summary = {
        "fold_count": int(len(folds)),
        "candidate_count": int(len(candidates)),
        "avg_selected_train_objective": clean_metric(
            float(np.mean(train_objectives)) if train_objectives else None,
            6,
        ),
        "avg_selected_validation_objective": clean_metric(
            float(np.mean(validation_objectives)) if validation_objectives else None,
            6,
        ),
        "median_selected_validation_objective": clean_metric(
            float(np.median(validation_objectives)) if validation_objectives else None,
            6,
        ),
    }

    logger.info("Weight optimization complete: recommended=%s", recommended_weights)
    return {
        "method": "random_search_walk_forward",
        "objective_description": (
            "Blend of score/future drawdown severity correlation, rank correlation, "
            "top-decile drawdown severity premium, top-decile 25% drawdown hit rate, "
            "and classic bubble stage stability."
        ),
        "config": {
            "trials": config.trials,
            "seed": config.seed,
            "train_years": config.train_years,
            "validation_years": config.validation_years,
            "step_years": config.step_years,
            "future_drawdown_years": config.future_drawdown_years,
            "min_weight": config.min_weight,
            "max_weight": config.max_weight,
            "top_quantile": config.top_quantile,
            "drawdown_threshold": config.drawdown_threshold,
            "min_observations": config.min_observations,
        },
        "summary": summary,
        "baseline": {
            "weights": {
                key: clean_metric(value, 6)
                for key, value in normalize_weight_dict(
                    {factor.key: factor.weight for factor in factors},
                    keys,
                ).items()
            },
            "metrics": baseline_metrics,
        },
        "recommended": {
            "weights": {key: clean_metric(value, 6) for key, value in recommended_weights.items()},
            "metrics": recommended_full_metrics,
        },
        "top_full_history_candidates": full_candidate_rows[: config.top_candidates],
        "walk_forward_folds": fold_results,
    }


def write_weight_optimization_outputs(
    result: dict[str, Any],
    out_dir: Path,
) -> dict[str, Path]:
    logger.info("Writing weight optimization outputs to %s", out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "weight_optimization.json"
    weights_path = out_dir / "optimized_factor_weights.json"
    top_candidates_path = out_dir / "weight_optimization_top_candidates.csv"

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    recommended = result["recommended"]["weights"]
    weights_payload = {
        "weights": recommended,
        "metadata": {
            "method": result["method"],
            "seed": result["config"]["seed"],
            "trials": result["config"]["trials"],
            "future_drawdown_years": result["config"]["future_drawdown_years"],
            "avg_selected_validation_objective": result["summary"][
                "avg_selected_validation_objective"
            ],
        },
    }
    weights_path.write_text(
        json.dumps(weights_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows = []
    for item in result["top_full_history_candidates"]:
        row = {
            "candidate_id": item["candidate_id"],
            "objective": item["objective"],
        }
        row.update(item["weights"])
        metrics = item["metrics"]
        row.update(
            {
                "corr": metrics.get("score_to_drawdown_severity_corr"),
                "spearman": metrics.get("score_to_drawdown_severity_spearman"),
                "top_decile_avg_future_max_drawdown": metrics.get(
                    "top_decile_avg_future_max_drawdown"
                ),
                "top_decile_hit_rate_25pct_drawdown": metrics.get(
                    "top_decile_hit_rate_25pct_drawdown"
                ),
                "stage_stability": metrics.get("stage_stability"),
            }
        )
        rows.append(row)
    pd.DataFrame(rows).to_csv(top_candidates_path, index=False)

    logger.info("Wrote optimization JSON: %s", result_path)
    logger.info("Wrote optimized weights JSON: %s", weights_path)
    logger.info("Wrote top candidates CSV: %s", top_candidates_path)
    return {
        "weight_optimization": result_path,
        "optimized_weights": weights_path,
        "top_candidates": top_candidates_path,
    }
