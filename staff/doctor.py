"""
Doctor — GBH system health check.
Run with: gbh doctor

Checks every moving part of the suite and prints a clear report with
suggested fix commands for anything that looks wrong.
"""

import shutil
import socket
import subprocess
import sys
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GBH_DATA    = Path.home() / ".gbh"
LAUNCH_AGENTS_DIR = Path.home() / "Library/LaunchAgents"

# plist label → friendly name → expected cmdline substring
DAEMONS = {
    "com.kalyan.gbh.serge":    ("Serge",    "main.py sort"),
    "com.kalyan.gbh.dimitri":  ("Dimitri",  "main.py patrol"),
    "com.kalyan.gbh.jopling":  ("Jopling",  "main.py jopling"),
    "com.kalyan.gbh.henckels": ("Henckels", "main.py henckels"),
    "com.kalyan.gbh.server":   ("Server",   "uvicorn server:app"),
}

# ── ANSI helpers ──────────────────────────────────────────────────

_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED   = "\033[31m"
_GOLD  = "\033[33m"
_DIM   = "\033[2m"
_BOLD  = "\033[1m"

def _ok(msg: str)   -> str: return f"{_GREEN}✅{_RESET}  {msg}"
def _err(msg: str)  -> str: return f"{_RED}❌{_RESET}  {msg}"
def _warn(msg: str) -> str: return f"{_GOLD}⚠️ {_RESET}  {msg}"
def _fix(cmd: str)  -> str: return f"   {_DIM}→ {cmd}{_RESET}"
def _hr()           -> str: return _DIM + "─" * 50 + _RESET


# ── Individual checks ────────────────────────────────────────────

def _loaded_labels() -> set[str]:
    """Return the set of launchctl labels currently loaded for this user."""
    try:
        r = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=5,
        )
        return {line.split()[-1] for line in r.stdout.splitlines() if "com.kalyan.gbh" in line}
    except Exception:
        return set()


def _running_cmdlines() -> list[str]:
    """Return all process cmdlines for the current user."""
    lines = []
    for p in psutil.process_iter(["cmdline", "uids"]):
        try:
            import os
            if p.uids().real == os.getuid():
                lines.append(" ".join(p.info.get("cmdline") or []))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return lines


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def check_daemons() -> list[str]:
    lines: list[str] = []
    loaded  = _loaded_labels()
    running = _running_cmdlines()

    for label, (name, cmdline_substr) in DAEMONS.items():
        plist = LAUNCH_AGENTS_DIR / f"{label}.plist"
        is_loaded  = label in loaded
        is_running = any(cmdline_substr in c for c in running)

        if is_running:
            lines.append(_ok(f"{name}"))
        elif is_loaded:
            lines.append(_warn(f"{name} — loaded but not running"))
            lines.append(_fix(f"launchctl kickstart -k gui/$UID/{label}"))
        elif plist.exists():
            lines.append(_err(f"{name} — not loaded"))
            lines.append(_fix(f"launchctl bootstrap gui/$UID {plist}"))
        else:
            lines.append(_err(f"{name} — plist missing ({plist.name})"))
            lines.append(_fix("bash installer.sh"))

    return lines


def check_dashboard() -> list[str]:
    server_plist = LAUNCH_AGENTS_DIR / "com.kalyan.gbh.server.plist"
    if _port_open(2525):
        return [_ok("Dashboard responding on port 2525")]
    return [
        _err("Dashboard not responding on port 2525"),
        _fix(f"launchctl bootstrap gui/$UID {server_plist}"),
    ]


def check_data_dir() -> list[str]:
    import os
    if GBH_DATA.exists() and os.access(GBH_DATA, os.W_OK):
        return [_ok("~/.gbh/ exists and is writable")]
    if not GBH_DATA.exists():
        return [
            _err("~/.gbh/ does not exist"),
            _fix("mkdir -p ~/.gbh"),
        ]
    return [
        _err("~/.gbh/ is not writable"),
        _fix(f"chmod u+w {GBH_DATA}"),
    ]


def check_tools() -> list[str]:
    lines: list[str] = []
    for tool, install_hint in [
        ("terminal-notifier", "brew install terminal-notifier"),
        ("networksetup",      None),  # always present on macOS
    ]:
        if shutil.which(tool):
            lines.append(_ok(f"{tool} installed"))
        else:
            lines.append(_err(f"{tool} not found"))
            if install_hint:
                lines.append(_fix(install_hint))
    return lines


def check_focus_state() -> list[str]:
    """Detect stale proxy (proxy on but no active focus session)."""
    import json as _json

    state_file = GBH_DATA / "focus_state.json"
    focus_active = False
    try:
        state = _json.loads(state_file.read_text()) if state_file.exists() else {}
        focus_active = bool(state.get("active"))
    except Exception:
        pass

    # Check current proxy state for Wi-Fi
    proxy_on = False
    try:
        r = subprocess.run(
            ["networksetup", "-getautoproxyurl", "Wi-Fi"],
            capture_output=True, text=True, timeout=5,
        )
        proxy_on = "Enabled: Yes" in r.stdout
    except Exception:
        pass

    lines: list[str] = []
    if focus_active:
        lines.append(_ok("Ivan focus session active"))
        if not _port_open(2526):
            lines.append(_warn("Block proxy not listening on port 2526 (session may be stale)"))
            lines.append(_fix("gbh focus stop && gbh focus <minutes>"))
    elif proxy_on:
        lines.append(_warn("Auto-proxy is ON but no active focus session — stale proxy config"))
        lines.append(_fix("networksetup -setautoproxystate Wi-Fi off"))
    else:
        lines.append(_ok("Ivan — no active session, proxy off"))

    return lines


# ── Doctor ───────────────────────────────────────────────────────

class Doctor:
    def run(self) -> None:
        print(f"\n{_BOLD}🏨 GBH Doctor{_RESET}\n" + _hr())

        all_lines: list[str] = []

        print("\nStaff & Processes")
        for line in check_daemons():
            print("  " + line)
            all_lines.append(line)

        print("\n" + _hr())
        print("\nDashboard")
        for line in check_dashboard():
            print("  " + line)
            all_lines.append(line)

        print("\n" + _hr())
        print("\nEnvironment")
        for line in check_data_dir() + check_tools():
            print("  " + line)
            all_lines.append(line)

        print("\n" + _hr())
        print("\nIvan / Focus")
        for line in check_focus_state():
            print("  " + line)
            all_lines.append(line)

        # Summary
        issues = sum(1 for line in all_lines if line.startswith(f"{_RED}❌") or "⚠️" in line)
        print("\n" + _hr())
        if issues == 0:
            print(f"\n{_GREEN}{_BOLD}All good.{_RESET} No issues found.\n")
        else:
            print(f"\n{_RED}{_BOLD}{issues} issue(s) found.{_RESET} See fix hints above.\n")

        sys.exit(0 if issues == 0 else 1)
