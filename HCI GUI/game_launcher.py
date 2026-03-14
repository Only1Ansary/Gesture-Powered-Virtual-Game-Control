"""
game_launcher.py
----------------
Game Launcher Module.

Provides a single function to launch the Beat Saber tiles game executable
using subprocess.  The launcher searches for the executable relative to
this script's directory.
"""

import subprocess
import os
import sys


# Path to the game executable.
GAME_EXECUTABLE = r"D:\DeskDump\Minecraft Launcher\Content\Minecraft.exe"


def launch_game(character_name: str = "") -> bool:
    """
    Launch the game executable.

    Parameters
    ----------
    character_name : str
        The name of the logged-in character (may be passed as an argument
        to the game, if desired).

    Returns
    -------
    bool
        True if the process was spawned successfully, False otherwise.
    """
    # Look for the exe.
    exe_path = GAME_EXECUTABLE

    if not os.path.isfile(exe_path):
        print(f"[GameLauncher] WARNING: '{exe_path}' not found.")
        print("[GameLauncher] Provide correct game.exe path.")
        return False

    try:
        # Popen is non-blocking — the GUI stays open (or can be minimised).
        cmd = [exe_path]
        if character_name:
            cmd.append(f"--character={character_name}")
        subprocess.Popen(cmd, cwd=base_dir)
        print(f"[GameLauncher] Launched '{exe_path}' for character: {character_name}")
        return True
    except Exception as exc:
        print(f"[GameLauncher] Failed to launch game: {exc}")
        return False
