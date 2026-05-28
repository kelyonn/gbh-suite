"""
Ivan — Focus Mode Manager
Blocks distracting sites via a PAC (Proxy Auto-Config) file + networksetup.
No sudo required. Works from CLI, dashboard, and background threads.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

GBH_DATA         = Path.home() / ".gbh"
FOCUS_STATE_FILE = GBH_DATA / "focus_state.json"
PAC_FILE         = GBH_DATA / "ivan_block.pac"

LOOP_TICK_SEC = 5  # how often start() re-reads state to detect pause/resume/stop

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify as _send_notify


# ── State helpers ─────────────────────────────────────────────────

def _read_state() -> dict | None:
    if not FOCUS_STATE_FILE.exists():
        return None
    try:
        return json.loads(FOCUS_STATE_FILE.read_text())
    except Exception:
        return None


def _write_state(state: dict):
    GBH_DATA.mkdir(exist_ok=True)
    FOCUS_STATE_FILE.write_text(json.dumps(state))


def _clear_state():
    if FOCUS_STATE_FILE.exists():
        FOCUS_STATE_FILE.unlink()


# ── Network helpers ───────────────────────────────────────────────

def _network_services() -> list[str]:
    """Return all enabled network service names."""
    try:
        r = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, timeout=5,
        )
        services = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("An asterisk") or line.startswith("*"):
                continue
            services.append(line)
        return services or ["Wi-Fi"]
    except Exception:
        return ["Wi-Fi"]


def _write_pac(blocklist: list[str]) -> str:
    """Write a PAC file that sends blocked domains to a dead local proxy."""
    domains: set[str] = set()
    for d in blocklist:
        d = d.lower()
        domains.add(d)
        if not d.startswith("www."):
            domains.add("www." + d)

    # Build JS array literal
    entries = ",\n    ".join(f'"{d}"' for d in sorted(domains))
    pac = f"""\
