# 🏨 Grand Budapest Hotel Suite

> *"There are still faint glimmers of civilization left in this barbaric slaughterhouse that was once known as humanity."*
> — M. Gustave H.

The Grand Budapest Hotel once stood as the finest establishment in all of Zubrowka. It ran on precision, discretion, and an unwavering commitment to the guest experience — not because anyone was watching, but because that was simply the standard.

This suite borrows its staff from that world. Each tool is a character. Each character has a role. None of them ask for your attention unless something has gone wrong. They simply work — silently, in the background, around the clock — so you don't have to think about it.

---

## The Staff

*The hotel does not run itself. Behind every smooth experience is a cast of people who never sleep.*

| Character | Their Story | Their Job | When |
|---|---|---|---|
| **M. Gustave** | The legendary concierge. Knows everything about the state of the hotel before the guests wake up. | Morning briefing — vitals, git, ports | Login + every terminal |
| **Serge X.** | The butler. Meticulous, fast, and completely silent. Everything in its place before you notice it wasn't. | File sorter — Downloads & Desktop | Always on |
| **Dimitri** | He keeps watch. Nothing moves through the hotel without him knowing. | Port & log sentinel | Always on |
| **Zero** | The lobby boy. Keeps the corridors spotless. Sweeps what others leave behind. | Screenshot & cleanup crew | Scheduled |
| **Ivan** | Dimitri's enforcer. When you need the world to go quiet, Ivan makes it happen. | Focus mode — blocks distracting sites | On demand |
| **Jopling** | The assassin. Silent. Precise. Appears only when something has gone badly wrong. | CPU & RAM runaway enforcer | Always on |
| **Henckels** | The inspector. Watching the network, the exits, every unfamiliar face at the door. | Network & WiFi sentinel | Always on |
| **Kovacs** | The lawyer. Every evening, he reviews the books. Uncommitted work does not go unnoticed. | Evening git compliance report | Daily 8pm |
| **Clotilde** | The maid. Works through the night. By morning, every cache is clear, every trace gone. | Cache sweeper | Daily 3am |
| **Ludwig** | The general. Once a week, a full inspection of the premises. Nothing escapes his report. | Weekly system audit | Sundays 10am |
| **Agatha** | She kept the secret, and she kept it safe. Your configs and projects, preserved faithfully. | Project archiver & dotfile backup | On demand |

---



## Install

```bash
bash installer.sh
source ~/.zshrc
```

That's it. All agents are registered as LaunchAgents and start immediately.

**Requirements:** macOS, Homebrew, Python 3.11 (`brew install python@3.11`)

---

## Usage

```bash
gbh                        # Full morning briefing (Gustave)
gbh compact                # One-line status (auto-runs on every new terminal)
```

### Serge — File Sorter
Automatically moves files dropped in `~/Downloads` or `~/Desktop` into subfolders:

| Extension | Destination |
|---|---|
| `.jpg .png .heic .webp …` | `Images/` |
| `.pdf .doc .txt .csv …` | `Documents/` |
| `.mp3 .wav .flac …` | `Audio/` |
| `.mp4 .mkv .mov …` | `Video/` |
| `.zip .dmg .iso …` | `Archives/` |
| `.py .js .go .sh …` | `~/Documents/Projects/` |
| anything else | `Others/` |

```bash
gbh undo [n]               # Undo last N Serge moves
```

### Zero — Cleanup
```bash
gbh clean                  # Sweep old screenshots
gbh clean --old [days]     # Archive Downloads older than N days
gbh clean --dupes [dir]    # Find & remove duplicate files (interactive)
gbh large [dir]            # Find files over 500MB
```

### Ivan — Focus Mode
```bash
gbh focus [minutes]        # Block distracting sites (default: 25 min)
gbh focus pause            # Pause — unblock sites, freeze the timer
gbh focus resume           # Resume — re-block sites, continue with remaining time
gbh focus stop             # End session early
gbh focus status           # Show active/paused state and time remaining
gbh focus pomodoro [n]     # Run N Pomodoro cycles (25m focus / 5m break)
```

