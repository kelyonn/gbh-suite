"""
Agatha v2 — Archiver & Dotfile Backup
Smart project packing, incremental dotfile backup, restore support.
"""

import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

BLACKLIST = {"node_modules", "venv", ".venv", "env", "__pycache__", ".git", "dist", "build", ".DS_Store"}


class Agatha:

    def log(self, msg: str):
        print(f"🧁 {msg}", flush=True)

    # ── Project Archiving ────────────────────────────────────────
    def pack_project(self, source_path: str):
        src = Path(source_path).resolve()
        if not src.exists():
            print(f"❌ Path not found: {source_path}")
            return

        archive_dir = Path(config.ARCHIVE_DIR)
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Check for .gbhignore
        extra_ignore: set[str] = set()
        gbhignore = src / ".gbhignore"
        if gbhignore.exists():
            for line in gbhignore.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    extra_ignore.add(line)

        ts = datetime.now().strftime("%Y-%m-%d")
        zip_name = f"{src.name}_{ts}.zip"
        zip_path = archive_dir / zip_name
        ignore = BLACKLIST | extra_ignore

        self.log(f"Packing: {src.name}")
        self.log(f"Ignoring: {', '.join(sorted(ignore))}")

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d not in ignore]
                    for fn in files:
                        if fn in ignore or fn.startswith("."):
                            continue
                        fp = Path(root) / fn
                        zf.write(fp, fp.relative_to(src))

            size_mb = zip_path.stat().st_size / (1024 * 1024)
            self.log(f"Done! → {zip_path} ({size_mb:.2f} MB)")
        except Exception as e:
            print(f"❌ Pack failed: {e}")

    # ── Dotfile Backup ───────────────────────────────────────────
    def backup_config(self):
        backup_dir = Path(config.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Timestamped snapshot folder
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        snapshot_dir = backup_dir / ts
        snapshot_dir.mkdir()

        manifest: list[dict] = []
        self.log(f"Backing up dotfiles → {snapshot_dir}")

        for path_str in config.DOTFILES_TO_BACKUP:
            src = Path(path_str).expanduser()
            if src.exists():
                dest = snapshot_dir / src.name
                shutil.copy2(str(src), str(dest))
                mtime = datetime.fromtimestamp(src.stat().st_mtime).isoformat()
                manifest.append({"file": str(src), "mtime": mtime})
                print(f"   ✅ {src.name}", flush=True)
            else:
                print(f"   ⚠️  Not found: {path_str}", flush=True)

        (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        self.log(f"Snapshot saved: {ts}")

    def list_backups(self) -> list[str]:
        backup_dir = Path(config.BACKUP_DIR)
        if not backup_dir.exists():
            return []
        return sorted(
            [d.name for d in backup_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

    def restore_backup(self, snapshot: str):
        backup_dir = Path(config.BACKUP_DIR) / snapshot
        if not backup_dir.exists():
            print(f"❌ Snapshot not found: {snapshot}")
            return

        manifest_file = backup_dir / "manifest.json"
        if not manifest_file.exists():
            print("❌ Manifest missing in snapshot.")
            return

        manifest = json.loads(manifest_file.read_text())
        self.log(f"Restoring from snapshot: {snapshot}")

        for entry in manifest:
            src_file = backup_dir / Path(entry["file"]).name
            dest = Path(entry["file"])
            if src_file.exists():
                shutil.copy2(str(src_file), str(dest))
                print(f"   ✅ Restored: {dest}", flush=True)
            else:
                print(f"   ⚠️  Missing in snapshot: {src_file.name}", flush=True)

        self.log("Restore complete.")