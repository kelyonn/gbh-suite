
# The Grand Budapest Hotel (GBH) Suite

**"I just wanted to clean my Downloads folder... and then I accidentally built a hotel."**

The **GBH Suite** is a modular automation system for macOS that manages the entire lifecycle of a local development environment. What started as a single script to optimize file sorting evolved into a complete architecture of background services, treating the operating system like a hotel that requires a dedicated staff to run efficiently.

---

## The Story

This project began with a simple irritation: I was wasting time manually dragging files from `~/Downloads` to `~/Documents`. I wrote a script to automate it.

But once you optimize one thing, you start seeing inefficiencies everywhere.
* Why am I manually deleting screenshots every week?
* Why do I stare at the terminal waiting for `localhost:3000` to start?
* Why do I type `git status` twenty times a day?

The script grew. It needed to handle concurrency. It needed to handle system resources. It needed a name. The *Grand Budapest Hotel* theme wasn't the goal—it was the answer. To manage a complex system invisibly and elegantly, you don't need a script; you need a **Concierge**, a **Butler**, and a **Lobby Boy**.

---

## The Staff (Architecture)

The suite is split into five distinct Python modules. Each "Staff Member" owns a specific domain of the OS, coordinated by a central "Reception Desk" (`main.py`).

### 1. Gustave (The Concierge)
**Domain:** System Health & Status.
* **The Problem:** Opening a terminal and not knowing the state of the machine (Disk space, active Docker containers, dirty git repos).
* **The Solution:** Gustave runs immediately upon login. He aggregates data from `psutil`, `docker`, and `git`, providing a "Morning Briefing" via a native macOS notification. He tells me if the system is ready for work or if it needs attention.

### 2. Serge (The Butler)
**Domain:** File Organization.
* **The Problem:** The `~/Downloads` folder is a chaotic dumping ground.
* **The Solution:** A background daemon using `watchdog` to monitor filesystem events. Serge watches the door. As soon as a file enters, he inspects the extension and escorts it to its proper room (`/Images`, `/Docs`, `/Projects`). He even handles naming collisions automatically.

### 3. Zero (The Lobby Boy)
**Domain:** Routine Maintenance & Optimization.
* **The Problem:** Digital clutter accumulates silently (old screenshots, duplicate files).
* **The Solution:**
    * **Daily Sweep:** Zero wakes up once a day to trash screenshots older than 24 hours.
    * **Duplicate Hunter:** When summoned, Zero performs a **3-Stage Filter** (Size → Header Hash → Full Hash) to identify duplicate files with O(n) efficiency, allowing for interactive cleanup.

### 4. Dimitri (The Sentinel)
**Domain:** Monitoring & Alerts.
* **The Problem:** "Context switching" penalty. Waiting for a server to boot or a build to finish breaks flow.
* **The Solution:** Dimitri is a background thread manager.
    * **The Waiter:** `gbh wait 8000` polls a local port and notifies me the second it responds.
    * **The Patrol:** Reads a `config` file on startup and silently monitors critical ports, pinging me when my dev environment is fully online.

### 5. Agatha (The Baker)
**Domain:** Archiving & Disaster Recovery.
* **The Problem:** Project folders are massive (thank you, `node_modules`) and hard to archive.
* **The Solution:** Agatha wraps projects in "Mendl's Boxes" (Zip archives). She parses the directory tree and actively strips out heavy dependencies (`venv`, `.git`, `node_modules`) before zipping, turning 500MB folders into 2MB backups.

---

## Installation

### 1. Setup
```bash
# 1. Clone the repository
git clone [https://github.com/yourusername/gbh-suite.git](https://github.com/yourusername/gbh-suite.git)
cd gbh-suite

# 2. Create Virtual Environment (Essential for dependency isolation)
python3 -m venv venv
source venv/bin/activate

# 3. Install Dependencies
pip install -r requirements.txt

```

### 2. Shell Configuration

Add this alias to your `~/.zshrc` or `~/.bashrc` to call the Reception Desk from anywhere:

```bash
alias gbh='/path/to/gbh-suite/venv/bin/python3 /path/to/gbh-suite/main.py'

```

---

## Command Reference

Once the alias is set, you have full control over the hotel staff.

### 🔍 System & Status

| Command | Staff Member | Description |
| --- | --- | --- |
| `gbh status` | **Gustave** | Displays the full colored System Health Dashboard in the terminal. |
| `gbh status --notify` | **Gustave** | Sends a silent, one-line summary via macOS Notification (Best for startup). |

### Cleaning & Organization

| Command | Staff Member | Description |
| --- | --- | --- |
| `gbh sort` | **Serge** | Manually starts the File Sorter (if not running in background). |
| `gbh clean` | **Zero** | Sweeps Desktop screenshots older than 24 hours to Trash. |
| `gbh clean --dupes` | **Zero** | Scans `~/Downloads` for duplicate files. |
| `gbh clean --dupes <path>` | **Zero** | Scans a specific folder (e.g., `~/Pictures`) for duplicates. |

### Monitoring & Alerts

| Command | Staff Member | Description |
| --- | --- | --- |
| `gbh wait <port>` | **Dimitri** | Blocks terminal until `localhost:<port>` is live (e.g., `gbh wait 3000`). |
| `gbh wait <port> --bg` | **Dimitri** | Runs in background. Notifies you when the port is live so you can keep working. |
| `gbh watch <file>` | **Dimitri** | Tails a log file. Notifies you if "Error" or "Exception" appears. |
| `gbh patrol` | **Dimitri** | Reads `config.py` and starts monitoring all permanent ports/logs. |
| `gbh stop` | **All** | Kills all background watchers (Dimitri instances). |

### Backup & Archiving

| Command | Staff Member | Description |
| --- | --- | --- |
| `gbh pack .` | **Agatha** | Archives current folder to `~/Documents/Archives` (skipping `node_modules`). |
| `gbh pack <path>` | **Agatha** | Archives a specific folder. |
| `gbh backup` | **Agatha** | Backs up `.zshrc`, `.ssh/config`, and git configs to `~/Documents/Backups`. |

---

## Automation (LaunchAgents)

The suite is designed to run automatically using macOS `launchd`.

**1. Startup Notification (Gustave)**
Runs at login to give a system health check.

```bash
launchctl load ~/Library/LaunchAgents/com.kalyan.gbh.gustave.plist

```

**2. Background Sorter (Serge)**
Runs continuously to organize Downloads.

```bash
launchctl load ~/Library/LaunchAgents/com.kalyan.gbh.serge.plist

```

**3. Startup Patrol (Dimitri)**
Reads `config.py` and watches your favorite ports/logs silently.

```bash
launchctl load ~/Library/LaunchAgents/com.kalyan.gbh.dimitri.plist

```

---

## Tech Stack

* **Python 3** (Core Logic)
* **Watchdog** (Filesystem Event Monitoring)
* **Psutil** (System Resource Management)
* **Subprocess** (Shell Integration & Git Commands)
* **Hashlib** (Data Integrity & Duplicate Detection)
* **Launchd** (macOS Daemon Management)

```

```
