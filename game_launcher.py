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


def _watch_process(process: subprocess.Popen) -> None:
    """Background daemon thread that waits for the game to exit."""
    process.wait()
    game_running.clear()
    print("[GameLauncher] Game process exited — GUI TUIO re-enabled.")


def launch_game(character_name: str = "") -> tuple[bool, str]:
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

            # Mark game as running and start a watcher thread
            game_running.set()
            watcher = threading.Thread(
                target=_watch_process,
                args=(process,),
                daemon=True,
                name="GameWatcher",
            )
            watcher.start()

        print(f"[GameLauncher] Launched: {GAME_EXE}  (character={character_name!r})")
        return True, ""
    except Exception as exc:
        msg = f"Launch failed:\n{exc}"
        print(f"[GameLauncher] ERROR: {exc}")
        game_running.clear()
        return False, msg
