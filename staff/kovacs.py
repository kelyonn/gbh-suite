"""
Kovacs — Git Compliance Officer
Runs every evening. Scans all repos for uncommitted/unpushed work.
Sends a single summary notification. Never nags during the day.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify




def run():
    print("⚖️ Kovacs: Evening git inspection...", flush=True)

    projects = Path(config.PROJECTS_DIR)
    if not projects.exists():
        print("No projects directory found.", flush=True)
        return

    dirty, unpushed, clean = [], [], []

    for item in sorted(projects.iterdir()):
        if not (item.is_dir() and (item / ".git").exists()):
            continue

        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(item),
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        ahead_raw = subprocess.run(
            ["git", "rev-list", "--count", "@{u}..HEAD"],
            cwd=str(item), capture_output=True, text=True, timeout=5
        ).stdout.strip()
        ahead = int(ahead_raw) if ahead_raw.isdigit() else 0

        if status:
            dirty.append(item.name)
        elif ahead:
            unpushed.append((item.name, ahead))
        else:
            clean.append(item.name)

    total_issues = len(dirty) + len(unpushed)
    print(f"   Dirty: {len(dirty)}  Unpushed: {len(unpushed)}  Clean: {len(clean)}", flush=True)

    if total_issues == 0:
        notify("Kovacs", f"All {len(clean)} repos are clean and pushed.")
        return

    parts = []
    if dirty:
        parts.append(f"{len(dirty)} uncommitted")
    if unpushed:
        parts.append(f"{len(unpushed)} unpushed")

    names = dirty[:3] + [n for n, _ in unpushed[:2]]
    name_str = ", ".join(names[:4])
    if total_issues > 4:
        name_str += f" +{total_issues - 4} more"

    notify("Kovacs", f"{' · '.join(parts)} — {name_str}")


if __name__ == "__main__":
    run()
