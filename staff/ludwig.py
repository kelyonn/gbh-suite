"""
Ludwig — Weekly System Inspector
Runs every Sunday. Checks brew outdated, disk health, large files,
accumulated downloads. Sends a single weekly digest notification.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify

GBH_DATA = Path.home() / ".gbh"




def run():
    print("🔍 Ludwig: Weekly inspection...", flush=True)
    findings = []

    # ── Brew outdated ─────────────────────────────────────────────
    try:
        res = subprocess.run(["brew", "outdated"], capture_output=True, text=True, timeout=30)
        count = len(res.stdout.strip().splitlines()) if res.stdout.strip() else 0
        if count > 0:
            findings.append(f"{count} brew package(s) outdated")
            print(f"   🍺 {count} outdated packages", flush=True)
    except Exception:
        pass

    # ── Disk health ───────────────────────────────────────────────
    import shutil
    _, _, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    if free_gb < 20:
        findings.append(f"Low disk: {free_gb}GB free")
    print(f"   💾 Disk: {free_gb}GB free", flush=True)

    # ── Downloads folder size ─────────────────────────────────────
    dl = Path(config.DOWNLOADS_DIR)
    if dl.exists():
        dl_mb = sum(f.stat().st_size for f in dl.rglob("*") if f.is_file()) / (1024*1024)
        if dl_mb > 2000:
            findings.append(f"Downloads folder: {dl_mb/1024:.1f}GB")
        print(f"   📥 Downloads: {dl_mb:.0f}MB", flush=True)

    # ── Large files scan (home, skip Library) ─────────────────────
    large = []
    skip = {"Library", ".Trash", "venv", "node_modules", ".git"}
    for root, dirs, files in os.walk(Path.home()):
        dirs[:] = [d for d in dirs if d not in skip]
        for fn in files:
            try:
                p = Path(root) / fn
                if p.stat().st_size > 2 * 1024**3:  # >2GB
                    large.append(p.name)
            except OSError:
                pass
    if large:
        findings.append(f"{len(large)} file(s) over 2GB")

    # ── Compose notification ───────────────────────────────────────
    if findings:
        notify("Ludwig", " · ".join(findings[:3]))
    else:
        notify("Ludwig", "System looks healthy this week.")

    GBH_DATA.mkdir(exist_ok=True)
    (GBH_DATA / "ludwig_last_run.txt").write_text(datetime.now().isoformat())
    print("✅ Ludwig inspection complete.", flush=True)


if __name__ == "__main__":
    run()
