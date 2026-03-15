# Gesture-Powered Virtual Game Control

HCI Project — TUIO / reacTIVision Integration  
**Branch: Ali's Theme**

---

## Overview

A fullscreen Python GUI application that authenticates users via **TUIO fiducial markers** detected by the **reacTIVision** engine. Placing a physical marker in front of a camera triggers a personalised user page with a unique colour theme and animated background. The user can then rotate the marker to navigate back to the main menu or launch a game.

---

## Features

- **Fullscreen Tkinter UI** — animated GIF backgrounds, per-user colour themes, and smooth screen transitions.
- **Automatic reacTIVision Launch** — the app starts `reacTIVision.exe` in the background on startup.
- **TUIO OSC Listener** — powered by `python-osc`, running on a background thread to keep the UI responsive.
- **Rotation-Based Navigation** — rotate marker **left** to return to the main menu, rotate **right** to launch the configured game.
- **Configurable via `config.json`** — set game path, TUIO host/port, and rotation sensitivity without touching any code.

---

## Requirements

- Python 3.10+
- [Pillow](https://pypi.org/project/Pillow/)
- [python-osc](https://pypi.org/project/python-osc/)

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Setup & Running

1. **Configure `config.json`** — set `game_exe` to the full path of your game executable and verify `reactvision_exe` points to `reacTIVision.exe`.
2. **Start reacTIVision** — the app will attempt to launch it automatically, but you can also run it manually first. Make sure it is broadcasting on the default port (`localhost:3333`).
3. **Launch the interface:**

```bash
python main.py
```

---

## Keyboard Shortcuts (no hardware needed)

| Key | Action |
|-----|--------|
| `0` / `1` / `2` / `3` | Simulate placing / removing marker for that user |
| `← Left Arrow` | Simulate rotating left (back to main menu) |
| `→ Right Arrow` | Simulate rotating right (launch game) |
| `F11` | Toggle fullscreen |
| `ESC` / `Q` | Exit |

---

## Architecture

| File | Description |
|------|-------------|
| `main.py` | Root Tkinter application — manages screen transitions and TUIO callbacks |
| `tuio_listener.py` | Background thread that decodes TUIO OSC messages over UDP and fires callbacks |
| `character_map.py` | Maps TUIO marker IDs to user themes (name, colours, GIF, avatar) |
| `game_launcher.py` | Launches the configured game executable via `subprocess` |
| `config.py` | Loads settings from `config.json` |
| `gif_utils.py` | GIF loading, resizing, caching, and animation helpers |
| `config.json` | Runtime configuration (game path, TUIO port, rotation threshold) |

---

## Character Mapping

| Marker ID | Name  | Theme  |
|-----------|-------|--------|
| 0         | Alex  | Blue   |
| 1         | Blake | Green  |
| 2         | Casey | Orange |
| 3         | Dana  | Purple |

To change assignments, edit `character_map.py`.

---

## Configuration (`config.json`)

```json
{
  "reactvision_exe":    "reacTIVision-1.5.1-win64/reacTIVision.exe",
  "game_exe":           "path/to/your/game.exe",
  "tuio_host":          "0.0.0.0",
  "tuio_port":          3333,
  "rotation_threshold": 0.5
}
```

| Key | Description |
|-----|-------------|
| `reactvision_exe` | Relative or absolute path to `reacTIVision.exe` |
| `game_exe` | Full path to the game executable to launch |
| `tuio_host` | Host to listen on (`0.0.0.0` = all interfaces) |
| `tuio_port` | UDP port reacTIVision broadcasts on (default `3333`) |
| `rotation_threshold` | Angular velocity (rad/s) required to trigger a rotation event |