// GBH Ivan — focus mode block list
// Generated automatically. Do not edit while focus is active.
function FindProxyForURL(url, host) {{
    var blocked = [
    {entries}
    ];
    var h = host.toLowerCase();
    for (var i = 0; i < blocked.length; i++) {{
        if (h === blocked[i] || h.endsWith("." + blocked[i])) {{
            // Route to a local port that isn't listening — connection refused.
            return "PROXY 127.0.0.1:9";
        }}
    }}
    return "DIRECT";
}}
"""
    GBH_DATA.mkdir(exist_ok=True)
    PAC_FILE.write_text(pac)
    return str(PAC_FILE)


def _block_sites(blocklist: list[str]) -> bool:
    """Enable PAC proxy on all network services. Returns True if at least one succeeded."""
    pac_path = _write_pac(blocklist)
    pac_url  = f"file://{pac_path}"
    ok = False
    for svc in _network_services():
        try:
            r1 = subprocess.run(
                ["networksetup", "-setautoproxyurl", svc, pac_url],
                capture_output=True, timeout=5,
            )
            r2 = subprocess.run(
                ["networksetup", "-setautoproxystate", svc, "on"],
                capture_output=True, timeout=5,
            )
            if r1.returncode == 0 and r2.returncode == 0:
                ok = True
        except Exception:
            pass
    return ok


def _unblock_sites():
    """Disable PAC proxy on all network services and remove the PAC file."""
    for svc in _network_services():
        try:
            subprocess.run(
                ["networksetup", "-setautoproxystate", svc, "off"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
    if PAC_FILE.exists():
        PAC_FILE.unlink(missing_ok=True)


# ── Ivan class ────────────────────────────────────────────────────

class Ivan:

    def start(self, minutes: int, blocklist: list[str]):
        """Start a focus session. Blocks the calling process until the session ends."""
        state = _read_state()
        if state and state.get("active"):
            if state.get("paused"):
                print("⚠️  A paused focus session exists. Use `gbh focus resume` or `gbh focus stop`.")
            else:
                ends_at   = datetime.fromisoformat(state["ends_at"])
                remaining = max(0, int((ends_at - datetime.now()).total_seconds() // 60))
                print(f"⚠️  Focus already active. {remaining}m remaining.")
            return

        print(f"🔕 Ivan: Starting {minutes}-minute focus session...")
        if not _block_sites(blocklist):
            print("❌ Could not set proxy. Check networksetup permissions.")
            return

        ends_at = datetime.now() + timedelta(minutes=minutes)
        _write_state({
            "active": True,
            "started_at": datetime.now().isoformat(),
            "ends_at": ends_at.isoformat(),
            "duration_min": minutes,
            "blocklist": blocklist,
            "paused": False,
            "paused_at": None,
            "remaining_at_pause_sec": None,
        })

        _send_notify("Ivan", f"Blocking distractions for {minutes} minutes.")
        print(f"✅ Focus active until {ends_at.strftime('%I:%M %p')}. Sites blocked.")

        # State-driven loop: re-reads state each tick so pause/resume/stop
        # from a separate shell is picked up within LOOP_TICK_SEC seconds.
        try:
            while True:
                s = _read_state()
                if not s or not s.get("active"):
                    return          # stop() was called externally
                if s.get("paused"):
                    time.sleep(LOOP_TICK_SEC)
                    continue
                ends_at = datetime.fromisoformat(s["ends_at"])
                if datetime.now() >= ends_at:
                    break
                time.sleep(LOOP_TICK_SEC)
        except KeyboardInterrupt:
            pass

        self.stop(send_notify=True)

    def pause(self):
        """Pause the active session: disable proxy, freeze the timer."""
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No active focus session.")
            return
        if state.get("paused"):
            print("ℹ️  Focus is already paused.")
            return

        ends_at   = datetime.fromisoformat(state["ends_at"])
        remaining = max(0, int((ends_at - datetime.now()).total_seconds()))

        _unblock_sites()
        state.update({
            "paused": True,
            "paused_at": datetime.now().isoformat(),
            "remaining_at_pause_sec": remaining,
        })
        _write_state(state)

        mins, secs = divmod(remaining, 60)
        _send_notify("Ivan", f"Paused. {mins}m {secs}s left.")
        print(f"⏸️  Focus paused — {mins}m {secs}s left. Sites unblocked.")

    def resume(self):
        """Resume a paused session: re-enable proxy, continue with remaining time."""
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No focus session to resume.")
            return
        if not state.get("paused"):
            print("ℹ️  Focus is already running.")
            return

        remaining = int(state.get("remaining_at_pause_sec") or 0)
        if remaining <= 0:
            print("ℹ️  No time left on this session. Ending it.")
            _clear_state()
            return

        if not _block_sites(state.get("blocklist", [])):
            print("❌ Could not re-enable proxy.")
            return

        new_ends_at = datetime.now() + timedelta(seconds=remaining)
        state.update({
            "paused": False,
            "paused_at": None,
            "remaining_at_pause_sec": None,
            "ends_at": new_ends_at.isoformat(),
        })
        _write_state(state)

        mins, secs = divmod(remaining, 60)
        _send_notify("Ivan", f"Resumed. {mins}m {secs}s to go.")
        print(f"▶️  Focus resumed until {new_ends_at.strftime('%I:%M %p')}.")

    def stop(self, send_notify: bool = False):
        """End the focus session and disable the proxy."""
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No active focus session.")
            return

        # Only unblock if sites are currently blocked (not if already paused/unblocked).
        if not state.get("paused"):
            _unblock_sites()
        _clear_state()

        if send_notify:
            _send_notify("Ivan", "Great work. Sites unblocked.")
        print("✅ Focus session ended. Sites unblocked.")

    def status(self) -> dict:
        """Return focus status dict. Safe to call from any context."""
        state = _read_state()
        if not state or not state.get("active"):
            return {"active": False, "paused": False, "remaining_sec": 0,
                    "duration_min": 0, "ends_at": None}

        if state.get("paused"):
            return {
                "active": True,
                "paused": True,
                "remaining_sec": int(state.get("remaining_at_pause_sec") or 0),
                "duration_min": state.get("duration_min", 25),
                "ends_at": state.get("ends_at"),
            }

        ends_at   = datetime.fromisoformat(state["ends_at"])
        remaining = max(0, int((ends_at - datetime.now()).total_seconds()))

        if remaining == 0:
            # Session expired (e.g. Mac restarted mid-session). Clean up safely —
            # no sudo needed since we're just toggling networksetup.
            _unblock_sites()
            _clear_state()
            return {"active": False, "paused": False, "remaining_sec": 0,
                    "duration_min": 0, "ends_at": None}

        return {
            "active": True,
            "paused": False,
            "remaining_sec": remaining,
            "duration_min": state.get("duration_min", 25),
            "ends_at": state.get("ends_at"),
        }

    def pomodoro(self, blocklist: list[str], cycles: int = 4):
        """Run N Pomodoro cycles: focus → short break, repeat."""
        from config import FOCUS_DEFAULT_MINUTES, FOCUS_BREAK_MINUTES
        print(f"🍅 Ivan: Starting Pomodoro — {cycles} × {FOCUS_DEFAULT_MINUTES}m focus / {FOCUS_BREAK_MINUTES}m break")
        for i in range(cycles):
            print(f"\n── Cycle {i + 1}/{cycles}: Focus ──")
            self.start(FOCUS_DEFAULT_MINUTES, blocklist)
            if i < cycles - 1:
                _send_notify("Ivan", f"Take {FOCUS_BREAK_MINUTES} minutes. Back soon.")
                print(f"☕ Break for {FOCUS_BREAK_MINUTES} minutes…")
                time.sleep(FOCUS_BREAK_MINUTES * 60)
        _send_notify("Ivan", f"All {cycles} cycles done. Excellent focus!")
        print("\n🎉 Pomodoro complete!")
