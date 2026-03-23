# Gesture-Powered Virtual Game Control

HCI Project — TUIO / reacTIVision integration

---

## Overview

A fullscreen Python GUI that authenticates users via **TUIO fiducial markers** detected by **reacTIVision**. Placing a marker in front of the camera opens that user’s page (theme + animated background). Rotating the marker **left** returns to the main menu; **right** launches the configured game.

An **admin** screen (user add/remove) unlocks only when a **specific Bluetooth device** is present **and** a dedicated **admin TUIO marker** is held on the main menu.

A **circular radial menu** opens while a dedicated **menu TUIO marker** (default **10**) is visible: **up/down** = Windows master volume; **left** = terminate tracked game + fullscreen GUI; **right** = minimize other windows + fullscreen GUI; **right-up** (upper-right wedge) = if the tracked game is **fullscreen/maximized**, minimize the game and fullscreen the GUI; **right-down** (lower-right) = if a **tracked .exe** is running, maximize/focus the game and **minimize the GUI** (overlay closes; show the marker again to reopen the menu). A cursor and wedge highlights track motion. **Removing** the marker closes the menu.

---

## Features

- **Fullscreen Tkinter UI** — GIF backgrounds, per-user themes, screen transitions.
- **reacTIVision** — auto-launched in the background (path in `config.json`).
- **TUIO OSC** — `python-osc` on a background thread.
- **Rotation navigation** — left → menu, right → launch game.
- **Admin mode** — Bluetooth gate + TUIO marker `9` (configurable) → manage users (stored in `admin_users.json`).
- **Circular TUIO menu** — marker `10` (configurable) → volume + window actions; see `tuio_circular_menu.py` and `menu_*` keys in `config.json`.
- **`config.json`** — game path, TUIO, VR bridge, admin Bluetooth, menu tuning, etc.

---

## Requirements

- **Python 3.10+**
- **Core Python packages** (install first):

```bash
pip install -r requirements.txt
```

| Package      | Purpose                          |
|-------------|-----------------------------------|
| Pillow      | Images / GIF frames               |
| python-osc  | TUIO / OSC over UDP               |
| pywin32     | Windows window ops (menu / focus) |
| pycaw + comtypes | Windows master volume (menu) |

### Optional: Bluetooth discovery in the app (PyBluez)

The admin screen can use **PyBluez** to scan for your configured device MAC during runtime:

```bash
pip install -r requirements-bluetooth.txt
```

- **Linux** (and many **macOS** setups): `pybluez` often installs cleanly.
- **Windows**: building `pybluez` from PyPI frequently **fails**. You can still configure admin:
  1. Pair your admin device with the PC.
  2. Run **`list_bluetooth_devices.ps1`** (PowerShell) to read the device **MAC** from Windows.
  3. Put that MAC in **`config.json`** → `admin_bluetooth_mac` (see below).
  4. For local testing without Bluetooth scanning, set **`admin_bluetooth_force`: `true`** (do not use in production).

---

## Setup & running

