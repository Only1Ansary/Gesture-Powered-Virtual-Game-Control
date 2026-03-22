# VRDriver — Custom SteamVR TUIO Controller Driver

A SteamVR driver DLL that registers **two virtual Valve Index controllers** and receives pose data from a Python app via Windows named pipes.

This replaces OpenVR-InputEmulator, which incorrectly classifies virtual devices as Vive Trackers instead of controllers.

## Building

1. Open `VRDriver.slnx` in Visual Studio 2022
2. Set platform to **x64** and configuration to **Release**
3. Build Solution → produces `VRDriver.dll`

### Post-build step (optional)

Add this to **Project → Properties → Build Events → Post-Build Event**:

```
xcopy /Y "$(OutDir)VRDriver.dll" "C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\tuio_controller\bin\win64\"
```

## Installation

1. Create the SteamVR driver folder structure:
   ```
   C:\Program Files (x86)\Steam\steamapps\common\SteamVR\drivers\tuio_controller\
   ├── driver.vrdrivermanifest
   └── bin\win64\
       ├── VRDriver.dll
       └── openvr_api.dll
   ```

2. Copy `driver.vrdrivermanifest` from `drivers/tuio_controller/` into the driver root folder above

3. Copy the built `VRDriver.dll` and `openvr_api.dll` into the `bin/win64/` folder

4. Restart SteamVR

## Driver Architecture

```
SteamVR
  └─ HmdDriverFactory()          ← dllmain.cpp
       └─ TuioDriverProvider      ← IServerTrackedDeviceProvider
            ├─ TuioControllerDriver (left)   ← ITrackedDeviceServerDriver
            │    └─ PipeListener (\\.\pipe\tuio_controller_left)
            └─ TuioControllerDriver (right)
                 └─ PipeListener (\\.\pipe\tuio_controller_right)
```

Each `PipeListener` creates a named pipe server and runs a background thread that reads **28-byte packets** (7 × float32: `x, y, z, qw, qx, qy, qz`) and pushes pose updates to SteamVR.

## Testing

1. Start SteamVR (with null driver — no physical headset needed)
2. Confirm two controller icons appear in the SteamVR status window (not tracker icons)
3. Run the Python bridge: `python vr_bridge.py` (from the project root)
4. Move TUIO markers → controllers should move in SteamVR Home mirror window
5. Launch Beat Saber → sabers respond to marker movement

### Dry-run (no SteamVR needed)

```bash
python vr_bridge.py --dry-run
```

## Named Pipe Protocol

| Field | Type    | Bytes | Description                |
|-------|---------|-------|----------------------------|
| x     | float32 | 0–3   | Position X (metres)        |
| y     | float32 | 4–7   | Position Y (metres)        |
| z     | float32 | 8–11  | Position Z (metres)        |
| qw    | float32 | 12–15 | Quaternion W               |
| qx    | float32 | 16–19 | Quaternion X               |
| qy    | float32 | 20–23 | Quaternion Y               |
| qz    | float32 | 24–27 | Quaternion Z               |

Python sends:
```python
data = struct.pack('7f', x, y, z, qw, qx, qy, qz)
win32file.WriteFile(pipe_handle, data)
```
