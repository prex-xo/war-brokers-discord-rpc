#!/usr/bin/env python3
"""War Brokers (Steam) Discord Rich Presence.

Put this in the game's Steam launch options:

    "/path/to/wb_rpc.py" %command%

It starts the game, follows the game's Player.log to see which server, region
and map you're on, and shows it on Discord. It exits when the game closes.
Run it without arguments to watch an already-running game instead.

Standard library only, works on Python 3.9+.
"""

import json
from concurrent.futures import ThreadPoolExecutor
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

# Application ID from https://discord.com/developers/applications
# The application's name is what Discord shows as "Playing <name>".
CLIENT_ID = "1503338987899846816"

SERVER_LIST_URL = "https://store1.warbrokers.io/314/server_list.php?location={region}"
# Only set this if the script can't find the game's Player.log by itself.
# Example: "/home/you/.var/app/com.valvesoftware.Steam/.config/unity3d/Trebuchet Entertainment LLC/War_Brokers/Player.log"
# The WB_RPC_LOG environment variable does the same thing.
PLAYER_LOG_PATH = ""

REFRESH_SECONDS = 30  # how often player count / mode is re-checked in a match
TICK = 1.0

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "wb_rpc.log"

# Map and mode names: github.com/War-Brokers/War-Brokers (libs/wb-types)
MAP_NAMES = {
    0: "Desert", 1: "Northwest", 2: "Pacific", 3: "Office", 4: "Flooded",
    5: "Temple", 6: "Escape", 7: "Southwest", 8: "Remagen", 9: "Battle Royale",
    13: "City Point", 14: "Tomb", 15: "The Somme", 17: "Dead End City", 18: "Tribute",
    19: "Cyber Tribute", 20: "Moonbase", 21: "Area 15 Base", 22: "Area 15 Bunker",
    24: "Skull Island", 25: "Hangar", 27: "Quarry", 28: "Dwarf's Dungeon", 29: "Kitchen",
    30: "Test", 31: "Frontier", 32: "Heist", 33: "Tower of Power", 34: "Three Lane",
    35: "Sniper Alley", 36: "Pyramid", 37: "Containers", 38: "Space Station", 39: "Siege",
    40: "Criss Cross", 41: "Only Snipers", 43: "Zen Garden", 44: "Cologne",
    45: "Area 15 Base", 47: "Gold Mine", 48: "Resort", 49: "Gold Mine V2",
    50: "Area 15 V2", 51: "Desert Redux",
}

_WIKI = "https://static.wikia.nocookie.net/war-brokers/images/"
MAP_IMAGES = {
    0: "6/63/Desert_vote.png", 1: "c/cb/Northwest_vote.png", 2: "3/30/Pacific_vote.png",
    3: "3/32/Office_vote.png", 4: "e/ea/Flooded_vote.png", 5: "e/e9/Temple_vote.png",
    6: "1/1f/Escape_vote.png", 7: "e/e3/Southwest_vote.png", 8: "2/27/Remagen_vote.png",
    9: "c/c9/BattleRoyale_vote.png", 13: "b/b5/CityPoint_vote.png", 14: "c/cb/Tomb_vote.png",
    15: "c/c3/Somme_vote.png", 17: "7/76/DeadEndCity_vote.png", 18: "0/0f/Tribute_vote.png",
    19: "c/c7/TributeSilk_vote.png", 20: "0/0c/Moonbase_vote.png",
    21: "e/ef/Area15Base_vote.png", 22: "f/f9/Area15Bunker_vote.png",
    24: "5/53/SkullIsland_vote.png", 25: "9/92/Hangar_vote.png", 27: "5/55/Quarry_vote.png",
    28: "e/e0/DwarfDungeon_vote.png", 29: "3/31/Kitchen_vote.png", 30: "9/96/Test_map.png",
    31: "c/c0/Frontier_vote.png", 32: "6/6a/Heist_vote.png", 33: "4/4d/TowerOfPower_vote.png",
    34: "1/11/ThreeLanes_vote.png", 35: "8/8d/SniperAlley_vote.png",
    36: "d/d5/Pyramid_vote.png", 37: "e/e1/Containers_vote.png",
    38: "b/be/SpaceStation_vote.png", 39: "7/77/Siege_vote.png",
    40: "3/32/CrissCross_vote.png", 41: "1/1e/SnipersOnly_vote.png", 43: "b/bb/Zen_vote.png",
    44: "0/02/Cologne_vote.png", 47: "4/4f/GoldMine_vote.png", 48: "c/c6/Resort_vote.png",
    49: "6/6f/GoldMineV2_map.png", 50: "9/9f/Area15V2_map.png",
    51: "1/1f/DesertRedux_vote.png",
}

