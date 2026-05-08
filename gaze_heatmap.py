"""
gaze_heatmap.py
---------------
Reusable heatmap generation for saved gaze CSV data.
"""

from __future__ import annotations

import csv
from pathlib import Path


def generate_heatmap(
    csv_path: str | Path,
    output_path: str | Path,
    *,
    screen_width: int,
    screen_height: int,
    background_image_path: str | None = None,
) -> bool:
    """Generate a PNG heatmap from normalized x,y gaze samples."""
    rows = _read_points(csv_path)
    if len(rows) < 2:
        return False

    try:
        import cv2
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import seaborn as sns
    except Exception as exc:
        print(f"[GazeHeatmap] Missing heatmap dependencies: {exc}")
        return False

    width = max(1, int(screen_width))
    height = max(1, int(screen_height))
    xs = [point[0] * width for point in rows]
    ys = [point[1] * height for point in rows]

    if background_image_path:
        img = cv2.imread(background_image_path)
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            height, width = img.shape[:2]
        else:
            img = _blank_image(height, width, np)
    else:
        img = _blank_image(height, width, np)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(img, extent=[0, width, height, 0], origin="upper")
    try:
        sns.kdeplot(x=xs, y=ys, fill=True, cmap="RdBu_r", cbar=False, ax=ax, alpha=0.45)
    except Exception:
        ax.scatter(xs, ys, s=20, c="red", alpha=0.35)

    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return True


def _read_points(csv_path: str | Path) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    path = Path(csv_path)
    if not path.is_file():
        return points

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                x = max(0.0, min(1.0, float(row["x"])))
                y = max(0.0, min(1.0, float(row["y"])))
            except (KeyError, TypeError, ValueError):
                continue
            points.append((x, y))
    return points


def _blank_image(height: int, width: int, np):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = (12, 12, 24)
    return img
