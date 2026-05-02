# Gesture-Powered Virtual Game Control

HCI Project -- TUIO / reacTIVision integration

---

## Overview

A fullscreen Python GUI that authenticates users via **TUIO fiducial markers** detected by **reacTIVision**. Placing a marker in front of the camera opens that user's page (theme + animated background). Rotating the marker **left** returns to the main menu; **right** launches the configured game.

An **admin** screen (user add/remove) unlocks only when a **specific Bluetooth device** is present **and** a dedicated **admin TUIO marker** is held on the main menu.

A **circular radial menu** opens while a dedicated **menu TUIO marker** (default **10**) is visible: **up/down** = Windows master volume; **left** = terminate tracked game + fullscreen GUI; **right** = minimize other windows + fullscreen GUI; **right-up** = if the game is fullscreen/maximized, minimize the game and fullscreen the GUI; **right-down** = maximize/focus the game and minimize the GUI. Removing the marker closes the menu. You can also **tap** a wedge with the mouse/touchscreen; TUIO volume repeats while hovering.

---

## Features

- **Fullscreen Tkinter UI** -- GIF backgrounds, per-user themes, screen transitions.
- **reacTIVision** -- auto-launched in the background (path in `config.json`).
- **TUIO OSC** -- `python-osc` on a background thread.
- **Rotation navigation** -- left = menu, right = launch game.
- **Admin mode** -- Bluetooth gate + TUIO marker `9` (configurable) to manage users (stored in `admin_users.json`).
- **Circular TUIO menu** -- marker `10` (configurable) for volume + window actions; see `tuio_circular_menu.py` and `menu_*` keys in `config.json`.
- **`config.json`** -- game path, TUIO, admin Bluetooth, menu tuning, etc.

---

## Requirements

- **Python 3.10+** (3.11 recommended on Windows -- use the python.org installer and tick **tcl/tk** in optional features so Tkinter is included)
- **reacTIVision 1.5.1** (or compatible) -- free download; set its path in `config.json`

### 1. Install core dependencies

```bash
pip install -r requirements.txt
```

| Package | Min version | Purpose |
|---------|------------|---------|
| `Pillow` | 12.0 | Image loading, GIF animation |
| `python-osc` | 1.9.3 | TUIO / OSC UDP listener |
| `pywin32` | 311 | Window minimize / focus / fullscreen (Windows only) |
| `pycaw` | 20251023 | Windows master-volume control in circular menu |
| `comtypes` | 1.4 | Required by pycaw |
| `opencv-python` | 4.8 | Webcam capture for hand-tracking (gesture controller) |
| `mediapipe` | 0.10 | Hand-pose detection (gesture controller) |

> **`opencv-python` and `mediapipe`** are only used by `gesture_controller.py` (hand-tracking). If you are not using hand tracking you can skip them -- the app runs fine without them.

> **`pywin32`, `pycaw`, `comtypes`** are Windows-only. On Linux/macOS the code no-ops safely, but the circular menu volume and window actions will not function.

### 2. Optional: in-app Bluetooth scanning

The admin screen can detect your admin Bluetooth device at runtime via **PyBluez**:

```bash
pip install -r requirements-bluetooth.txt
```

- **Linux / macOS** -- `pybluez` usually installs cleanly.
- **Windows** -- PyBluez often fails to build from PyPI. If it does:
  1. Pair your admin device with the PC first.
  2. Run **`list_bluetooth_devices.ps1`** (PowerShell helper in this repo) to get the MAC address.
  3. Set that MAC in **`config.json`** as `admin_bluetooth_mac` (no PyBluez needed at runtime).
  4. For local testing without Bluetooth hardware set `"admin_bluetooth_force": true` in `config.json`.

---

## Setup & running

```bash
# 1. Clone
git clone <repo-url>
cd "<repo-folder>"

# 2. Install dependencies
pip install -r requirements.txt

# Optional Bluetooth admin scanning:
# pip install -r requirements-bluetooth.txt

# 3. Edit config.json -- set your paths:
#    "reactvision_exe": "path/to/reacTIVision.exe"
#    "game_exe":        "path/to/YourGame.exe"

# 4. Run
python app_entry.py
```

**TUIO marker IDs to configure in reacTIVision:**

| ID | Role |
|----|------|
| 0-3 | Users (default Alex / Blake / Casey / Dana) |
| 9 | Admin unlock (`admin_tuio_marker` in config) |
| 10 | Circular menu (`menu_tuio_marker` in config) |

> **Keyboard shortcuts for testing without hardware:** keys **0-3** simulate user markers, **M** toggles the circular menu, **Left/Right arrows** simulate rotation.

---

## Admin Bluetooth setup

Admin access requires **both**:

1. The app considers your **allowed Bluetooth device** present (see config).
2. On the **main menu**, you hold the **admin TUIO marker** (default ID **9**).

### Step A -- Find your device MAC (recommended)

**Windows (paired device):**

```powershell
cd path\to\this\repo
powershell -ExecutionPolicy Bypass -File .\list_bluetooth_devices.ps1
```

Copy the **MAC** next to the device you want (e.g. `7c:03:ab:2a:0c:ce`).

**Linux / others:** pair the device, then use `bluetoothctl devices`, `hcitool scan`, or install PyBluez and run a small discovery script.

### Step B -- Edit `config.json`

Use **either** MAC **or** exact name (MAC is preferred -- one unique device).

```json
{
  "admin_tuio_marker": 9,
  "admin_bluetooth_mac": "7c:03:ab:2a:0c:ce",
  "admin_bluetooth_name": "",
  "admin_bluetooth_scan_seconds": 6,
  "admin_bluetooth_poll_seconds": 3,
  "admin_bluetooth_ttl_seconds": 45,
  "admin_bluetooth_force": false
}
```

| Key | Description |
|-----|-------------|
| `admin_tuio_marker` | TUIO fiducial ID that opens admin (must not clash with user markers 0-3). |
| `admin_bluetooth_mac` | **Exact** MAC of the one allowed device (normalized: `:` or `-`). If set, **only** this address matches. |
| `admin_bluetooth_name` | Use only if MAC is empty: full Bluetooth name, exact match (case-insensitive). |
| `admin_bluetooth_scan_seconds` | PyBluez inquiry duration per scan. |
| `admin_bluetooth_poll_seconds` | Sleep between scans. |
| `admin_bluetooth_ttl_seconds` | How long "last seen" keeps admin gate open if a scan misses the device. |
| `admin_bluetooth_force` | `true` = skip Bluetooth check (testing only). |

**Legacy:** `admin_bluetooth_names` (array) -- if present and `admin_bluetooth_name` is empty, the **first** string is used as the single name.

### Step C -- reacTIVision

Add / enable the **admin** pattern (e.g. ID **9**) in your reacTIVision marker configuration so the camera reports that TUIO id.

User changes from the admin UI are saved to **`admin_users.json`** in the project folder.

**On the admin screen (TUIO-only):** move the **admin marker** **up/down** (relative to a neutral hold) to change the highlighted user; **push the marker to the right** (displacement, edge-triggered) to **add** a random user; **rotate the marker right** to **remove** the selected user; **rotate left** to return to the main menu.

---

## Configuration (`config.json`) -- core keys

```json
{
  "reactvision_exe": "reacTIVision-1.5.1-win64/reacTIVision.exe",
  "game_exe": "path/to/your/game.exe",
  "tuio_host": "0.0.0.0",
  "tuio_port": 3333,
  "rotation_threshold": 0.5
}
```

| Key | Description |
|-----|-------------|
| `reactvision_exe` | Path to `reacTIVision.exe` |
| `game_exe` | Path to the game to launch |
| `tuio_host` / `tuio_port` | OSC listen address / port (default **3333**) |
| `rotation_threshold` | Angular velocity (rad/s) for rotation events |

### Circular menu (`config.json`)

| Key | Description |
|-----|-------------|
| `menu_tuio_marker` | Fiducial ID that opens the radial overlay (default `10`) |
| `menu_motion_threshold` | TUIO displacement (0-1 scale) before a direction counts |
| `menu_smooth_alpha` | Low-pass smoothing for cursor (0-1, higher = smoother) |
| `menu_volume_step` | Master volume delta each time VOL +/- fires |
| `menu_volume_repeat_seconds` | How often volume repeats while TUIO marker stays in VOL wedge |
| `menu_action_cooldown_seconds` | Min seconds between any wedge action (tap or TUIO); default **2.0** |
| `menu_cursor_gain` | How far the on-screen cursor moves per TUIO delta |

**Game exit** from the menu only works when the game was launched as a **direct `.exe`** via `launch_game` (not `.lnk` shortcuts -- those are not tracked).

---

## Architecture

| File | Description |
|------|-------------|
| `app_entry.py` | Tkinter app -- screens, TUIO callbacks, admin UI, menu wiring |
| `tuio_circular_menu.py` | Fullscreen radial overlay + TUIO motion to sectors |
| `windows_controls.py` | Volume (pycaw), minimize-other-windows, focus GUI |
| `tuio_listener.py` | TUIO OSC listener thread |
| `character_map.py` | Default marker 0-3 to themes (assets, colours) |
| `user_store.py` | Load/save `admin_users.json`, random names, presets |
| `bluetooth_admin.py` | Optional PyBluez scan; sets "admin device present" flag |
| `game_launcher.py` | Launches game; process tracking for terminate/PID |
| `gesture_controller.py` | Webcam hand-tracking controller |
| `config.py` | Loads `config.json` |
| `gif_utils.py` | GIF load / cache / animate |
| `config.json` | Local settings (paths, TUIO, admin Bluetooth, menu tuning) |
| `list_bluetooth_devices.ps1` | Windows helper -- list paired BT devices for config |
| `requirements.txt` | Core Python dependencies |
| `requirements-bluetooth.txt` | Optional `pybluez` for in-app Bluetooth scanning |

---

## Character mapping (default users)

| Marker ID | Name  | Theme  |
|-----------|-------|--------|
| 0 | Alex  | Blue   |
| 1 | Blake | Green  |
| 2 | Casey | Orange |
| 3 | Dana  | Purple |

**Admin marker:** default **9** (`admin_tuio_marker`). **Menu marker:** default **10** (`menu_tuio_marker`). Edit defaults in `character_map.py`; runtime list in **`admin_users.json`** after admin changes.

---

## Licence / credits

Project files as provided in the repository; third-party tools (reacTIVision, game) have their own licences.