Sites blocked during focus are defined in `config.py` under `FOCUS_BLOCKLIST`.
Pause/Resume is also available in the dashboard at `http://127.0.0.1:2525`.

> Ivan uses a scoped passwordless sudo rule for `/etc/hosts`. Run `bash installer.sh`
> and accept the prompt to install it once. Revoke at any time:
> `sudo rm /etc/sudoers.d/gbh-ivan`

### Agatha — Archiver
```bash
gbh pack [path]            # Zip a project (respects .gbhignore)
gbh backup                 # Snapshot dotfiles to ~/.gbh/backups/
gbh restore [snapshot]     # Restore a dotfile snapshot
```

### Dimitri — Sentinel
```bash
gbh patrol                 # Start manually (auto-started by launchd)
gbh wait <port>            # Notify when a port opens
gbh watch <file>           # Watch a log file for errors
```

### Dashboard
```bash
gbh open                   # Open web dashboard at http://127.0.0.1:2525
```

The dashboard shows live CPU, RAM, disk, battery, staff status, Serge move feed, and Ivan focus controls — updated every 0.5s via WebSocket.

---

## Configuration

All settings live in `config.py`:

```python
SERGE_WATCH_DIRS        # Folders Serge monitors
SERGE_DESTINATIONS      # Extension → category mapping
FOCUS_BLOCKLIST         # Domains Ivan blocks
CRITICAL_PORTS          # Ports Dimitri watches
DOTFILES_TO_BACKUP      # Files Agatha backs up
LARGE_FILE_THRESHOLD_MB # Zero large-file scan threshold
TRASH_WARN_GB           # Zero trash size warning
```

---

## Notifications

All notifications use [`terminal-notifier`](https://github.com/julienXX/terminal-notifier) — they appear as proper macOS notifications attributed to each character, never Script Editor. Each staff member has a distinct sound.

Notifications are grouped per character in Notification Centre so they don't pile up.

---

## Project Structure

```
gbh/
├── main.py               # CLI entry point — gbh <command>
├── server.py             # FastAPI dashboard server (port 2525)
├── config.py             # All paths, thresholds, and lists
├── installer.sh          # One-shot setup script
├── staff/
│   ├── notify.py         # Shared notification layer (terminal-notifier)
│   ├── serge.py          # File sorter
│   ├── dimitri.py        # Port/log/process sentinel
│   ├── gustave.py        # Morning briefing
│   ├── zero.py           # Cleanup crew
│   ├── ivan.py           # Focus mode
│   ├── jopling.py        # Process enforcer
│   ├── henckels.py       # Network sentinel
│   ├── kovacs.py         # Git compliance
│   ├── clotilde.py       # Cache sweeper
│   ├── ludwig.py         # Weekly inspector
│   └── agatha.py         # Archiver
├── launchagents/         # Plist files (symlinked to ~/Library/LaunchAgents)
└── templates/
    └── dashboard.html    # Web dashboard
```

---

## Runtime Data

Everything lives in `~/.gbh/`:

```
~/.gbh/
├── serge_moves.jsonl     # All Serge moves (used for undo)
├── focus_state.json      # Active Ivan focus session
├── known_networks.txt    # Henckels trusted WiFi networks
├── backups/              # Agatha dotfile snapshots
└── *_last_run.txt        # Timestamps for scheduled agents
```

---

## Stopping & Restarting

```bash
gbh stop                  # Kill Serge + Dimitri background processes
bash installer.sh         # Re-install and restart everything
```

Individual agents:
```bash
launchctl unload ~/Library/LaunchAgents/com.kalyan.gbh.serge.plist
launchctl load   ~/Library/LaunchAgents/com.kalyan.gbh.serge.plist
```

Logs:
```bash
tail -f /tmp/gbh_serge.out
tail -f /tmp/gbh_dimitri.out
tail -f /tmp/gbh_server.err
```
