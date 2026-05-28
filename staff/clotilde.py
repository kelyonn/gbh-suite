"""
Clotilde — Cache & Temp Sweeper
Runs daily. Clears npm, pip, brew, Xcode caches when bloated.
"""

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify

GBH_DATA = Path.home() / ".gbh"
THRESHOLDS = {"npm": 500, "pip": 500, "brew": 1000, "xcode": 2000}




def _dir_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def _run(cmd):
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception:
        pass


def _xcode_running() -> bool:
    """Skip DerivedData cleanup if Xcode or a build is in progress."""
    targets = {"Xcode", "xcodebuild", "swift-build-tool", "swift-frontend", "clang"}
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info.get("name") or "") in targets:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def run():
    print("🧹 Clotilde: Inspecting caches...", flush=True)
    freed_total = 0.0
    actions = []

    npm_cache = Path.home() / "Library/Caches/node"
    if (s := _dir_mb(npm_cache)) > THRESHOLDS["npm"]:
        _run(["npm", "cache", "clean", "--force"])
        freed = s - _dir_mb(npm_cache)
        freed_total += freed
        actions.append(f"npm {freed:.0f}MB")

    pip_cache = Path.home() / "Library/Caches/pip"
    if (s := _dir_mb(pip_cache)) > THRESHOLDS["pip"]:
        _run(["/opt/homebrew/bin/python3.11", "-m", "pip", "cache", "purge"])
        freed = s - _dir_mb(pip_cache)
        freed_total += freed
        actions.append(f"pip {freed:.0f}MB")

    brew_cache = Path.home() / "Library/Caches/Homebrew"
    if (s := _dir_mb(brew_cache)) > THRESHOLDS["brew"]:
        _run(["brew", "cleanup", "--prune=7"])
        freed = s - _dir_mb(brew_cache)
        freed_total += freed
        actions.append(f"brew {freed:.0f}MB")

    xcode_dd = Path.home() / "Library/Developer/Xcode/DerivedData"
    if (s := _dir_mb(xcode_dd)) > THRESHOLDS["xcode"]:
        if _xcode_running():
            print(f"   ⏸  Xcode is running — skipping DerivedData wipe ({s:.0f}MB).", flush=True)
        else:
            try:
                shutil.rmtree(str(xcode_dd))
                xcode_dd.mkdir()
                freed_total += s
                actions.append(f"Xcode {s:.0f}MB")
            except Exception:
                pass

    # Old /tmp files (>7 days)
    cutoff = time.time() - 7 * 86400
    for f in Path("/tmp").iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                freed_total += f.stat().st_size / (1024*1024)
                f.unlink()
        except Exception:
            pass

    if freed_total > 10:
        notify("Clotilde", f"Freed {freed_total:.0f}MB — {', '.join(actions)}")
    else:
        print("   ✨ Caches tidy.", flush=True)

    GBH_DATA.mkdir(exist_ok=True)
    (GBH_DATA / "clotilde_last_run.txt").write_text(datetime.now().isoformat())


if __name__ == "__main__":
    run()
