"""
GBH Notify Utility
Unified notification layer using terminal-notifier.
Falls back to osascript if terminal-notifier is not available.

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

GBH_ICON = os.path.expanduser("~/.gbh/icon.png")


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
    full_title   = title or f"GBH  ·  {staff}"
    subtitle     = STAFF_SUBTITLES.get(staff, "")
    chosen_sound = sound or (STAFF_SOUNDS.get("Default") if urgent else STAFF_SOUNDS.get(staff, "default"))

    if os.path.exists(NOTIFIER):
        cmd = [
            NOTIFIER,
            "-title",    full_title,
            "-message",  message,
            "-group",    f"gbh-{staff.lower()}",
            "-sound",    chosen_sound,
        ]
        if subtitle:
            cmd += ["-subtitle", subtitle]
        if os.path.exists(GBH_ICON):
            cmd += ["-appIcon", GBH_ICON]
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            return
        except Exception:
            pass

    # Fallback: osascript (will appear as Script Editor but at least works)
    safe_msg   = message.replace('"', '\\"')
    safe_title = full_title.replace('"', '\\"')
    os.system(f'osascript -e \'display notification "{safe_msg}" with title "{safe_title}"\'')