1. **Clone the repo** and create **`config.json`** from your team’s template (or edit the one in the repo).
2. Set **`game_exe`** and **`reactvision_exe`** to valid paths on your machine.
3. **TUIO patterns** — include marker IDs **0–3** (users), **admin** (default **9** → `admin_tuio_marker`), and **circular menu** (default **10** → `menu_tuio_marker`).
4. **Admin Bluetooth** — see [Admin Bluetooth setup](#admin-bluetooth-setup).
5. Run:

```bash
python main.py
```

---

## Admin Bluetooth setup

Admin access requires **both**:

1. The app considers your **allowed Bluetooth device** present (see config).
2. On the **main menu**, you hold the **admin TUIO marker** (default ID **9**).

### Step A — Find your device MAC (recommended)

**Windows (paired device):**

```powershell
cd path\to\this\repo
powershell -ExecutionPolicy Bypass -File .\list_bluetooth_devices.ps1
```

Copy the **MAC** next to the device you want (e.g. `7c:03:ab:2a:0c:ce`).

**Linux / others:** pair the device, then use `bluetoothctl devices`, `hcitool scan`, or install PyBluez and run a small discovery script.

### Step B — Edit `config.json`

Use **either** MAC **or** exact name (MAC is preferred — one unique device).

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
| `admin_tuio_marker` | TUIO fiducial ID that opens admin (must not clash with user markers **0–3**). |
| `admin_bluetooth_mac` | **Exact** MAC of the one allowed device (normalized: `:` or `-`). If set, **only** this address matches. |
| `admin_bluetooth_name` | Use only if MAC is empty: **full** Bluetooth name, **exact** match (case-insensitive). |
| `admin_bluetooth_scan_seconds` | PyBluez inquiry duration per scan. |
| `admin_bluetooth_poll_seconds` | Sleep between scans. |
| `admin_bluetooth_ttl_seconds` | How long “last seen” keeps admin gate open if a scan misses the device. |
| `admin_bluetooth_force` | `true` = skip Bluetooth check (testing only). |

**Legacy:** `admin_bluetooth_names` (array) — if present and `admin_bluetooth_name` is empty, the **first** string is used as the single name.

### Step C — reacTIVision

Add / enable the **admin** pattern (e.g. ID **9**) in your reacTIVision marker configuration so the camera reports that TUIO id.

User changes from the admin UI are saved to **`admin_users.json`** in the project folder.

**On the admin screen (TUIO-only):** move the **admin marker** **up/down** (relative to a neutral hold) to change the highlighted user; **push the marker to the right** (displacement, edge-triggered) to **add** a random user; **rotate the marker right** to **remove** the selected user; **rotate left** to return to the main menu. Uses the same `menu_motion_threshold` / `menu_smooth_alpha` / `menu_volume_repeat_seconds` / `menu_action_cooldown_seconds` style tuning as the circular menu where applicable.

---

## Configuration (`config.json`) — core keys

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

VR bridge keys are optional; see `config.py` for defaults.

### Circular menu (`config.json`)

| Key | Description |
|-----|-------------|
| `menu_tuio_marker` | Fiducial ID that opens the radial overlay (default `10`) |
| `menu_motion_threshold` | TUIO displacement (0–1 scale) before a direction “counts” |
| `menu_smooth_alpha` | Low-pass smoothing for cursor (0–1, higher = smoother) |
| `menu_volume_step` | Master volume delta per repeat while in up/down wedge |
| `menu_volume_repeat_seconds` | How often volume repeats while held in a wedge |
| `menu_action_cooldown_seconds` | Min time between left/right actions |
| `menu_cursor_gain` | How far the on-screen cursor moves per TUIO delta |

**Game exit** from the menu only works when the game was launched as a **direct `.exe`** via `launch_game` (not `.lnk` shortcuts — those are not tracked).

---

## Architecture

| File | Description |
|------|-------------|
| `main.py` | Tkinter app — screens, TUIO callbacks, admin UI, menu wiring |
| `tuio_circular_menu.py` | Fullscreen radial overlay + TUIO motion → sectors |
| `windows_controls.py` | Volume (pycaw), minimize-other-windows, focus GUI |
| `tuio_listener.py` | TUIO OSC listener thread |
| `character_map.py` | Default marker **0–3** → themes (assets, colours) |
| `user_store.py` | Load/save `admin_users.json`, random names, presets |
| `bluetooth_admin.py` | Optional PyBluez scan; sets “admin device present” flag |
| `game_launcher.py` | Launches game; optional process tracking |
| `config.py` | Loads `config.json` |
| `gif_utils.py` | GIF load / cache / animate |
| `vr_bridge.py` | Optional VR input bridge |
| `config.json` | Local settings (paths, TUIO, admin Bluetooth, VR) |
| `list_bluetooth_devices.ps1` | Windows helper — list paired BT devices → MAC for config |
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
