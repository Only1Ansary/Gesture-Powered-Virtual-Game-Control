# Gesture Beat Saber Login System
HCI Project - TUIO / reacTIVision Integration

## Overview
This is a futuristic, dark-themed Python GUI application that logs in a user using a TUIO marker detected by the **reacTIVision** engine. Placing a marker in front of the camera triggers the UI to change its theme dynamically based on the specific character mapped to the fiducial ID, before finally launching the game executable.

## Features
- **Modern UI**: Built with PyQt5, featuring dynamic gradients, glowing text effects, and smooth transitions.
- **Custom TUIO Client**: A lightweight, dependency-free OSC/UDP packet decoder designed specifically for this task (running on a background thread to prevent GUI freezing).
- **Extensible Character Map**: Easily assign new colors, names, backgrounds, and icons to different fiducial IDs.
- **Game Launcher**: Uses `subprocess` to trigger your `game.exe` automatically without blocking the UI.

## Requirements
* Python 3.8+
* PyQt5 (for the beautifully animated GUI)

```bash
pip install PyQt5
```

## Setup & Running

1. **Start reacTIVision**: Run the `reacTIVision.exe` provided in your project folder. Make sure it is tracking your markers and broadcasting on the default port (`localhost:3333`).
2. **Add Game Executable**: Place your game executable named `game.exe` inside this same directory. (If it's missing, the console and GUI will gracefully display an error but won't crash).
3. **Launch the Interface**:

```bash
python main.py
```

## Architecture
- `main.py` - Connects all pieces and displays the `PyQt5` graphical interface.
- `tuio_listener.py` - Background thread that decodes raw TUIO OSC messages over UDP port 3333 and triggers callbacks.
- `character_map.py` - Definitions for characters (Styles, Colors, Names). Maps TUIO marker indices `0-4` to a specific character theme.
- `game_launcher.py` - Minimalist launcher module connecting Python bindings to your external `.exe`.

## Character Mapping
By default, the mapping is:
| Marker ID | Character | Glow Color |
| --------- | --------- | ---------- |
| 0         | Nadeem    | Blue       |
| 1         | Seif      | Green      |
| 2         | Ahmed     | Red        |
| 3         | Ali       | Purple     |
| 4         | Ibrahim   | Orange     |

To modify the assignments, just open and edit `character_map.py`.