MODE_NAMES = {
    0: "Team Death Match", 1: "Demolition Derby", 2: "Protect Leader",
    3: "Resource Capture", 4: "Race", 5: "Tank Battle", 6: "Tank King",
    7: "Capture Point", 8: "Vehicle Escort", 9: "Package Drop",
    10: "Missile Launch", 11: "Battle Royale", 12: "Competitive",
    13: "Competitive Lobby", 14: "Battle Royale Lobby", 15: "Gun Game",
}

REGION_NAMES = {
    "USA": "USA East", "USA_WEST": "USA West", "EUROPE": "Europe", "ASIA": "Asia",
    "JAPAN": "Japan", "INDIA": "India", "AUSTRALIA": "Australia", "RUSSIA": "Russia",
    "USA_4V4": "USA 4v4", "EU_4V4": "Europe 4v4", "ASIA_4V4": "Asia 4v4",
    "NA_BATTLE_ROYALE": "NA Battle Royale", "EU_BATTLE_ROYALE": "Europe Battle Royale",
    "AS_BATTLE_ROYALE": "Asia Battle Royale", "AU_BATTLE_ROYALE": "Australia Battle Royale",
    "DEAD_CITY": "NA Dead City", "EU_DEAD_CITY": "Europe Dead City", "EU_DEAD": "Europe Dead City",
    "AS_DEAD_CITY": "Asia Dead City",
    "USA_CLAN": "USA East Clan", "USA_WEST_CLAN": "USA West Clan", "EUROPE_CLAN": "Europe Clan",
    "INDIA_CLAN": "India Clan", "AUSTRALIA_CLAN": "Australia Clan",
    "NA_COMPETITIVE": "NA Competitive", "NA_COMPETITIVE_TESTING": "NA Competitive (testing)",
}  # every region the server list accepts; all are searched to find your server

# Lines Unity writes to Player.log
RE_REGION = re.compile(r"^Setting last location to (\S+)")
RE_SERVER = re.compile(r"^openSocketAndConnect - wss://([^/\s]+)")
RE_SCENE = re.compile(r"^Loading scene (-?\d+)")
RE_MENU = "External Call: serverMenuOpen();"
RE_QUIT = "webguy.OnDestroy"


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


COMPANY = "Trebuchet Entertainment LLC"
_search_cache = {"at": -1e9, "found": None}


def _deep_search(home: Path) -> Optional[Path]:
    """Last resort: look for the publisher folder in the places Steam installs can put it
    (Flatpak, Snap, Steam's own folders). Depth-limited and throttled so it stays cheap."""
    if time.time() - _search_cache["at"] < 30:
        return _search_cache["found"]
    _search_cache["at"] = time.time()
    found = []
    for root in (".var", "snap", ".local/share", ".steam", ".config"):
        top = home / root
        if not top.is_dir():
            continue
        for dirpath, dirs, _files in os.walk(top, onerror=lambda e: None):
            depth = len(Path(dirpath).relative_to(top).parts)
            if COMPANY in dirs:
                found += (Path(dirpath) / COMPANY).glob("*/Player.log")
            if depth >= 8:
                dirs[:] = []
    _search_cache["found"] = max(found, key=lambda p: p.stat().st_mtime) if found else None
    return _search_cache["found"]


