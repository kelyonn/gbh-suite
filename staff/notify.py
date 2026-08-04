"""
GBH Notify Utility
Sends macOS notifications via terminal-notifier (primary) with osascript fallback.

Usage:
    from staff.notify import notify
    notify("Serge", "file.pdf → Documents")
    notify("Jopling", "Chrome using 94% CPU", sound="Basso")
"""

import os
import shutil
import subprocess
from pathlib import Path

NOTIFIER = shutil.which("terminal-notifier") or "/opt/homebrew/bin/terminal-notifier"

# Absolute path to the GBH favicon used as the notification icon
_BASE_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = str(_BASE_DIR / "static" / "favicon.png")

# Per-staff sounds — matches each character's personality
STAFF_SOUNDS: dict[str, str] = {
    "Gustave":  "Purr",
    "Serge":    "Tink",
    "Dimitri":  "Funk",
    "Zero":     "Pop",
    "Ivan":     "Submarine",
    "Jopling":  "Basso",
    "Henckels": "Sosumi",
    "Kovacs":   "Frog",
    "Clotilde": "Glass",
    "Ludwig":   "Hero",
    "Agatha":   "Purr",
    "Default":  "default",
}

# Staff subtitles shown under the title
STAFF_SUBTITLES: dict[str, str] = {
    "Gustave":  "Concierge",
    "Serge":    "File Sorter",
    "Dimitri":  "Sentinel",
    "Zero":     "Cleanup",
    "Ivan":     "Focus Mode",
    "Jopling":  "Enforcer",
    "Henckels": "Network",
    "Kovacs":   "Git Officer",
    "Clotilde": "Cache Sweeper",
    "Ludwig":   "Inspector",
    "Agatha":   "Archivist",
}


def notify(
    staff: str,
    message: str,
    title: str | None = None,
    sound: str | None = None,
    urgent: bool = False,
):
    """
    Send a properly attributed macOS notification.

    Args:
        staff:   Character name (e.g. "Serge") — sets title, subtitle, sound
        message: Notification body
        title:   Override title (default: "GBH · {staff}")
        sound:   Override sound name
        urgent:  If True, uses a more attention-grabbing sound
    """
    full_title = title or f"GBH  ·  {staff}"
    subtitle   = STAFF_SUBTITLES.get(staff, "")
    snd        = sound or STAFF_SOUNDS.get(staff, "default")

    # Primary: terminal-notifier — supports -appIcon for custom icon
    if os.path.exists(NOTIFIER):
        try:
            cmd = [
                NOTIFIER,
                "-title",   full_title,
                "-message", message,
                "-sender", "com.gbh.concierge",
                "-ignoreDnD",
            ]
            if subtitle:
                cmd += ["-subtitle", subtitle]
            if snd and snd != "default":
                cmd += ["-sound", snd]
            subprocess.run(cmd, capture_output=True, timeout=5)
            return
        except Exception:
            pass

    # Fallback: osascript
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script_parts = [
        f'tell application "System Events"',
        f'  display notification "{_esc(message)}" with title "{_esc(full_title)}"',
    ]
    if subtitle:
        script_parts[1] = (
            f'  display notification "{_esc(message)}" with title "{_esc(full_title)}"'
            f' subtitle "{_esc(subtitle)}"'
        )
    script_parts.append("end tell")

    try:
        subprocess.run(
            ["osascript", "-e", "\n".join(script_parts)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass
