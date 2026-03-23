"""
game_launcher.py
----------------
Handles launching the game executable configured in config.json.

Exposes a module-level ``game_running`` threading.Event that is SET while the
game process is alive and CLEARED once it exits.  GUI callbacks can check
``game_running.is_set()`` to suppress navigation while the game is active.
"""

import os
import subprocess
import threading

from config import BASE_DIR, GAME_EXE

# Thread-safe flag: set while the game process is running.
# GUI TUIO callbacks should check  game_running.is_set()  and return
# immediately if True so that rotation gestures don't trigger navigation.
game_running = threading.Event()

_game_lock = threading.Lock()
# Populated when launch_game starts a tracked subprocess (.exe, not .lnk).
_game_process: subprocess.Popen | None = None


def _watch_process(process: subprocess.Popen, on_exit=None) -> None:
    process.wait()

    with _game_lock:
        global _game_process
        if _game_process is process:
            _game_process = None

    game_running.clear()

    print("[GameLauncher] Game exited.")

    if on_exit:
        try:
            on_exit()
        except Exception as e:
            print(f"[GameLauncher] on_exit error: {e}")


def get_tracked_game_pid() -> int | None:
    """PID of the game launched via Popen from launch_game, or None if not running."""
    with _game_lock:
        proc = _game_process
    if proc is None or proc.poll() is not None:
        return None
    try:
        return int(proc.pid)
    except Exception:
        return None


def terminate_game() -> bool:
    """
    Terminate the game subprocess started via launch_game (non-.lnk only).

    Returns True if a running process was signalled to stop.
    """
    global _game_process
    with _game_lock:
        proc = _game_process
        _game_process = None
    if proc is None or proc.poll() is not None:
        game_running.clear()
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        game_running.clear()
        print("[GameLauncher] Game process terminated by circular menu / user.")
        return True
    except Exception as exc:
        print(f"[GameLauncher] terminate_game failed: {exc}")
        game_running.clear()
        return False


def launch_game(character_name: str = "", on_exit=None) -> tuple[bool, str]:
    """
    Launch the configured game executable.

    Parameters
    ----------
    character_name : str
        Name of the logged-in user (included in console output).

    Returns
    -------
    (success, error_message)
        success is True when the process was spawned without error.
        error_message is an empty string on success.
    """
    if not GAME_EXE or not os.path.isfile(GAME_EXE):
        hint = GAME_EXE if GAME_EXE else "<not set>"
        msg  = (
            "Game executable not found.\n\n"
            "Set  \"game_exe\"  in  config.json\n"
            f"(looked for: {hint})"
        )
        print(f"[GameLauncher] WARN: {msg}")
        return False, msg

    try:
        if GAME_EXE.lower().endswith(".lnk"):
            # .lnk shortcuts can't be launched via Popen; use the Windows shell
            os.startfile(GAME_EXE)
            # For .lnk files we can't easily track the child process,
            # so we don't set game_running here.
        else:
            game_dir = os.path.dirname(GAME_EXE) or BASE_DIR
            process = subprocess.Popen([GAME_EXE], cwd=game_dir)

            with _game_lock:
                global _game_process
                _game_process = process

            # Mark game as running and start a watcher thread
            game_running.set()
            watcher = threading.Thread(
            target=_watch_process,
            args=(process, on_exit),
            daemon=True,
            )
            watcher.start()

        print(f"[GameLauncher] Launched: {GAME_EXE}  (character={character_name!r})")
        return True, ""
    except Exception as exc:
        msg = f"Launch failed:\n{exc}"
        print(f"[GameLauncher] ERROR: {exc}")
        game_running.clear()
        return False, msg
