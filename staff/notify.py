"""
GBH Notify Utility

Delivers macOS notifications with a cascade that refuses to fail silently:

  1. osascript `display notification` (most reliable for CLI/LaunchAgents)
  2. terminal-notifier (no -sender — a stub Concierge.app made that drop banners)
  3. Always append an audit line to ~/.gbh/notify_audit.jsonl

Verification:
  - terminal-notifier path is confirmed via `terminal-notifier -list <group>`
  - osascript path is confirmed by return code
  - `probe()` is used by Doctor / installer to catch breakage early

Never use `-sender com.gbh.concierge` until Concierge.app has a real executable
AND Notification Centre permission is confirmed for that bundle.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

GBH_DATA = Path.home() / ".gbh"
AUDIT_LOG = GBH_DATA / "notify_audit.jsonl"
_BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = _BASE_DIR / "static" / "favicon.png"

# Prefer a user-Applications copy — Launch Services / Notification Centre
# often ignore cellar-only helper apps on modern macOS.
_NOTIFIER_CANDIDATES = [
    Path.home() / "Applications/terminal-notifier.app/Contents/MacOS/terminal-notifier",
    Path("/Applications/terminal-notifier.app/Contents/MacOS/terminal-notifier"),
    Path(shutil.which("terminal-notifier") or ""),
    Path("/opt/homebrew/bin/terminal-notifier"),
    Path("/usr/local/bin/terminal-notifier"),
]


def _resolve_notifier() -> str | None:
    for p in _NOTIFIER_CANDIDATES:
        if p and p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


NOTIFIER = _resolve_notifier()

STAFF_SOUNDS: dict[str, str] = {
    "Gustave": "Purr",
    "Serge": "Tink",
    "Dimitri": "Funk",
    "Zero": "Pop",
    "Ivan": "Submarine",
    "Jopling": "Basso",
    "Henckels": "Sosumi",
    "Kovacs": "Frog",
    "Clotilde": "Glass",
    "Ludwig": "Hero",
    "Agatha": "Purr",
    "Doctor": "Ping",
    "Default": "default",
}

STAFF_SUBTITLES: dict[str, str] = {
    "Gustave": "Concierge",
    "Serge": "File Sorter",
    "Dimitri": "Sentinel",
    "Zero": "Cleanup",
    "Ivan": "Focus Mode",
    "Jopling": "Enforcer",
    "Henckels": "Network",
    "Kovacs": "Git Officer",
    "Clotilde": "Cache Sweeper",
    "Ludwig": "Inspector",
    "Agatha": "Archivist",
    "Doctor": "Health Check",
}


def _audit(record: dict) -> None:
    """Append one delivery attempt. Never raise — logging must not break callers."""
    try:
        GBH_DATA.mkdir(parents=True, exist_ok=True)
        record = {
            **record,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _esc_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _send_osascript(title: str, message: str, subtitle: str, sound: str) -> bool:
    """Primary path — no third-party bundle, no -sender footgun."""
    # Prefer the simple form (no System Events). It still works from LaunchAgents
    # in the Aqua gui domain and avoids an extra TCC dependency.
    sound_clause = ""
    if sound and sound != "default":
        sound_clause = f' sound name "{_esc_as(sound)}"'

    scripts = [
        f'display notification "{_esc_as(message)}" with title "{_esc_as(title)}"'
        + (f' subtitle "{_esc_as(subtitle)}"' if subtitle else "")
        + sound_clause,
    ]
    # Fallback tell-block if the simple form fails on some hosts.
    if subtitle:
        scripts.append(
            "tell application \"System Events\"\n"
            f'  display notification "{_esc_as(message)}" with title "{_esc_as(title)}"'
            f' subtitle "{_esc_as(subtitle)}"{sound_clause}\n'
            "end tell"
        )
    else:
        scripts.append(
            "tell application \"System Events\"\n"
            f'  display notification "{_esc_as(message)}" with title "{_esc_as(title)}"'
            f"{sound_clause}\n"
            "end tell"
        )

    for script in scripts:
        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _tn_list(notifier: str, group: str) -> bool:
    try:
        r = subprocess.run(
            [notifier, "-list", group],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return False
        # Header-only output means nothing delivered for this group.
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        return any(group in ln for ln in lines[1:])
    except Exception:
        return False


def _send_terminal_notifier(
    notifier: str,
    title: str,
    message: str,
    subtitle: str,
    sound: str,
    group: str,
) -> bool:
    """Secondary path. NEVER pass -sender with a stub bundle ID."""
    cmd = [
        notifier,
        "-title", title,
        "-message", message,
        "-group", group,
        "-ignoreDnD",
    ]
    if ICON_PATH.is_file():
        # file:// is more reliably accepted than a bare path on newer macOS.
        cmd += ["-appIcon", ICON_PATH.as_uri()]
    if subtitle:
        cmd += ["-subtitle", subtitle]
    if sound and sound != "default":
        cmd += ["-sound", sound]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return False
    except Exception:
        return False

    # Confirm it actually landed. Exit 0 alone lied to us for months with -sender.
    time.sleep(0.15)
    return _tn_list(notifier, group)


def notify(
    staff: str,
    message: str,
    title: str | None = None,
    sound: str | None = None,
    urgent: bool = False,
) -> bool:
    """
    Send a macOS notification. Returns True if at least one path succeeded.

    Args:
        staff:   Character name (e.g. "Serge") — sets title, subtitle, sound
        message: Notification body
        title:   Override title (default: "GBH · {staff}")
        sound:   Override sound name
        urgent:  If True, uses Basso unless an explicit sound is passed
    """
    full_title = title or f"GBH  ·  {staff}"
    subtitle = STAFF_SUBTITLES.get(staff, "")
    if sound:
        snd = sound
    elif urgent:
        snd = "Basso"
    else:
        snd = STAFF_SOUNDS.get(staff, "default")

    group = f"gbh-{staff.lower()}-{uuid.uuid4().hex[:8]}"
    paths_tried: list[str] = []
    delivered_via: str | None = None

    # 1) osascript first — independent of terminal-notifier permission state
    paths_tried.append("osascript")
    if _send_osascript(full_title, message, subtitle, snd):
        delivered_via = "osascript"

    # 2) terminal-notifier as well when osascript worked? No — avoid doubles.
    #    Only use it if osascript failed.
    notifier = _resolve_notifier()
    if delivered_via is None and notifier:
        paths_tried.append("terminal-notifier")
        if _send_terminal_notifier(notifier, full_title, message, subtitle, snd, group):
            delivered_via = "terminal-notifier"

    ok = delivered_via is not None
    _audit({
        "staff": staff,
        "title": full_title,
        "message": message[:200],
        "ok": ok,
        "via": delivered_via,
        "tried": paths_tried,
        "group": group,
    })

    if not ok:
        # Last-ditch: print so LaunchAgent stdout logs still show something.
        try:
            print(f"[gbh-notify-FAILED] {full_title}: {message}", flush=True)
        except Exception:
            pass

    return ok


def probe(timeout_sec: float = 2.0) -> dict:
    """
    End-to-end self-test for Doctor / installer.

    Returns:
      {
        "ok": bool,
        "via": str | None,
        "detail": str,
        "fix_hint": str | None,
      }
    """
    token = uuid.uuid4().hex[:10]
    msg = f"GBH notify probe {token}"
    title = "GBH  ·  Probe"
    group = f"gbh-probe-{token}"

    # Test osascript
    osa_ok = _send_osascript(title, msg, "Health Check", "Ping")
    if osa_ok:
        _audit({"staff": "Probe", "title": title, "message": msg, "ok": True, "via": "osascript", "tried": ["osascript"], "probe": True})
        return {
            "ok": True,
            "via": "osascript",
            "detail": "osascript display notification succeeded",
            "fix_hint": None,
        }

    notifier = _resolve_notifier()
    if not notifier:
        _audit({"staff": "Probe", "ok": False, "via": None, "tried": ["osascript"], "probe": True})
        return {
            "ok": False,
            "via": None,
            "detail": "osascript failed and terminal-notifier is not installed",
            "fix_hint": "brew install terminal-notifier && bash installer.sh",
        }

    tn_ok = _send_terminal_notifier(notifier, title, msg, "Health Check", "Ping", group)
    # Give NC a moment, then re-check list
    deadline = time.time() + timeout_sec
    while time.time() < deadline and not tn_ok:
        time.sleep(0.2)
        tn_ok = _tn_list(notifier, group)

    _audit({
        "staff": "Probe",
        "title": title,
        "message": msg,
        "ok": tn_ok,
        "via": "terminal-notifier" if tn_ok else None,
        "tried": ["osascript", "terminal-notifier"],
        "probe": True,
        "group": group,
    })

    if tn_ok:
        return {
            "ok": True,
            "via": "terminal-notifier",
            "detail": f"terminal-notifier delivered group {group}",
            "fix_hint": None,
        }

    return {
        "ok": False,
        "via": None,
        "detail": "Both osascript and terminal-notifier failed to deliver",
        "fix_hint": (
            "System Settings → Notifications → allow banners for Script Editor "
            "and terminal-notifier (Alert style: Banners, not None). "
            "Then: open ~/Applications/terminal-notifier.app once and re-run "
            "`gbh doctor` / `bash installer.sh`."
        ),
    }


def recent_audit(n: int = 10) -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    out: list[dict] = []
    for line in AUDIT_LOG.read_text().splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out
