"""
GBH v2 — Central Configuration
All settings for all staff members live here.
"""

import os

# ─── PATHS ──────────────────────────────────────────────
PROJECTS_DIR   = os.path.expanduser("~/Documents/Projects")
DOWNLOADS_DIR  = os.path.expanduser("~/Downloads")
DESKTOP_DIR    = os.path.expanduser("~/Desktop")
ARCHIVE_DIR    = os.path.expanduser("~/Documents/Archives")
BACKUP_DIR     = os.path.expanduser("~/Documents/Backups/Dotfiles")
GBH_DATA_DIR   = os.path.expanduser("~/.gbh")  # runtime data: logs, state

# ─── DIMITRI — Port & Process Sentinel ───────────────────
PERMANENT_PORTS = [3000, 8000, 5432, 8080]

# Optional: HTTP health check URLs (instead of raw TCP)
# HEALTH_CHECK_URLS = ["http://localhost:3000/health"]
HEALTH_CHECK_URLS = []

# Optional: watch these log files for errors
PERMANENT_LOGS = [
    # os.path.expanduser("~/Documents/Projects/myapp/debug.log"),
]

# Processes to restart if they crash (command substring to match)
WATCHDOG_PROCESSES = []

# ─── SERGE — File Sorter ─────────────────────────────────
SERGE_WATCH_DIRS = [
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Desktop"),
]

SERGE_DESTINATIONS = {
    "Images":     [".jpg", ".jpeg", ".png", ".gif", ".svg", ".heic", ".webp", ".bmp", ".tiff"],
    "Documents":  [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".csv", ".xlsx", ".epub", ".pages", ".numbers", ".key"],
    "Audio":      [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"],
    "Video":      [".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"],
    "Archives":   [".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".dmg"],
    "Installers": [".pkg", ".app"],
    "Code":       [".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".sql", ".sh", ".json", ".ipynb", ".rb", ".go", ".rs"],
}

# Files older than this many days in Downloads will be flagged by Zero
OLD_DOWNLOADS_DAYS = 30

# ─── GUSTAVE — Morning Briefing ──────────────────────────
CRITICAL_PORTS = [3000, 5432, 6379, 8000, 8080]

DOTFILES_TO_BACKUP = [
    "~/.zshrc",
    "~/.gitconfig",
    "~/.ssh/config",
    "~/.vimrc",
    "~/.tmux.conf",
]

# ─── ZERO — Cleanup ──────────────────────────────────────
SCREENSHOT_MAX_AGE_DAYS = 1      # Auto-sweep screenshots older than this
LARGE_FILE_THRESHOLD_MB = 500    # Files larger than this flagged by Zero
TRASH_WARN_GB = 5                # Warn when Trash exceeds this

# ─── IVAN — Focus Mode ───────────────────────────────────
# Ivan auto-prefixes www. — list each domain once.
FOCUS_BLOCKLIST = [
    # Social
    "reddit.com", "twitter.com", "x.com", "instagram.com",
    "facebook.com", "tiktok.com", "linkedin.com", "threads.net",
    "pinterest.com", "snapchat.com", "tumblr.com", "bsky.app",
    # Video / entertainment
    "youtube.com", "netflix.com", "twitch.tv",
    "hulu.com", "primevideo.com", "disneyplus.com",
    # Time-sinks
    "news.ycombinator.com", "buzzfeed.com", "9gag.com",
    "imgur.com", "quora.com", "medium.com",
]

FOCUS_DEFAULT_MINUTES  = 25
FOCUS_BREAK_MINUTES    = 5

# ─── SERVER ──────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 2525
