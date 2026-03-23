"""
user_store.py
-------------
Runtime user list persisted to admin_users.json.

Defaults come from character_map.USERS; the JSON stores only marker id + display name.
Theme assets (gif, avatar, colours) are derived by cycling the four built-in presets.
"""

from __future__ import annotations

import copy
import json
import os
import random
from typing import Any

from character_map import USERS as DEFAULT_USERS

_STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_users.json")

# Random display names for “Add user”
_NAME_PARTS = (
    "Nova",
    "River",
    "Sky",
    "Echo",
    "Morgan",
    "Quinn",
    "Phoenix",
    "Sage",
    "Rowan",
    "Indigo",
    "Ash",
    "Jules",
    "Reese",
    "Blair",
    "Eden",
)


def _preset_templates() -> list[dict[str, Any]]:
    order = sorted(DEFAULT_USERS.keys())
    return [copy.deepcopy(DEFAULT_USERS[i]) for i in order]


def build_user_dict(marker_id: int, name: str) -> dict[str, Any]:
    """Build a full user entry: same asset paths as presets, rotated by id."""
    templates = _preset_templates()
    base = copy.deepcopy(templates[marker_id % len(templates)])
    base["name"] = name
    return base


def _default_snapshot() -> list[dict[str, Any]]:
    return [{"id": int(k), "name": v["name"]} for k, v in sorted(DEFAULT_USERS.items())]


def load_users() -> dict[int, dict[str, Any]]:
    """Load users from disk or factory defaults."""
    if not os.path.isfile(_STORE_PATH):
        entries = _default_snapshot()
    else:
        try:
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("users")
            if not isinstance(entries, list) or not entries:
                entries = _default_snapshot()
        except Exception as exc:
            print(f"[user_store] Could not read admin_users.json: {exc}")
            entries = _default_snapshot()

    out: dict[int, dict[str, Any]] = {}
    for row in entries:
        try:
            uid = int(row["id"])
            name = str(row["name"])
        except (KeyError, TypeError, ValueError):
            continue
        out[uid] = build_user_dict(uid, name)
    if not out:
        for row in _default_snapshot():
            out[row["id"]] = build_user_dict(row["id"], row["name"])
    return dict(sorted(out.items()))


def save_users(users: dict[int, dict[str, Any]]) -> None:
    """Persist current id → name mapping."""
    payload = {
        "users": [{"id": int(k), "name": v["name"]} for k, v in sorted(users.items())],
    }
    try:
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as exc:
        print(f"[user_store] Could not write admin_users.json: {exc}")


def next_free_marker_id(users: dict[int, dict[str, Any]]) -> int:
    """Smallest non-negative integer not used as a marker id."""
    used = set(users.keys())
    n = 0
    while n in used:
        n += 1
    return n


def random_display_name() -> str:
    a, b = random.sample(_NAME_PARTS, 2)
    return f"{a} {b}"