def player_log_path() -> Optional[Path]:
    """The game's Player.log: your own setting first, then the usual places per OS,
    then a limited search. Returns None if it can't be found (yet)."""
    manual = PLAYER_LOG_PATH or os.environ.get("WB_RPC_LOG", "")
    if manual:
        return Path(manual).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        bases = [home / "Library/Logs" / COMPANY]
    elif sys.platform == "win32":
        bases = [home / "AppData/LocalLow" / COMPANY]
    else:
        config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        bases = [config / "unity3d" / COMPANY,
                 home / ".config/unity3d" / COMPANY,
                 home / ".var/app/com.valvesoftware.Steam/.config/unity3d" / COMPANY,  # Flatpak Steam
                 home / "snap/steam/common/.config/unity3d" / COMPANY]                # Snap Steam
        # Windows build under Proton: native, Flatpak and Snap Steam folders
        for steam in (home / ".steam/steam", home / ".local/share/Steam",
                      home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
                      home / "snap/steam/common/.local/share/Steam"):
            bases.append(steam / "steamapps/compatdata/750470/pfx/drive_c/users/steamuser"
                                 "/AppData/LocalLow" / COMPANY)
    found = [p for base in bases for p in base.glob("*/Player.log")]
    if found:
        return max(found, key=lambda p: p.stat().st_mtime)
    return _deep_search(home) if sys.platform not in ("darwin", "win32") else None


# ── Discord IPC (https://discord.com/developers/docs/topics/rpc) ──────────────

