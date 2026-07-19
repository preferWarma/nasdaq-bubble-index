"""Reporting package public exports."""

from .assets import copy_static_assets, project_root, static_assets_dir
from .charts import (
    interactive_chart_bootstrap,
    interactive_chart_payload,
    render_interactive_charts,
    render_stage_chips,
    svg_index_chart,
    svg_line_chart,
)
from .constants import BUBBLE_STAGE_NOTES, BUBBLE_STAGE_YEARS, HISTORICAL_REFERENCE_STAGES
from .formatting import (
    chart_number,
    format_axis_number,
    format_decimal,
    format_plain_percent,
    format_score,
    format_signed_percent,
    script_json,
)
from .gauge import svg_score_gauge
from .html import render_html_report
from .outputs import write_outputs
from .sections import (
    historical_reference_cards,
    previous_score_caption,
    render_backtest_section,
    render_reference_section,
)
from .summary import (
    build_summary,
    factor_reason,
    latest_complete_row,
    previous_complete_row,
    risk_label,
)
from .time_series import (
    find_stage_points,
    future_max_drawdown,
    nearest_index_position,
    scaled_index_series,
    trim_frame_to_range,
    trim_to_recent_years,
    x_axis_ticks,
)

__all__ = [
    "BUBBLE_STAGE_NOTES",
    "BUBBLE_STAGE_YEARS",
    "HISTORICAL_REFERENCE_STAGES",
    "build_summary",
    "chart_number",
    "copy_static_assets",
    "factor_reason",
    "find_stage_points",
    "format_axis_number",
    "format_decimal",
    "format_plain_percent",
    "format_score",
    "format_signed_percent",
    "future_max_drawdown",
    "historical_reference_cards",
    "interactive_chart_bootstrap",
    "interactive_chart_payload",
    "latest_complete_row",
    "nearest_index_position",
    "previous_score_caption",
    "previous_complete_row",
    "project_root",
    "render_backtest_section",
    "render_html_report",
    "render_interactive_charts",
    "render_reference_section",
    "render_stage_chips",
    "risk_label",
    "scaled_index_series",
    "script_json",
    "static_assets_dir",
    "svg_index_chart",
    "svg_line_chart",
    "svg_score_gauge",
    "trim_frame_to_range",
    "trim_to_recent_years",
    "write_outputs",
    "x_axis_ticks",
]
