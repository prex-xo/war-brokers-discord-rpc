# War Brokers Discord Rich Presence (Steam)

Show your War Brokers match on your Discord profile: game mode, map (with the map picture), region, player count and time played.

![War Brokers Rich Presence on a Discord profile](images/discord-presence.png)

Between matches it shows **In menu**, and it clears when you quit the game.

- One file, standard-library Python only. Nothing to `pip install`.
- Starts and stops with the game through Steam launch options.
- No browser extension, no userscript, no server, no account.
- Read-only: it reads the game's log file. It doesn't touch game memory, files or network traffic.

## Platforms
| | Status |
|---|---|
| macOS | Tested |
| Windows | Should work, not tested yet |
| Linux (native or Proton) | Should work, not tested yet |

Reports from Windows and Linux players are welcome.

## Supported servers
Every region on the War Brokers server list:

| Type | Regions |
|---|---|
| Classic | USA East, USA West, Europe, Asia, Japan, India, Australia, Russia |
| 4v4 | USA, Europe, Asia |
| Battle Royale | NA, Europe, Asia, Australia (shows lobby / in progress) |
| Dead City | NA, Europe, Asia |
| Clan | USA East, USA West, Europe, India, Australia |
| Competitive | NA |

## Requirements
- War Brokers on Steam
- Discord desktop app, running
- Python 3.9 or newer
  - macOS: already installed (`/usr/bin/python3`). If it asks to install developer tools, accept.
  - Windows: install from [python.org](https://www.python.org/downloads/)

## Install

1. Download `wb_rpc.py` and put it somewhere it will stay.
2. macOS / Linux only: make it runnable once:
   ```bash
   chmod +x ~/Games/wb_rpc.py
   ```
3. In Steam, right-click **War Brokers** → **Properties** → **Launch Options**, and paste:

   **macOS / Linux**
   ```
   "/Users/YOUR_NAME/Games/wb_rpc.py" %command%
   ```
   **Windows**
   ```
   pyw "C:\Games\wb_rpc.py" %command%
   ```
   `pyw` comes with the python.org installer and runs the script without a console window.
   Use the real path to where you saved the file. On macOS the line must start with the file path, not `python3`; otherwise Steam fails with *OS Error 260*.
4. Press **Play**.

To remove it, clear the launch options.

### Without launch options
Start the game normally, then run:
```bash
python3 wb_rpc.py
```
It watches the running game until you press Ctrl+C.

## How it works
Unity writes the game's log to `Player.log`. The script follows that file:

| Log line | Meaning |
|---|---|
| `Setting last location to ASIA_4V4` | last region tab picked (only a hint; the real region is found by IP) |
| `openSocketAndConnect - wss://45-32-31-106.warbrokers.io/...` | server IP |
| `Loading scene 33` | map (`-1` = left the match) |
| `External Call: serverMenuOpen();` | back in the menu |
| `webguy.OnDestroy` | game closed |

Region, game mode and player count come from the public War Brokers server list:

- **On each server join**, every region is searched for the server's IP. The game's "last location" line is not trusted, because it's only the region tab you last picked (it can say `ASIA_4V4` while you're on an EU server).
- **Several servers can share an IP** (for example a clan server and a public server), so it picks the one running the map you loaded. The region tab is only used to break a tie.
- **Once confirmed**, only that one region is re-checked every 30 seconds for player count and mode. Joining another server starts a fresh search.

Log locations:
- macOS: `~/Library/Logs/Trebuchet Entertainment LLC/War_Brokers/Player.log`
- Windows: `%USERPROFILE%\AppData\LocalLow\Trebuchet Entertainment LLC\War_Brokers\Player.log`
- Linux: `~/.config/unity3d/Trebuchet Entertainment LLC/War_Brokers/Player.log`
- Linux with Proton: inside `steamapps/compatdata/750470/pfx/drive_c/users/steamuser/AppData/LocalLow/...`

The script searches these automatically and uses the newest log.

## Troubleshooting
- **Nothing on Discord:** Discord must be the desktop app and already open. Check *Settings → Activity Privacy → Share your detected activities* is on.
- **Debug output:** see `wb_rpc.log` next to the script. It's recreated on every launch. It includes your Steam username, so check it before posting it in an issue.
- **Player count shows 0, or no region for a moment:** the server list updates a few seconds behind the game; it corrects itself on the next check (up to 30 seconds).
- **Clan server shown as the public region:** a clan server and a public server can share an IP. If both are on the same map, the script can't tell them apart and follows the region tab you picked.
- **Linux, Discord installed as Flatpak or Snap:** the script looks for Discord's socket in those locations too; if it still can't connect, check `wb_rpc.log`.

## Using your own Discord application
The script ships with a Discord application ID named "War Brokers". Application IDs aren't secret. To use your own, create one at <https://discord.com/developers/applications> and put its **Application ID** in `CLIENT_ID` at the top of `wb_rpc.py`. The application's name is what Discord shows after "Playing".

## Credits
- Map and mode names: [War-Brokers/War-Brokers](https://github.com/War-Brokers/War-Brokers) (`libs/wb-types`)
- Map pictures: [War Brokers Wiki](https://war-brokers.fandom.com)

Not affiliated with Trebuchet Entertainment or War Brokers.

## License
MIT
