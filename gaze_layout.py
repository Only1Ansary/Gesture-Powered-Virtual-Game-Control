"""
gaze_layout.py
--------------
Converts gaze samples into conservative adaptive button anchors.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any


DEFAULT_LAYOUT: dict[str, Any] = {
    "version": 1,
    "adaptive": False,
    "anchors": {
        "back": {"x": 0.30, "y": 0.80},
        "launch": {"x": 0.56, "y": 0.80},
        "game_icon": {"x": 0.84, "y": 0.80},
    },
    "hot_zones": [],
}


def compute_layout(
    samples: list[dict[str, float]],
    *,
    grid_columns: int,
    grid_rows: int,
    min_samples: int,
    margin_ratio: float,
    min_distance: float,
) -> dict[str, Any] | None:
    valid = [
        {"x": float(s["x"]), "y": float(s["y"]), "t": float(s.get("t", 0.0))}
        for s in samples
        if _is_valid_point(s)
    ]
    if len(valid) < min_samples:
        return None

    hot_zones = _rank_hot_zones(valid, grid_columns, grid_rows)
    if not hot_zones:
        return None

    launch_anchor = _safe_point(hot_zones[0], margin_ratio)
    anchors = {
        "launch": launch_anchor,
        "back": _choose_distinct_point(hot_zones[1:], hot_zones[0], margin_ratio, min_distance),
        "game_icon": _icon_anchor_away_from(launch_anchor),
    }
    if anchors["back"] is None:
        anchors["back"] = _back_anchor_away_from(launch_anchor)

    return {
        "version": 1,
        "adaptive": True,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sample_count": len(valid),
        "grid": {"columns": grid_columns, "rows": grid_rows},
        "anchors": anchors,
        "hot_zones": hot_zones[:8],
    }


def _rank_hot_zones(
    samples: list[dict[str, float]],
    grid_columns: int,
    grid_rows: int,
) -> list[dict[str, float]]:
    cols = max(1, int(grid_columns))
    rows = max(1, int(grid_rows))
    counts: dict[tuple[int, int], int] = {}

    for sample in samples:
        col = min(cols - 1, max(0, int(sample["x"] * cols)))
        row = min(rows - 1, max(0, int(sample["y"] * rows)))
        counts[(col, row)] = counts.get((col, row), 0) + 1

    total = max(1, len(samples))
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [
        {
            "x": (col + 0.5) / cols,
            "y": (row + 0.5) / rows,
            "count": count,
            "weight": count / total,
        }
        for (col, row), count in ranked
    ]


def _choose_distinct_point(
    candidates: list[dict[str, float]],
    existing: dict[str, float],
    margin_ratio: float,
    min_distance: float,
) -> dict[str, float] | None:
    for candidate in candidates:
        if _distance(candidate, existing) >= min_distance:
            return _safe_point(candidate, margin_ratio)
    return None


def _icon_anchor_away_from(launch_anchor: dict[str, float]) -> dict[str, float]:
    return {"x": 0.84 if float(launch_anchor["x"]) < 0.58 else 0.16, "y": 0.80}


def _back_anchor_away_from(launch_anchor: dict[str, float]) -> dict[str, float]:
    return {"x": 0.24 if float(launch_anchor["x"]) > 0.50 else 0.76, "y": 0.80}


def _safe_point(point: dict[str, float], margin_ratio: float) -> dict[str, float]:
    margin = max(0.02, min(0.25, float(margin_ratio)))
    x = max(margin, min(1.0 - margin, float(point["x"])))
    y = max(0.18, min(1.0 - margin, float(point["y"])))
    return {"x": x, "y": y}


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def _is_valid_point(sample: dict[str, float]) -> bool:
    try:
        x = float(sample["x"])
        y = float(sample["y"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
