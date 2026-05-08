"""
gaze_store.py
-------------
Per-profile gaze persistence, heatmap generation, and layout loading.
"""

from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any

from config import BASE_DIR, GAZE_MIRROR_HORIZONTAL
from gaze_heatmap import generate_heatmap
from gaze_layout import DEFAULT_LAYOUT, compute_layout


class GazeProfileStore:
    def __init__(self, data_dir: str):
        root = Path(data_dir)
        if not root.is_absolute():
            root = Path(BASE_DIR) / root
        self.root = root

    def load_layout(self, user_id: int) -> dict[str, Any]:
        path = self._user_dir(user_id) / "layout.json"
        if not path.is_file():
            return DEFAULT_LAYOUT
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and isinstance(data.get("anchors"), dict):
                return data
        except Exception as exc:
            print(f"[GazeStore] Could not load layout for user {user_id}: {exc}")
        return DEFAULT_LAYOUT

    def finalize_session(
        self,
        *,
        user_id: int,
        started_at: float | None,
        ended_at: float,
        samples: list[dict[str, float]],
        screen_width: int,
        screen_height: int,
        camera_index: int,
        min_samples: int,
        grid_columns: int,
        grid_rows: int,
        margin_ratio: float,
        min_distance: float,
        background_image_path: str | None = None,
    ) -> dict[str, str | int | bool]:
        user_dir = self._user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        self._archive_previous(user_dir)

        csv_path = user_dir / "last_session.csv"
        json_path = user_dir / "last_session.json"
        heatmap_path = user_dir / "heatmap.png"
        layout_path = user_dir / "layout.json"

        self._write_csv(csv_path, samples)
        self._write_json(
            json_path,
            user_id=user_id,
            started_at=started_at,
            ended_at=ended_at,
            samples=samples,
            screen_width=screen_width,
            screen_height=screen_height,
            camera_index=camera_index,
        )

        heatmap_created = False
        if len(samples) >= 2:
            heatmap_created = generate_heatmap(
                csv_path,
                heatmap_path,
                screen_width=screen_width,
                screen_height=screen_height,
                background_image_path=background_image_path,
            )

        layout = compute_layout(
            samples,
            grid_columns=grid_columns,
            grid_rows=grid_rows,
            min_samples=min_samples,
            margin_ratio=margin_ratio,
            min_distance=min_distance,
        )
        layout_created = layout is not None
        if layout is not None:
            if GAZE_MIRROR_HORIZONTAL:
                layout["mirror_horizontal_calibration"] = True
            self._write_dict(layout_path, layout)

        return {
            "sample_count": len(samples),
            "heatmap_created": heatmap_created,
            "layout_created": layout_created,
            "user_dir": str(user_dir),
        }

    def _user_dir(self, user_id: int) -> Path:
        return self.root / f"user_{user_id}"

    def _archive_previous(self, user_dir: Path) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        history = user_dir / "history"
        history.mkdir(parents=True, exist_ok=True)
        for name in ("last_session.csv", "last_session.json", "heatmap.png"):
            src = user_dir / name
            if src.is_file():
                suffix = src.suffix
                stem = "heatmap" if name == "heatmap.png" else "session"
                shutil.copy2(src, history / f"{timestamp}_{stem}{suffix}")

    def _write_csv(self, path: Path, samples: list[dict[str, float]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["x", "y", "t"])
            writer.writeheader()
            writer.writerows(samples)

    def _write_json(
        self,
        path: Path,
        *,
        user_id: int,
        started_at: float | None,
        ended_at: float,
        samples: list[dict[str, float]],
        screen_width: int,
        screen_height: int,
        camera_index: int,
    ) -> None:
        payload = {
            "user_id": user_id,
            "camera_index": camera_index,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "started_at": _iso_from_timestamp(started_at),
            "ended_at": _iso_from_timestamp(ended_at),
            "sample_count": len(samples),
            "samples": samples,
        }
        self._write_dict(path, payload)

    def _write_dict(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_path, path)


def _iso_from_timestamp(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value).isoformat(timespec="seconds")
