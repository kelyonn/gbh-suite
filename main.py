import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from staff import (
    agatha,
    clotilde,
    dimitri,
    gustave,
    henckels,
    ivan,
    jopling,
    kovacs,
    ludwig,
    serge,
    zero,
)


def main():
    if len(sys.argv) < 2:
        g = gustave.Gustave()
        g.report()
        return

    command = sys.argv[1].lower()

    # ── Gustave ───────────────────────────────────────────────────
    if command in ("status", "briefing"):
        g = gustave.Gustave()
        if "--notify" in sys.argv:
            g.notify()
        else:
            g.report()

    elif command == "compact":
        gustave.Gustave().compact()

    # ── Serge ─────────────────────────────────────────────────────
    elif command == "sort":
        serge.start_watch()

    elif command == "undo":
        n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
        results = serge.undo_last_moves(n)
        for r in results:
            print(r)

    # ── Zero ──────────────────────────────────────────────────────
    elif command == "clean":
        z = zero.Zero()
        if "--dupes" in sys.argv:
            target = os.path.expanduser(sys.argv[sys.argv.index("--dupes") + 1]) \
                if sys.argv.index("--dupes") + 1 < len(sys.argv) \
                else os.path.expanduser("~/Downloads")
            z.find_duplicates(target)
        elif "--old" in sys.argv:
            days = int(sys.argv[sys.argv.index("--old") + 1]) \
                if sys.argv.index("--old") + 1 < len(sys.argv) \
                else config.OLD_DOWNLOADS_DAYS
            z.archive_old_downloads(days)
        else:
            z.clean_screenshots(days_old=1)

    elif command == "large":
        z = zero.Zero()
        directory = sys.argv[2] if len(sys.argv) > 2 else None
        files = z.find_large_files(directory)
        if not files:
            print("✨ No large files found.")
        else:
            print(f"\n📦 {len(files)} large file(s) found:\n")
            for f in files[:30]:
                print(f"  {f['size_mb']:>7.1f} MB  {f['path']}")

    # ── Dimitri ───────────────────────────────────────────────────
    elif command == "patrol":
        guard = dimitri.Dimitri()
        guard.start_patrol(config.PERMANENT_PORTS, config.PERMANENT_LOGS)

    elif command == "wait":
        if len(sys.argv) < 3 or not sys.argv[2].isdigit():
            print("Usage: gbh wait <port>")
            return
        guard = dimitri.Dimitri()
        guard.wait_for_port(int(sys.argv[2]))

    elif command == "watch":
        if len(sys.argv) < 3:
            print("Usage: gbh watch <file>")
            return
        guard = dimitri.Dimitri()
        guard.watch_log(sys.argv[2])

    # ── Ivan ──────────────────────────────────────────────────────
    elif command == "focus":
        iv = ivan.Ivan()
        if len(sys.argv) > 2 and sys.argv[2] == "stop":
            iv.stop()
        elif len(sys.argv) > 2 and sys.argv[2] == "pause":
            iv.pause()
        elif len(sys.argv) > 2 and sys.argv[2] == "resume":
            iv.resume()
        elif len(sys.argv) > 2 and sys.argv[2] == "status":
            status = iv.status()
            if status["active"]:
                mins = status["remaining_sec"] // 60
                secs = status["remaining_sec"] % 60
                label = "paused" if status.get("paused") else "active"
                print(f"🔕 Focus {label} — {mins}m {secs}s remaining")
            else:
                print("✅ No active focus session.")
        elif len(sys.argv) > 2 and sys.argv[2] == "pomodoro":
            cycles = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 4
            iv.pomodoro(config.FOCUS_BLOCKLIST, cycles)
        else:
            minutes = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else config.FOCUS_DEFAULT_MINUTES
            iv.start(minutes, config.FOCUS_BLOCKLIST)

    # ── Agatha ────────────────────────────────────────────────────
    elif command == "pack":
        target = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
        agatha.Agatha().pack_project(target)

    elif command == "backup":
        agatha.Agatha().backup_config()

    elif command == "restore":
        a = agatha.Agatha()
        backups = a.list_backups()
        if not backups:
            print("No backups found.")
            return
        if len(sys.argv) > 2:
            a.restore_backup(sys.argv[2])
        else:
            print("Available snapshots:")
            for i, b in enumerate(backups):
                print(f"  [{i+1}] {b}")
            choice = input("Restore which? (number): ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(backups):
                    a.restore_backup(backups[idx])

    # ── New Staff ─────────────────────────────────────────────────
    elif command == "jopling":
        jopling.run()

    elif command == "henckels":
        henckels.run()

    elif command == "kovacs":
        kovacs.run()

    elif command == "clotilde":
        clotilde.run()

    elif command == "ludwig":
        ludwig.run()

    # ── Misc ──────────────────────────────────────────────────────
    elif command == "open":
        subprocess.run(["open", f"http://{config.SERVER_HOST}:{config.SERVER_PORT}"])

    elif command == "stop":
        print("🔫 Stopping all GBH background tasks...")
        # Match the actual cmdline: python3.11 .../main.py <subcommand>
        for sub in ("sort", "patrol", "jopling", "henckels"):
            os.system(f"pkill -f 'main.py {sub}'")
        os.system("pkill -f 'uvicorn server:app'")
        print("   Done.")

    else:
        print("""
🏨 Grand Budapest Hotel — v2

  gbh                      Morning briefing (Gustave)
  gbh sort                 Start file sorter (Serge)
  gbh undo [n]             Undo last N Serge moves
  gbh clean                Sweep screenshots (Zero)
  gbh clean --dupes [dir]  Find duplicates
  gbh clean --old [days]   Archive old downloads
  gbh large [dir]          Find large files
  gbh patrol               Start port/log sentinel (Dimitri)
  gbh wait <port>          Notify when port opens
  gbh watch <file>         Watch log file for errors
  gbh focus [minutes]      Start focus mode (Ivan)
  gbh focus pause          Pause — unblock sites, freeze timer
  gbh focus resume         Resume the paused session
  gbh focus stop           End focus session
  gbh focus status         Show remaining time
  gbh focus pomodoro [n]   Pomodoro cycles
  gbh pack [path]          Archive project (Agatha)
  gbh backup               Backup dotfiles
  gbh restore [snapshot]   Restore dotfiles
  gbh open                 Open dashboard in browser
  gbh stop                 Kill background tasks
""")


if __name__ == "__main__":
    main()