class Discord:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.conn = None

    def _open(self):
        if sys.platform == "win32":
            for i in range(10):
                try:
                    return open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                except OSError:
                    continue
            return None
        dirs = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")]
        dirs = [d for d in dirs if d] + ["/tmp"]
        # Flatpak / snap Discord on Linux
        dirs += [os.path.join(d, sub) for d in dirs[:1] for sub in ("app/com.discordapp.Discord", "snap.discord")]
        for d in dirs:
            for i in range(10):
                path = os.path.join(d, f"discord-ipc-{i}")
                if not os.path.exists(path):
                    continue
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    s.connect(path)
                    return s.makefile("rwb", buffering=0)
                except OSError:
                    s.close()
        return None

    def _send(self, op: int, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        self.conn.write(struct.pack("<ii", op, len(data)) + data)
        header = self.conn.read(8)
        if len(header) < 8:
            raise ConnectionError("Discord closed the connection")
        _, length = struct.unpack("<ii", header)
        return json.loads(self.conn.read(length))

    def connect(self) -> bool:
        if self.conn:
            return True
        conn = self._open()
        if not conn:
            return False
        self.conn = conn
        try:
            reply = self._send(0, {"v": 1, "client_id": self.client_id})
            if reply.get("evt") != "READY":
                raise ConnectionError(reply.get("message") or reply)
            log("Connected to Discord")
            return True
        except Exception as e:
            log(f"Discord handshake failed: {e}")
            self.close()
            return False

    def set_activity(self, activity: Optional[dict]) -> bool:
        if not self.connect():
            return False
        try:
            reply = self._send(1, {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": str(uuid.uuid4()),
            })
            if reply.get("evt") == "ERROR":
                log(f"Discord rejected presence: {reply.get('data')}")
            return True
        except Exception as e:
            log(f"Lost Discord connection: {e}")
            self.close()
            return False

    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except OSError:
                pass
        self.conn = None


# ── War Brokers server list ──────────────────────────────────────────────────

def fetch_servers(region: str) -> list:
    """Parse "count,address,region,version,status,players,map,..." for one region."""
    url = SERVER_LIST_URL.format(region=region)
    req = urllib.request.Request(url, headers={"User-Agent": "wb-rpc-steam"})
    with urllib.request.urlopen(req, timeout=8) as r:
        entries = r.read().decode().strip().split(",")
    servers = []
    for i in range(int(entries[0])):
        address, sregion, _version, status, players, map_id = entries[6 * i + 1:6 * i + 7]
        servers.append({
            "ip": address.split(":")[0],
            "region": sregion,
            "mode": int(status) & 0b00111111,
            "closed": bool(int(status) & 0b01000000),  # match started, can't join
            "players": int(players),
            "map": int(map_id),
        })
    return servers


def _servers_with_ip(region: str, ip: str) -> list:
    try:
        return [s for s in fetch_servers(region) if s["ip"] == ip]
    except Exception as e:
        log(f"Server list for {region} failed: {e}")
        return []


def find_server(known: Optional[str], hint: Optional[str], ip: str,
                map_id: Optional[int]) -> Optional[dict]:
    """Find the server we're on.

    `known` is the region already confirmed for this connection; only that list is
    checked. Otherwise every region is searched, because the game's "last location"
    hint is just the region tab last picked (it said ASIA_4V4 on an EU_4V4 server),
    and clan servers share IPs with public ones. The hint only breaks ties."""
    if known:
        candidates = _servers_with_ip(known, ip)
    else:
        regions = list(REGION_NAMES) + ([hint] if hint and hint not in REGION_NAMES else [])
        with ThreadPoolExecutor(len(regions)) as pool:
            candidates = [s for found in pool.map(lambda r: _servers_with_ip(r, ip), regions) for s in found]
    if not candidates:
        return None
    # Several servers can share one IP; the map we loaded tells them apart.
    same_map = [s for s in candidates if s["map"] == map_id]
    server = max(same_map or candidates, key=lambda s: (s["region"] == hint, s["players"]))
    server["confirmed"] = bool(same_map)
    return server


def max_players(region: str, map_id: Optional[int]) -> int:
    if region.endswith("_4V4"):
        return 8
    if "BATTLE_ROYALE" in region or "DEAD" in region:
        return 60
    if map_id in (25, 27, 28):  # 2v2 maps
        return 4
    return 16


# ── Game state from Player.log ───────────────────────────────────────────────

class Game:
    def __init__(self):
        self.region: Optional[str] = None
        self.ip: Optional[str] = None
        self.map_id: Optional[int] = None
        self.in_match = False
        self.since = int(time.time())
        self.server: Optional[dict] = None
        self.known_region: Optional[str] = None  # confirmed for the current connection
        self.checked_at = 0.0

    def feed(self, line: str) -> bool:
        """Update state from one log line. Returns True if presence should change."""
        if m := RE_REGION.match(line):
            self.region = m.group(1)
        elif m := RE_SERVER.match(line):
            host = m.group(1).split(".")[0]
            self.ip = host.replace("-", ".") if host.count("-") == 3 else host
            self.known_region, self.server = None, None
            self.since = int(time.time())
            log(f"Joining {self.ip}")
        elif m := RE_SCENE.match(line):
            scene = int(m.group(1))
            if scene < 0:
                self.leave()
            else:
                self.map_id, self.in_match = scene, True
                self.checked_at = 0.0  # look up mode/players for the new map
                log(f"Map: {MAP_NAMES.get(scene, scene)}")
            return True
        elif line.startswith(RE_MENU):
            if self.in_match:
                self.leave()
                return True
        return False

    def leave(self):
        self.in_match, self.map_id, self.server = False, None, None
        self.since = int(time.time())
        log("In menu")

    def refresh(self) -> bool:
        """Re-check mode and player count. Returns True if they changed."""
        if not (self.in_match and self.ip):
            return False
        if time.time() - self.checked_at < REFRESH_SECONDS:
            return False
        self.checked_at = time.time()
        server = find_server(self.known_region, self.region, self.ip, self.map_id)
        if server is None and self.known_region:  # fall back to a full search
            server = find_server(None, self.region, self.ip, self.map_id)
        if server and server["confirmed"]:
            self.known_region = server["region"]
        changed = server != self.server
        self.server = server
        return changed

    def activity(self) -> dict:
        if not self.in_match:
            return {"details": "In menu", "timestamps": {"start": self.since},
                    "assets": {"large_image": _WIKI + MAP_IMAGES[33], "large_text": "War Brokers"}}
        map_name = MAP_NAMES.get(self.map_id, f"Map {self.map_id}")
        details = map_name
        state = None
        if self.server:
            region_id = self.server["region"]
            region = REGION_NAMES.get(region_id, region_id.replace("_", " ").title())
            mode = MODE_NAMES.get(self.server["mode"], f"Mode {self.server['mode']}")
            if self.server["mode"] == 11 and self.server["closed"]:
                mode = "Battle Royale (in progress)"
            details = mode if map_name in mode else f"{mode} • {map_name}"
            state = f"{region} • {self.server['players']}/{max_players(region_id, self.map_id)} players"
        activity = {"details": details, "timestamps": {"start": self.since}}
        if state:
            activity["state"] = state
        if self.map_id in MAP_IMAGES:
            activity["assets"] = {"large_image": _WIKI + MAP_IMAGES[self.map_id], "large_text": map_name}
        return activity


class LogFollower:
    """Yields new lines of Player.log; restarts from the top when the game recreates it."""

    def __init__(self, path: Path):
        self.path = path
        self.warned = False
        self.inode, self.pos = self._stat()
        self.partial = ""

    def _stat(self):
        if self.path is None:
            return None, 0
        try:
            st = self.path.stat()
            return st.st_ino, st.st_size
        except OSError:
            return None, 0

    def lines(self):
        inode, size = self._stat()
        if inode is None:
            self.path = player_log_path()  # the log may appear later, or somewhere else
            if self.path is None or not self.path.exists():
                if not self.warned:
                    self.warned = True
                    log("Can't find the game's Player.log yet. If it never appears, set "
                        "PLAYER_LOG_PATH at the top of wb_rpc.py (see the README).")
                return []
            self.warned = False
            log(f"Found log: {self.path}")
            self.inode, self.pos = None, 0  # read it from the start
            inode, size = self._stat()
            if inode is None:
                return []
        if inode != self.inode or size < self.pos:
            self.inode, self.pos, self.partial = inode, 0, ""
        if size == self.pos:
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self.pos)
            chunk = f.read()
            self.pos = f.tell()
        text = self.partial + chunk
        *done, self.partial = text.split("\n")
        return [line.rstrip("\r") for line in done]


