"""
Serge v2 — Smart File Sorter
Watches Downloads and Desktop. Logs all moves. Supports undo.
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Allow running standalone
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify

GBH_DATA     = Path.home() / ".gbh"
MOVE_LOG     = GBH_DATA / "serge_moves.jsonl"

EMOJI_MAP = {
    "Images": "🖼️", "Documents": "📝", "Audio": "🎵", "Video": "🎥",
    "Archives": "📦", "Installers": "💿", "Code": "💻", "Others": "📂"
}




def _log_move(src: str, dst: str, category: str):
    GBH_DATA.mkdir(exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "src": src,
        "dst": dst,
        "category": category,
        "filename": os.path.basename(src),
    }
    with open(MOVE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_recent_moves(n: int = 20) -> list[dict]:
    if not MOVE_LOG.exists():
        return []
    lines = MOVE_LOG.read_text().strip().splitlines()
    entries = []
    for line in reversed(lines[-n * 2:]):
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[:n]


def undo_last_moves(n: int = 1) -> list[str]:
    """Move the last N files back to their source. Returns list of messages."""
    if not MOVE_LOG.exists():
        return ["No move history found."]

    lines = MOVE_LOG.read_text().strip().splitlines()
    if not lines:
        return ["No moves to undo."]

    results = []
    undone_indices = []

    for i, line in enumerate(reversed(lines)):
        if len(undone_indices) >= n:
            break
        try:
            entry = json.loads(line)
            dst = entry["dst"]
            src = entry["src"]
            if os.path.exists(dst):
                os.makedirs(os.path.dirname(src), exist_ok=True)
                shutil.move(dst, src)
                results.append(f"↩️  Restored: {entry['filename']} → {os.path.dirname(src)}")
                undone_indices.append(len(lines) - 1 - i)
            else:
                results.append(f"⚠️  File no longer at destination: {entry['filename']}")
        except Exception as e:
            results.append(f"❌ Error undoing move: {e}")

    # Remove undone entries from log
    remaining = [l for i, l in enumerate(lines) if i not in undone_indices]
    MOVE_LOG.write_text("\n".join(remaining) + ("\n" if remaining else ""))

    return results


def _make_unique(dest_path: str, filename: str, ts: str) -> str:
    """Produce a unique destination path using timestamp suffix."""
    base, ext = os.path.splitext(filename)
    path = os.path.join(dest_path, filename)
    if not os.path.exists(path):
        return path
    # Use timestamp to avoid conflicts
    return os.path.join(dest_path, f"{base}_{ts}{ext}")


def _categorize(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    for cat, exts in config.SERGE_DESTINATIONS.items():
        if ext in exts:
            return cat
    return "Others"  # catches everything with no matching extension


def _sort_file(file_path: str):
    filename = os.path.basename(file_path)
    category = _categorize(filename)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Destination: Code goes to Projects dir, everything else to a subfolder of the source dir
    src_parent = os.path.dirname(file_path)
    if category == "Code":
        dest_dir = config.PROJECTS_DIR
    else:
        dest_dir = os.path.join(src_parent, category)  # includes Others

    os.makedirs(dest_dir, exist_ok=True)
    final_dest = _make_unique(dest_dir, filename, ts)

    try:
        shutil.move(file_path, final_dest)
        icon = EMOJI_MAP.get(category, "📂")
        _log_move(file_path, final_dest, category)
        notify("Serge", f"{filename} → {category} {icon}")
        print(f"✅ {filename} → {category}", flush=True)
    except Exception as e:
        print(f"❌ Error moving {filename}: {e}", flush=True)


def _is_skip(filename: str) -> bool:
    """Skip only system/hidden files and actively downloading files."""
    return (
        filename.startswith(".")
        or filename == ".DS_Store"
        or filename.endswith((".tmp", ".crdownload", ".part", ".download"))
    )


class SmartSorter(FileSystemEventHandler):
    """Watchdog event handler — directly subclasses FileSystemEventHandler."""

    def __init__(self, watch_dir: str):
        super().__init__()
        self.watch_dir = os.path.abspath(watch_dir)
        self.processing: set[str] = set()
        self.processed: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        if os.path.dirname(os.path.abspath(event.src_path)) != self.watch_dir:
            return
        self._handle(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if os.path.dirname(os.path.abspath(event.dest_path)) != self.watch_dir:
            return
        self._handle(event.dest_path)

    def _handle(self, path: str):
        abs_path = os.path.abspath(path)
        filename  = os.path.basename(path)

        if _is_skip(filename):
            return
        if abs_path in self.processing or abs_path in self.processed:
            return
        if not os.path.isfile(path):
            return

        self.processing.add(abs_path)
        try:
            time.sleep(0.8)
            if os.path.isfile(path):
                _sort_file(path)
        finally:
            self.processing.discard(abs_path)
            self.processed.add(abs_path)
            if len(self.processed) > 200:
                self.processed = set(list(self.processed)[-100:])


def _sort_existing(watch_dir: str):
    count = 0
    for filename in os.listdir(watch_dir):
        if _is_skip(filename):
            continue
        full = os.path.join(watch_dir, filename)
        if os.path.isfile(full):
            _sort_file(full)
            count += 1
    if count:
        print(f"✅ Sorted {count} existing file(s) in {watch_dir}", flush=True)


def start_watch():
    from watchdog.observers import Observer

    GBH_DATA.mkdir(exist_ok=True)
    os.makedirs(config.PROJECTS_DIR, exist_ok=True)

    observers = []
    for watch_dir in config.SERGE_WATCH_DIRS:
        if not os.path.exists(watch_dir):
            print(f"⚠️  Watch dir not found, skipping: {watch_dir}", flush=True)
            continue

        _sort_existing(watch_dir)

        handler = SmartSorter(watch_dir)
        obs = Observer()
        obs.schedule(handler, watch_dir, recursive=False)
        obs.start()
        observers.append(obs)
        print(f"🎩 Serge watching: {watch_dir}", flush=True)

    notify("Serge", "Watching the door.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for obs in observers:
            obs.stop()
        for obs in observers:
            obs.join()

