"""
Ivan — Focus Mode Manager
Blocks distracting sites by editing /etc/hosts.
Runs a countdown and auto-unblocks when done.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

GBH_DATA = Path.home() / ".gbh"
FOCUS_STATE_FILE = GBH_DATA / "focus_state.json"
HOSTS_FILE = Path("/etc/hosts")
HOSTS_MARKER_START = "# GBH_IVAN_START"
HOSTS_MARKER_END   = "# GBH_IVAN_END"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify as _send_notify





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


def _block_sites(blocklist: list[str]):
    """Add blocklist entries to /etc/hosts via sudo."""
    lines = [HOSTS_MARKER_START]
    for domain in blocklist:
        lines.append(f"127.0.0.1 {domain}")
        if not domain.startswith("www."):
            lines.append(f"127.0.0.1 www.{domain}")
    lines.append(HOSTS_MARKER_END)
    block_text = "\n".join(lines) + "\n"

    try:
        current = HOSTS_FILE.read_text()
        # Remove any existing GBH block first
        current = _strip_gbh_block(current)
        new_content = current.rstrip("\n") + "\n\n" + block_text
        _write_hosts(new_content)
        return True
    except Exception as e:
        print(f"❌ Could not block sites: {e}")
        return False


def _unblock_sites():
    """Remove GBH block from /etc/hosts."""
    try:
        current = HOSTS_FILE.read_text()
        new_content = _strip_gbh_block(current)
        _write_hosts(new_content)
        return True
    except Exception as e:
        print(f"❌ Could not unblock sites: {e}")
        return False


def _strip_gbh_block(content: str) -> str:
    lines = content.splitlines()
    out, inside = [], False
    for line in lines:
        if line.strip() == HOSTS_MARKER_START:
            inside = True
            continue
        if line.strip() == HOSTS_MARKER_END:
            inside = False
            continue
        if not inside:
            out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"


def _write_hosts(content: str):
    """Write to /etc/hosts using sudo tee (doesn't require root shell)."""
    proc = subprocess.run(
        ["sudo", "tee", str(HOSTS_FILE)],
        input=content.encode(),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise PermissionError(proc.stderr.decode())
    # Flush DNS cache
    subprocess.run(["sudo", "dscacheutil", "-flushcache"], capture_output=True)
    subprocess.run(["sudo", "killall", "-HUP", "mDNSResponder"], capture_output=True)


class Ivan:
    def start(self, minutes: int, blocklist: list[str]):
        """Start a focus session."""
        state = _read_state()
        if state and state.get("active"):
            ends_at = datetime.fromisoformat(state["ends_at"])
            remaining = max(0, int((ends_at - datetime.now()).total_seconds() // 60))
            print(f"⚠️  Focus already active. {remaining}m remaining.")
            return

        print(f"🔕 Ivan: Starting {minutes}-minute focus session...")
        if not _block_sites(blocklist):
            print("❌ Could not block sites. Try running with sudo once to grant tee access.")
            return

        ends_at = datetime.now() + timedelta(minutes=minutes)
        _write_state({
            "active": True,
            "started_at": datetime.now().isoformat(),
            "ends_at": ends_at.isoformat(),
            "duration_min": minutes,
            "blocklist": blocklist,
        })

        _send_notify("Ivan", f"Blocking distractions for {minutes} minutes.")
        print(f"✅ Focus active until {ends_at.strftime('%I:%M %p')}. Sites blocked.")

        # Wait and auto-unblock
        try:
            while datetime.now() < ends_at:
                time.sleep(30)
        except KeyboardInterrupt:
            pass

        self.stop(send_notify=True)

    def stop(self, send_notify: bool = False):
        """End focus session and unblock sites."""
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No active focus session.")
            return

        _unblock_sites()
        _clear_state()

        if send_notify:
            _send_notify("Ivan", "Great work. Sites unblocked.")
        print("✅ Focus session ended. Sites unblocked.")

    def status(self) -> dict:
        """Return focus status dict for dashboard/CLI."""
        state = _read_state()
        if not state or not state.get("active"):
            return {"active": False, "remaining_sec": 0, "duration_min": 0, "ends_at": None}

        ends_at = datetime.fromisoformat(state["ends_at"])
        remaining = max(0, int((ends_at - datetime.now()).total_seconds()))

        if remaining == 0:
            # Session expired — clean up silently
            _unblock_sites()
            _clear_state()
            return {"active": False, "remaining_sec": 0, "duration_min": 0, "ends_at": None}

        return {
            "active": True,
            "remaining_sec": remaining,
            "duration_min": state.get("duration_min", 25),
            "ends_at": state.get("ends_at"),
        }

    def pomodoro(self, blocklist: list[str], cycles: int = 4):
        """Run pomodoro cycles: 25 min focus → 5 min break × N."""
        from config import FOCUS_DEFAULT_MINUTES, FOCUS_BREAK_MINUTES
        print(f"🍅 Ivan: Starting Pomodoro ({cycles} cycles × {FOCUS_DEFAULT_MINUTES}m focus / {FOCUS_BREAK_MINUTES}m break)")
        for i in range(cycles):
            print(f"\n── Cycle {i+1}/{cycles}: Focus ──")
            self.start(FOCUS_DEFAULT_MINUTES, blocklist)
            if i < cycles - 1:
                _send_notify("Ivan", f"Take {FOCUS_BREAK_MINUTES} minutes. Back soon.")
                print(f"☕ Break for {FOCUS_BREAK_MINUTES} minutes...")
                time.sleep(FOCUS_BREAK_MINUTES * 60)
        _send_notify("Ivan", f"All {cycles} cycles done. Excellent focus!")
        print("\n🎉 Pomodoro complete!")
