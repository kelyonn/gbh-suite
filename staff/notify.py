"""
GBH Notify Utility
Sends macOS notifications via osascript (primary) with terminal-notifier fallback.

Usage:
    from staff.notify import notify
    notify("Serge", "file.pdf → Documents")
    notify("Jopling", "Chrome using 94% CPU", sound="Basso")
"""

import os
import shutil
import subprocess

NOTIFIER = shutil.which("terminal-notifier") or "/opt/homebrew/bin/terminal-notifier"

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

    # Escape quotes for AppleScript strings
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # Primary: osascript — reliable on all modern macOS, Terminal already has permission
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
        result = subprocess.run(
            ["osascript", "-e", "\n".join(script_parts)],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return
    except Exception:
        pass

    # Fallback: terminal-notifier
    if os.path.exists(NOTIFIER):
        try:
            subprocess.run([
                NOTIFIER,
                "-title",   full_title,
                "-message", message,
                "-sender",  "com.apple.Terminal",
                "-ignoreDnD",
            ], capture_output=True, timeout=5)
        except Exception:
            pass

