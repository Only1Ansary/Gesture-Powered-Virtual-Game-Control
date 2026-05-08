# Gesture-Powered Virtual Game Control

HCI Project -- TUIO / reacTIVision integration

---

## Overview

The **main application GUI** is the C# WinForms app in **`FruitNinjaGame/`** (launch with **`run.bat`** or `dotnet run` on the `.csproj`). It authenticates users via **TUIO fiducial markers** detected by **reacTIVision**. Placing a marker in front of the camera opens that user's page. Rotating the marker **left** returns to the main menu; **right** launches the configured game.

Python modules in the repo support **TUIO**, **game launch**, optional **gaze recording** (`gaze_session_cli.py`, started by the C# UI), and other side services — not a Tkinter front-end (the old `app_entry.py` prototype has been removed).

An **admin** screen (user add/remove) unlocks only when a **specific Bluetooth device** is present **and** a dedicated **admin TUIO marker** is held on the main menu.

A **circular radial menu** opens while a dedicated **menu TUIO marker** (default **10**) is visible: **up/down** = Windows master volume; **left** = terminate tracked game + fullscreen GUI; **right** = minimize other windows + fullscreen GUI; **right-up** = if the game is fullscreen/maximized, minimize the game and fullscreen the GUI; **right-down** = maximize/focus the game and minimize the GUI. Removing the marker closes the menu. You can also **tap** a wedge with the mouse/touchscreen; TUIO volume repeats while hovering.

---

## Features

- **C# WinForms UI** -- main menu, per-user profile flow, TUIO integration, game launch.
- **reacTIVision** -- auto-launched in the background (path in `config.json`).
- **TUIO OSC** -- `python-osc` on a background thread.
- **Rotation navigation** -- left = menu, right = launch game.
- **Admin mode** -- Bluetooth gate + TUIO marker `9` (configurable) to manage users (stored in `admin_users.json`).
- **Circular TUIO menu** -- marker `10` (configurable) for volume + window actions; see `tuio_circular_menu.py` and `menu_*` keys in `config.json`.
- **Eye-gaze heatmaps** -- optional dedicated-camera gaze tracking records per-user sessions, writes `gaze_data/user_<id>/heatmap.png`, and adapts profile action placement on the next visit.
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
| `dlib-bin` | 20.0.1 | Windows prebuilt dlib runtime for eye-gaze tracking |
| `pandas`, `seaborn`, `matplotlib` | current | Per-user heatmap generation |

> **`opencv-python` and `mediapipe`** are only used by `gesture_controller.py` (hand-tracking). If you are not using hand tracking you can skip them -- the app runs fine without them.

> **Eye gaze on Windows:** after `pip install -r requirements.txt`, install the gaze package with `python -m pip install --no-deps git+https://github.com/antoinelame/GazeTracking.git`. This avoids compiling `dlib` from source because `dlib-bin` already provides the runtime module.

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

# 4. Run the main GUI (Windows)
run.bat

# Or from the repo root:
# dotnet run --project FruitNinjaGame\FruitNinjaGame.csproj
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
| `reactvision_camera_index` | **DirectShow / videoInput** device id for **reacTIVision** (same numbering as `reacTIVision.exe -l`). **Not** the same as OpenCV’s camera index for Python. Written into `camera.xml` when the GUI launches reacTIVision. |
| `reactvision_camera_name_contains` | Optional: substring matched against names from `reacTIVision.exe -l` (e.g. `ASUS FHD` for a built-in webcam). When set, the GUI runs `-l`, picks the first matching device id, and **overrides** the numeric index for `camera.xml`. Leave `""` to use only `reactvision_camera_index`. **Matching skips any device whose name contains `Iriun`.** |

**reacTIVision persists `camera.xml` when it exits.** The GUI therefore **stops** any previous bundled reacTIVision session **before** writing `camera.xml`, then starts a new process — otherwise shutdown would overwrite your ASUS choice with the Iriun stream that was open.
| `gaze_camera_index` | **OpenCV** index for eye gaze (`gaze_session_cli.py`). If this numeric value equals `reactvision_camera_index`, the GUI may stop/restart reacTIVision while gaze records — prefer distinct physical cameras. |
| `emotion_camera_index` | **OpenCV** index for `emotion_server.py` — unique among gaze / emotion / YOLO / hand |
| `yolo_camera_index` | **OpenCV** index for `yolo_object_tracker.py` — unique among those four |
| `hand_tracker_camera_index` | **OpenCV** index for `hand_controller.py` — unique among those four |

**Why TUIO used Iriun with `reactvision_camera_index: 0`:** On Windows, DirectShow often lists **Iriun** as device **0** and the real laptop cam later (e.g. **2** for “ASUS FHD webcam”). OpenCV may order devices differently. Use `reacTIVision.exe -l` for reacTIVision, and set `reactvision_camera_name_contains` or the correct DirectShow id.

Defaults in code are **0 / 1 / 2 / 3 / 4** (reacTIVision / gaze / emotion / YOLO / hand) for fallbacks only — tune per machine.

The GUI logs `WARNING: config.json reuses OpenCV camera index…` if gaze, emotion, YOLO, or hand share an OpenCV index.

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

### Eye gaze heatmaps (`config.json`)

| Key | Description |
|-----|-------------|
| `gaze_enabled` | Enable/disable eye-gaze recording and adaptive profile layouts |
| `gaze_camera_index` | **OpenCV** device index for gaze (often **0** for the first **Iriun** entry in DirectShow; compare indices with `reacTIVision.exe -l`) |
| `gaze_opencv_dshow_first` | If **true**, try **DirectShow** (`CAP_DSHOW`) before MSMF when opening the gaze camera — use for **Iriun / phone** streams so the index matches typical DirectShow order; **false** keeps MSMF-first (better for many laptop webcams) |
| `gaze_sample_interval_ms` | Delay between gaze samples |
| `gaze_min_samples` | Minimum samples before writing an adaptive `layout.json` |
| `gaze_smooth_alpha` | Low-pass smoothing for gaze points, higher = smoother |
| `gaze_data_dir` | Folder for `user_<id>/last_session.csv`, `last_session.json`, `heatmap.png`, and `layout.json` |
| `gaze_heatmap_grid_columns` / `gaze_heatmap_grid_rows` | Grid used to find most-looked hot zones |
| `gaze_layout_margin_ratio` | Keeps adaptive anchors away from screen edges |
| `gaze_layout_min_distance` | Minimum normalized distance between primary action anchors |

---

## Architecture

| File | Description |
|------|-------------|
| `FruitNinjaGame/GUIForm.cs` | Main C# WinForms GUI; starts TUIO, user profile flow, game launch, and gaze sidecar |
| `gaze_session_cli.py` | Python gaze recorder sidecar started/stopped by the C# GUI for each profile session |
| `tuio_circular_menu.py` | Radial menu logic (shared concepts; C# hosts the main menu UI) |
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