def resolve_app(cmd: list) -> list:
    """macOS Steam passes the .app bundle. Open it through Launch Services like a
    normal app (so macOS gives it foreground priority and Game Mode) and wait for it."""
    app = Path(cmd[0])
    if sys.platform == "darwin" and app.suffix == ".app" and app.is_dir():
        env = [arg for k, v in os.environ.items()
               if k.startswith(("Steam", "SteamApp", "DYLD_")) for arg in ("--env", f"{k}={v}")]
        return ["/usr/bin/open", "-W", "-n", *env, str(app), *(["--args", *cmd[1:]] if cmd[1:] else [])]
    return cmd


def main() -> int:
    global LOG_FILE
    log_path = player_log_path()
    # Keep wb_rpc.log with the game's own logs, not next to the script (e.g. Downloads)
    if log_path and log_path.parent.parent.name == COMPANY and log_path.parent.parent.is_dir():
        LOG_FILE = log_path.parent.parent / "wb_rpc.log"
    try:
        LOG_FILE.write_text("", encoding="utf-8")
    except OSError:
        LOG_FILE = HERE / "wb_rpc.log"
        LOG_FILE.write_text("", encoding="utf-8")
    game_cmd = resolve_app(sys.argv[1:]) if sys.argv[1:] else []
    follower = LogFollower(log_path)  # remember the old log before the game replaces it

    proc = None
    if game_cmd:
        log(f"Starting game: {' '.join(game_cmd)}")
        proc = subprocess.Popen(game_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        log(f"Watching {log_path or 'for Player.log'} (Ctrl+C to stop)")

    if CLIENT_ID.startswith("PUT_"):
        log("Set CLIENT_ID in wb_rpc.py to your Discord application ID. Presence is off.")
        return proc.wait() if proc else 1

    discord = Discord(CLIENT_ID)
    game = Game()
    shown = None
    last_try = 0.0

    try:
        while proc is None or proc.poll() is None:
            for line in follower.lines():
                if line.startswith(RE_QUIT):
                    log("Game closed")
                    if proc is None:
                        discord.set_activity(None)
                        game, shown = Game(), None
                    continue
                game.feed(line)
            game.refresh()

            activity = game.activity() if (proc or game.ip) else None
            # Retry Discord every 15s if it wasn't open yet
            if activity != shown and (discord.conn or time.time() - last_try > 15):
                last_try = time.time()
                if discord.set_activity(activity):
                    shown = activity
                    if activity:
                        log(f"Presence: {activity['details']} | {activity.get('state', '')}")
            time.sleep(TICK)
    except KeyboardInterrupt:
        pass
    finally:
        discord.set_activity(None)
        discord.close()
    return proc.returncode if proc else 0


if __name__ == "__main__":
    sys.exit(main())
