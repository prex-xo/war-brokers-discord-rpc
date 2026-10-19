#!/usr/bin/env python3
"""Installer for War Brokers Discord Rich Presence.

1. Puts wb_rpc.py in the game's own "Trebuchet Entertainment LLC" folder.
2. Sets the War Brokers launch option in Steam (Steam has to be closed;
   the settings file is backed up first). If that can't be done, it prints
   the line to paste instead and copies it to your clipboard.

Run it again any time to update.

    python3 install.py        (Windows: python install.py)
    python3 install.py --no-steam    only install, don't touch Steam settings
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


COMPANY = "Trebuchet Entertainment LLC"
APP_ID = "750470"


def install_dir() -> Path:
    """The game's own data folder, so the script isn't deleted by accident."""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library/Logs"
    elif sys.platform == "win32":
        base = home / "AppData/LocalLow"
    elif FLATPAK_STEAM.is_dir():
        # Flatpak Steam can only see its own folder, so the script has to live inside it
        base = FLATPAK_STEAM / ".config/unity3d"
    elif (home / "snap/steam").is_dir():
        base = home / "snap/steam/common/.config/unity3d"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "unity3d"
    return base / COMPANY / "wb-rpc"


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


# ── Steam text VDF (KeyValues) ───────────────────────────────────────────────
# A node is a list of [key, value] pairs; value is a str or another node.

def vdf_parse(text: str) -> list:
    pos, n = 0, len(text)

    def skip():
        nonlocal pos
        while pos < n:
            if text[pos] in " \t\r\n":
                pos += 1
            elif text.startswith("//", pos):
                pos = text.find("\n", pos)
                pos = n if pos < 0 else pos
            else:
                break

    def string() -> str:
        nonlocal pos
        if text[pos] != '"':
            raise ValueError(f"expected a quote at {pos}")
        pos += 1
        out = []
        while text[pos] != '"':
            if text[pos] == "\\" and text[pos + 1] in '"\\':  # Steam only escapes \" and \\
                out.append(text[pos + 1])
                pos += 2
            else:
                out.append(text[pos])
                pos += 1
        pos += 1
        return "".join(out)

    def block(top: bool) -> list:
        nonlocal pos
        node = []
        while True:
            skip()
            if pos >= n:
                if top:
                    return node
                raise ValueError("unexpected end of file")
            if text[pos] == "}":
                if top:
                    raise ValueError(f"unexpected }} at {pos}")
                pos += 1
                return node
            key = string()
            skip()
            if text[pos] == "{":
                pos += 1
                node.append([key, block(False)])
            else:
                node.append([key, string()])

    return block(True)


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def vdf_dump(node: list, depth: int = 0) -> str:
    tabs = "\t" * depth
    out = []
    for key, value in node:
        if isinstance(value, list):
            out.append(f"{tabs}{_q(key)}\n{tabs}{{\n{vdf_dump(value, depth + 1)}{tabs}}}\n")
        else:
            out.append(f"{tabs}{_q(key)}\t\t{_q(value)}\n")
    return "".join(out)


def _get(node: list, key: str):
    for k, v in node:
        if k.lower() == key.lower():
            return v
    return None


def _get_or_add(node: list, key: str) -> list:
    child = _get(node, key)
    if not isinstance(child, list):
        child = []
        node.append([key, child])
    return child


# ── Steam settings ───────────────────────────────────────────────────────────

def steam_roots() -> list:
    home = Path.home()
    if sys.platform == "darwin":
        roots = [home / "Library/Application Support/Steam"]
    elif sys.platform == "win32":
        roots = []
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
        roots += [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"]
    else:
        roots = [home / ".steam/steam", home / ".local/share/Steam",
                 FLATPAK_STEAM / ".local/share/Steam", FLATPAK_STEAM / "data/Steam",
                 home / "snap/steam/common/.local/share/Steam"]
    seen, out = set(), []
    for r in roots:
        if (r / "userdata").is_dir() and r.resolve() not in seen:
            seen.add(r.resolve())
            out.append(r)
    return out


def steam_running() -> bool:
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                                 capture_output=True, text=True, timeout=10).stdout
            return "steam.exe" in out.lower()
        names = ["steam_osx"] if sys.platform == "darwin" else ["steam", "steamwebhelper"]
        return any(subprocess.run(["pgrep", "-x", n], capture_output=True, timeout=10).returncode == 0
                   for n in names)
    except (OSError, subprocess.SubprocessError):
        return False  # can't tell; the backup still protects the file


def recent_account(root: Path):
    """Account ID of the most recently signed-in Steam user, if known."""
    try:
        users = _get(vdf_parse((root / "config/loginusers.vdf").read_text(encoding="utf-8")), "users") or []
    except (OSError, ValueError):
        return None
    best = None
    for steam_id, info in users:
        if not isinstance(info, list) or not steam_id.isdigit():
            continue
        rank = (_get(info, "MostRecent") == "1", int(_get(info, "Timestamp") or 0))
        if best is None or rank > best[0]:
            best = (rank, str(int(steam_id) - 76561197960265728))
    return best[1] if best else None


def target_configs(root: Path) -> list:
    """localconfig.vdf of every account that already has War Brokers settings,
    plus the most recently signed-in account."""
    recent = recent_account(root)
    found = []
    for cfg in sorted((root / "userdata").glob("*/config/localconfig.vdf")):
        account = cfg.parent.parent.name
        try:
            data = vdf_parse(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        apps = _get(_get(_get(_get(_get(data, "UserLocalConfigStore") or [], "Software") or [],
                                 "Valve") or [], "Steam") or [], "apps")
        has_game = isinstance(apps, list) and _get(apps, APP_ID) is not None
        if has_game or account == recent:
            found.append(cfg)
    return found


def set_launch_option(cfg: Path, option: str, ask) -> str:
    """Returns "set", "same" or "skipped"."""
    raw = cfg.read_text(encoding="utf-8")
    data = vdf_parse(raw)
    if vdf_dump(data) != raw:
        return "skipped"  # unexpected format: don't risk rewriting it
    node = data
    for key in ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps", APP_ID):
        node = _get_or_add(node, key)
    current = _get(node, "LaunchOptions")
    if current == option:
        return "same"
    if current and "wb_rpc.py" not in current:
        if not ask(f"War Brokers already has launch options:\n    {current}\nReplace them? [y/N] "):
            return "skipped"
    if current is None:
        node.append(["LaunchOptions", option])
    else:
        next(p for p in node if p[0] == "LaunchOptions")[1] = option
    backup = cfg.with_name("localconfig.vdf.wb-rpc-backup")
    if not backup.exists():
        shutil.copy2(cfg, backup)
    text = vdf_dump(data)
    vdf_parse(text)  # sanity check before writing
    tmp = cfg.with_name("localconfig.vdf.wb-rpc-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cfg)
    return "set"


def ask_user(prompt: str) -> bool:
    if not (sys.stdin and sys.stdin.isatty()):
        return False
    return input(prompt).strip().lower() in ("y", "yes")


def configure_steam(option: str) -> bool:
    roots = steam_roots()
    if not roots:
        print("Couldn't find Steam's settings folder.")
        return False
    while steam_running():
        if not (sys.stdin and sys.stdin.isatty()):
            print("Steam is open, so its settings can't be changed now.")
            return False
        answer = input("Steam is open. Quit Steam fully (Steam menu > Exit/Quit), then press Enter.\n"
                       "Or type s and Enter to skip and paste the launch option yourself: ")
        if answer.strip().lower() == "s":
            return False
    changed = False
    for root in roots:
        for cfg in target_configs(root):
            try:
                result = set_launch_option(cfg, option, ask_user)
            except (OSError, ValueError) as e:
                print(f"Couldn't update {cfg}: {e}")
                continue
            print(f"Steam account {cfg.parent.parent.name}: launch option {'already set' if result == 'same' else result}")
            changed |= result in ("set", "same")
    return changed


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
    print()
    if "--no-steam" not in sys.argv and configure_steam(option):
        print("\nDone. Open Steam and press Play on War Brokers (keep the Discord desktop app open).")
        print(f"Launch option set to:\n    {option}")
    else:
        copied = copy_to_clipboard(option)
        print("\nLast step: in Steam, right-click War Brokers > Properties > Launch Options, and paste:")
        print(f"\n    {option}\n")
        print("(copied to your clipboard)" if copied else "(copy the line above)")
        print("Then press Play. Keep the Discord desktop app open.")
    if sys.platform.startswith("linux") and FLATPAK_STEAM.is_dir():
        print("\nFlatpak Steam detected: installed inside Steam's sandbox so it can run the script.")
    return 0


if __name__ == "__main__":
    code = main()
    if sys.platform == "win32" and sys.stdin and sys.stdin.isatty():
        input("\nPress Enter to close.")  # keep the window open when double-clicked
    sys.exit(code)
