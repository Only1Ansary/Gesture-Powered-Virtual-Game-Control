"""
game_launcher.py
----------------
Handles launching the game executable configured in config.json.
"""

import os
import subprocess

from config import BASE_DIR, GAME_EXE


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
        game_dir = os.path.dirname(GAME_EXE) or BASE_DIR
        subprocess.Popen([GAME_EXE], cwd=game_dir)
        print(f"[GameLauncher] Launched: {GAME_EXE}  (character={character_name!r})")
        return True, ""
    except Exception as exc:
        msg = f"Launch failed:\n{exc}"
        print(f"[GameLauncher] ERROR: {exc}")
        return False, msg
