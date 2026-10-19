#!/usr/bin/env python3
"""Installer for War Brokers Discord Rich Presence.

Puts wb_rpc.py in a fixed folder and prints the Steam launch option to paste
(also copied to your clipboard). Run it again any time to update.

    python3 install.py        (Windows: python install.py)
"""

import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

SCRIPT_URL = "https://raw.githubusercontent.com/prex-xo/war-brokers-discord-rpc/main/wb_rpc.py"
FLATPAK_STEAM = Path.home() / ".var/app/com.valvesoftware.Steam"


def install_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/wb-rpc"  # no spaces: Mac Steam launch options are fussy
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local") / "wb-rpc"
    if FLATPAK_STEAM.is_dir():
        # Flatpak Steam can only see its own folder, so the script has to live inside it
        return FLATPAK_STEAM / "data/wb-rpc"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share") / "wb-rpc"


def get_script() -> bytes:
    # Use the wb_rpc.py next to this installer if there is one, otherwise download it
    try:
        local = Path(__file__).resolve().with_name("wb_rpc.py")
        if local.is_file():
            print(f"Using {local}")
            return local.read_bytes()
    except NameError:  # run from a pipe, no __file__
        pass
    print(f"Downloading {SCRIPT_URL}")
    req = urllib.request.Request(SCRIPT_URL, headers={"User-Agent": "wb-rpc-installer"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def launch_option(script: Path) -> str:
    if sys.platform == "win32":
        # Full path to this Python, so it works whether or not python/pyw is on PATH
        return f'"{sys.executable}" "{script}" %command%'
    return f'"{script}" %command%'


def copy_to_clipboard(text: str) -> bool:
    if sys.platform == "darwin":
        commands = [["pbcopy"]]
    elif sys.platform == "win32":
        commands = [["clip"]]
    else:
        commands = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in commands:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-16-le" if cmd[0] == "clip" else "utf-8"),
                               check=True, timeout=5)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


def main() -> int:
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is needed.")
        return 1
    target_dir = install_dir()
    target = target_dir / "wb_rpc.py"
    try:
        data = get_script()
    except Exception as e:
        print(f"Couldn't get wb_rpc.py: {e}")
        return 1
    if b"class Discord" not in data:
        print("That doesn't look like wb_rpc.py, stopping.")
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if sys.platform != "win32":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installed {target}")

    option = launch_option(target)
    copied = copy_to_clipboard(option)
    print()
    print("Last step: in Steam, right-click War Brokers > Properties > Launch Options, and paste:")
    print()
    print(f"    {option}")
    print()
    print("(copied to your clipboard)" if copied else "(copy the line above)")
    print("Then press Play. Make sure the Discord desktop app is open.")
    if sys.platform.startswith("linux") and FLATPAK_STEAM.is_dir():
        print("\nFlatpak Steam detected: installed inside Steam's sandbox so it can run the script.")
    return 0


if __name__ == "__main__":
    code = main()
    if sys.platform == "win32" and sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close.")  # keep the window open when double-clicked
    sys.exit(code)
