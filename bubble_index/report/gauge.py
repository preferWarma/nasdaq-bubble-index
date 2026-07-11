"""SVG score gauge rendering."""

from __future__ import annotations

import html

import numpy as np

from .formatting import format_score


def gauge_angle(score: float) -> float:
    clamped = float(np.clip(score, 0, 100))
    return 210 - clamped / 100 * 240


def point_from_angle(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    radians = np.deg2rad(angle)
    return cx + radius * float(np.cos(radians)), cy - radius * float(np.sin(radians))


def gauge_point(cx: float, cy: float, radius: float, score: float) -> tuple[float, float]:
    return point_from_angle(cx, cy, radius, gauge_angle(score))


def gauge_arc_points(cx: float, cy: float, radius: float, start: float, end: float) -> str:
    scores = np.linspace(start, end, 34)
    return " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (gauge_point(cx, cy, radius, score) for score in scores)
    )


def svg_score_gauge(score: float, color: str, width: int = 470, height: int = 330) -> str:
    cx, cy = 235, 220
    arc_radius = 142
    needle_x, needle_y = gauge_point(cx, cy, 118, score)
    score_text = format_score(score)

    bands = [
        (0.7, 39.3, "#18b981"),
        (40.7, 59.3, "#14b8a6"),
        (60.7, 79.3, "#f59e0b"),
        (80.7, 89.3, "#dc2626"),
        (90.7, 99.3, "#b91c1c"),
    ]
    band_markup = []
    for start, end, band_color in bands:
        band_markup.append(
            f'<polyline points="{gauge_arc_points(cx, cy, arc_radius, start, end)}" '
            f'fill="none" stroke="{band_color}" stroke-width="30" stroke-linecap="butt" />'
        )

    ticks = []
    for tick in range(0, 101, 2):
        inner_radius = 102 if tick % 10 == 0 else 112
        outer_radius = 124
        x1, y1 = gauge_point(cx, cy, inner_radius, tick)
        x2, y2 = gauge_point(cx, cy, outer_radius, tick)
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#94a3b8" stroke-width="{1.8 if tick % 10 == 0 else 0.9}" />'
        )

    labels = []
    for tick in (0, 20, 40, 60, 80, 90, 100):
        x, y = gauge_point(cx, cy, 181, tick)
        label_color = "#b91c1c" if tick >= 90 else "#111827"
        labels.append(
            f'<text x="{x:.1f}" y="{y + 7:.1f}" text-anchor="middle" '
            f'font-size="19" font-weight="800" fill="{label_color}">{tick}</text>'
        )

    return f"""
<svg class="score-gauge" viewBox="0 0 {width} {height}" role="img" aria-label="Bubble score gauge">
  <rect width="{width}" height="{height}" fill="white" />
  {''.join(band_markup)}
  <circle cx="{cx}" cy="{cy}" r="115" fill="white" />
  {''.join(ticks)}
  {''.join(labels)}
  <line x1="{cx}" y1="{cy}" x2="{needle_x:.1f}" y2="{needle_y:.1f}"
    stroke="{html.escape(color)}" stroke-width="9" stroke-linecap="round" />
  <circle cx="{cx}" cy="{cy}" r="23" fill="white" stroke="#111827" stroke-width="6" />
  <circle cx="{cx}" cy="{cy}" r="13" fill="#111827" />
  <text x="{cx}" y="284" text-anchor="middle" font-size="44" font-weight="800" fill="{html.escape(color)}">{score_text}</text>
  <text x="{cx}" y="313" text-anchor="middle" font-size="20" font-weight="800" fill="#64748b">分</text>
</svg>
"""
