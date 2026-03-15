"""
character_map.py
----------------
Maps TUIO fiducial marker IDs (0–3) to user data used by the GUI.

Each user has:
  - name       : display name
  - bg         : page background colour
  - header_bg  : header / game-bar background colour
  - accent     : primary accent colour
  - glow       : softer glow / highlight colour
  - fg         : foreground (text) colour
  - gif        : absolute path to the animated GIF background
  - avatar     : absolute path to the user avatar image

Extend or modify USERS to change assignments or themes.
"""

import os

_A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Assests")

USERS: dict[int, dict] = {
    0: {
        "name":      "Alex",
        "bg":        "#0d1b2a",
        "header_bg": "#03045e",
        "accent":    "#00b4d8",
        "glow":      "#90e0ef",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "blue animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "blue user.jpg"),
    },
    1: {
        "name":      "Blake",
        "bg":        "#1b4332",
        "header_bg": "#081c15",
        "accent":    "#52b788",
        "glow":      "#d8f3dc",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "green animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "green user.jpg"),
    },
    2: {
        "name":      "Casey",
        "bg":        "#370617",
        "header_bg": "#03071e",
        "accent":    "#f48c06",
        "glow":      "#ffba08",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "orange animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "orange user.jpg"),
    },
    3: {
        "name":      "Dana",
        "bg":        "#240046",
        "header_bg": "#10002b",
        "accent":    "#c77dff",
        "glow":      "#e0aaff",
        "fg":        "#ffffff",
        "gif":       os.path.join(_A, "bk gifs",    "purple animation.gif"),
        "avatar":    os.path.join(_A, "user icons", "purple user.jpg"),
    },
}

MAIN_BK_GIF = os.path.join(_A, "bk gifs",    "main bk.gif")
GAME_ICON   = os.path.join(_A, "game icons", "Beat_Saber_logo.jpg")


def get_user(marker_id: int) -> dict | None:
    """Return the user dict for *marker_id*, or None if not mapped."""
    return USERS.get(marker_id)


def get_all_users() -> dict[int, dict]:
    """Return the full user mapping."""
    return USERS
