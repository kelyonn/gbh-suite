"""
Zero v2 — Cleanup Crew
Screenshots, old downloads, duplicate hunter, large file finder, Trash monitor.
"""

import hashlib
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify

TRASH_DIR = Path.home() / ".Trash"
DESKTOP   = Path(config.DESKTOP_DIR)
DOWNLOADS = Path(config.DOWNLOADS_DIR)




class Zero:

    def log(self, msg: str):
        print(f"🟣 {msg}", flush=True)

    def clean_screenshots(self, days_old: int = 1) -> int:
        self.log(f"Sweeping Desktop for screenshots older than {days_old} day(s)...")
        cutoff = time.time() - (days_old * 86400)
        count = 0
        for p in DESKTOP.iterdir():
            if "Screenshot" in p.name and p.suffix == ".png":
                try:
                    if p.stat().st_ctime < cutoff:
                        shutil.move(str(p), str(TRASH_DIR))
                        print(f"   🗑️  Trashed: {p.name}", flush=True)
                        count += 1
                except Exception as e:
                    print(f"   ❌ {e}", flush=True)
        self.log("Desktop is clean." if count == 0 else f"Moved {count} screenshot(s) to Trash.")
        return count

    def archive_old_downloads(self, days: int | None = None) -> int:
        days = days or config.OLD_DOWNLOADS_DAYS
        cutoff = time.time() - (days * 86400)
        archive_dir = Path(config.ARCHIVE_DIR) / "OldDownloads"
        archive_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Archiving Downloads not accessed in {days}+ days...")
        count = 0
        for p in DOWNLOADS.iterdir():
            if p.name.startswith(".") or p.is_dir():
                continue
            try:
                if p.stat().st_atime < cutoff:
                    dest = archive_dir / p.name
                    i = 1
                    while dest.exists():
                        dest = archive_dir / f"{p.stem}_{i}{p.suffix}"
                        i += 1
                    shutil.move(str(p), str(dest))
                    count += 1
            except Exception as e:
                print(f"   ❌ {e}", flush=True)
        self.log(f"Archived {count} old file(s).")
        return count

    def find_large_files(self, directory: str | None = None, threshold_mb: float | None = None) -> list[dict]:
        directory = directory or str(Path.home())
        threshold_mb = threshold_mb or config.LARGE_FILE_THRESHOLD_MB
        threshold_bytes = threshold_mb * 1024 * 1024
        self.log(f"Scanning {directory} for files > {threshold_mb:.0f}MB...")
        results = []
        skip = {".git", "venv", ".venv", "node_modules", "Library"}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in skip]
            for fn in files:
                path = os.path.join(root, fn)
                try:
                    size = os.path.getsize(path)
                    if size >= threshold_bytes:
                        results.append({"path": path, "size_mb": round(size / (1024 * 1024), 1)})
                except OSError:
                    pass
        results.sort(key=lambda x: x["size_mb"], reverse=True)
        return results

    def check_trash(self) -> dict:
        total = sum(f.stat().st_size for f in TRASH_DIR.rglob("*") if f.is_file())
        gb = round(total / (1024 ** 3), 2)
        if gb > config.TRASH_WARN_GB:
            notify("Zero", "Your Trash has {gb:.1f} GB. Consider emptying it.")
        return {"size_gb": gb, "warn": gb > config.TRASH_WARN_GB}

    def _hash_file(self, path: str) -> str | None:
        hasher = hashlib.md5()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return None

    def find_duplicates(self, directory: str) -> list[list[str]]:
        self.log(f"Hunting duplicates in: {directory}")
        by_size: dict[int, list[str]] = {}
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if fn.startswith("."): continue
                path = os.path.join(root, fn)
                try:
                    size = os.path.getsize(path)
                    if size >= 10240:
                        by_size.setdefault(size, []).append(path)
                except OSError:
                    pass
        candidates = {s: p for s, p in by_size.items() if len(p) > 1}
        self.log(f"Phase 1: {len(candidates)} size groups.")
        duplicates: list[list[str]] = []
        for paths in candidates.values():
            hashes: dict[str, list[str]] = {}
            for path in paths:
                h = self._hash_file(path)
                if h:
                    hashes.setdefault(h, []).append(path)
            for group in hashes.values():
                if len(group) > 1:
                    duplicates.append(group)
        if not duplicates:
            self.log("No duplicates found.")
            return []
        total_saved = 0.0
        for group in duplicates:
            size_mb = os.path.getsize(group[0]) / (1024 * 1024)
            print(f"\n📦 Duplicate group ({size_mb:.2f} MB each)")
            for i, f in enumerate(group):
                print(f"   [{i+1}] {f}")
            choice = input("   👉 Keep which? (number or 0 to skip): ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(group):
                    for j, path in enumerate(group):
                        if j != idx:
                            try:
                                shutil.move(path, str(TRASH_DIR))
                                total_saved += size_mb
                            except Exception as e:
                                print(f"   ❌ {e}")
        print(f"\n✨ Reclaimed ~{total_saved:.2f} MB.")
        return duplicates