"""
character_map.py
----------------
Character Mapping Module.

Maps TUIO fiducial marker IDs (0-4) to character data used by the GUI.

Each character has:
  - name          : display name
  - theme_color   : primary accent hex color
  - bg_gradient   : tuple of two hex colors for the background gradient
  - glow_color    : neon glow ring color (for animated ring)
  - icon_char     : Unicode symbol used as avatar icon fallback

Extend or modify this dictionary to change character assignments or themes.
"""

CHARACTER_MAP = {
    0: {
        "name": "Nadeem",
        "theme_color": "#00B4FF",      # Electric Blue
        "bg_gradient": ("#0a0a1a", "#001a33"),
        "glow_color": "#00D4FF",
        "accent_rgb": (0, 180, 255),
        "icon_char": "⚔",
        "title": "The Warrior",
        "gif": "blue animation.gif",
        "avatar": "blue user.jpg",
    },
    1: {
        "name": "Seif",
        "theme_color": "#00FF88",      # Neon Green
        "bg_gradient": ("#0a1a0a", "#001a11"),
        "glow_color": "#00FF99",
        "accent_rgb": (0, 255, 136),
        "icon_char": "🏹",
        "title": "The Archer",
        "gif": "green animation.gif",
        "avatar": "green user.jpg",
    },
    2: {
        "name": "Ahmed",
        "theme_color": "#FF3B3B",      # Plasma Red
        "bg_gradient": ("#1a0a0a", "#330000"),
        "glow_color": "#FF4444",
        "accent_rgb": (255, 59, 59),
        "icon_char": "🔥",
        "title": "The Mage",
        "gif": "orange animation.gif",
        "avatar": "orange user.jpg",
    },
    3: {
        "name": "Ali",
        "theme_color": "#BB44FF",      # Royal Purple
        "bg_gradient": ("#100a1a", "#1a0033"),
        "glow_color": "#CC55FF",
        "accent_rgb": (187, 68, 255),
        "icon_char": "🗡",
        "title": "The Rogue",
        "gif": "purple animation.gif",
        "avatar": "purple user.jpg",
    },
}


def get_character(marker_id: int) -> dict | None:
    """Return the character dict for *marker_id*, or None if not mapped."""
    return CHARACTER_MAP.get(marker_id)


def get_all_characters() -> dict:
    """Return the full character mapping."""
    return CHARACTER_MAP
