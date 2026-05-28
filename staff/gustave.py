"""
Gustave v2 — Morning Briefing
System vitals, git status, Docker, ports, weather, top processes.
"""

import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify

# ── Colour palette ────────────────────────────────────────────────────────────
# Using true 24-bit ANSI where possible; falls back fine on most terminals.

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Warm gold — brand colour
    GOLD    = "\033[38;2;212;175;55m"
    GOLD_DK = "\033[38;2;140;110;30m"

    # Semantic
    OK      = "\033[38;2;74;222;128m"    # soft green
    WARN    = "\033[38;2;251;191;36m"    # amber
    ERR     = "\033[38;2;248;113;113m"   # soft red
    INFO    = "\033[38;2;147;197;253m"   # sky blue

    # Neutral
    TEXT    = "\033[38;2;229;229;229m"
    SUBTEXT = "\033[38;2;140;140;140m"
    FAINT   = "\033[38;2;70;70;70m"


def c(text: str, *codes: str) -> str:
    return "".join(codes) + text + C.RESET


def _bar(pct: float, width: int = 18) -> str:
    filled = round(width * min(pct, 100) / 100)
    empty  = width - filled
    if pct > 85:
        colour = C.ERR
    elif pct > 65:
        colour = C.WARN
    else:
        colour = C.OK
    return colour + "█" * filled + C.FAINT + "░" * empty + C.RESET




# ── Layout helpers ────────────────────────────────────────────────────────────

WIDTH = 60

def _blank():
    print()

def _rule(char: str = "─"):
    print(c("  " + char * (WIDTH - 2), C.FAINT))

def _section(title: str):
    _blank()
    print(c(f"  {title}", C.GOLD, C.BOLD))
    print(c("  " + "─" * len(title), C.GOLD_DK))

def _row(label: str, value: str, note: str = ""):
    label_str = c(f"  {label:<10}", C.SUBTEXT)
    note_str  = c(f"  {note}", C.SUBTEXT) if note else ""
    print(f"{label_str} {value}{note_str}")


# ── Gustave ───────────────────────────────────────────────────────────────────

class Gustave:

    def _header(self):
        now_date = datetime.now().strftime("%A, %d %B %Y")
        now_time = datetime.now().strftime("%I:%M %p")

        _blank()
        print(c("  ━" * (WIDTH // 2), C.GOLD_DK))
        _blank()
        print(c("  🏨  GRAND BUDAPEST HOTEL", C.GOLD, C.BOLD))
        print(c(f"      Morning Briefing  ·  {now_date}  ·  {now_time}", C.SUBTEXT))
        _blank()
        print(c("  ━" * (WIDTH // 2), C.GOLD_DK))

    def check_vitals(self):
        _section("System")

        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        _, _, free = shutil.disk_usage("/")
        free_gb = free // (2 ** 30)

        cpu_val = c(f"{cpu:>5.1f}%", C.WARN if cpu > 70 else C.TEXT)
        ram_val = c(f"{mem.percent:>5.1f}%", C.WARN if mem.percent > 75 else C.TEXT)
        dsk_col = C.ERR if free_gb < 15 else (C.WARN if free_gb < 30 else C.OK)
        dsk_val = c(f"{free_gb} GB free", dsk_col)

        _blank()
        _row("CPU",  f"{_bar(cpu)}  {cpu_val}")
        _blank()
        _row("RAM",  f"{_bar(mem.percent)}  {ram_val}")
        _blank()
        _row("Disk", f"  {dsk_val}")

        try:
            bat = psutil.sensors_battery()
            if bat:
                pct    = bat.percent
                status = c("⚡ charging", C.OK) if bat.power_plugged else c("on battery", C.WARN if pct < 30 else C.SUBTEXT)
                bat_val = c(f"{pct:.0f}%", C.ERR if pct < 15 else C.TEXT)
                _blank()
                _row("Battery", f"{_bar(pct)}  {bat_val}", f"  {status}")
        except Exception:
            pass

        # Top 3 memory hogs
        try:
            procs = sorted(
                psutil.process_iter(["name", "memory_percent"]),
                key=lambda p: p.info.get("memory_percent") or 0,
                reverse=True,
            )
            top3 = [
                (p.info["name"][:22], p.info["memory_percent"])
                for p in procs[:5]
                if p.info.get("name") and p.info.get("memory_percent", 0) > 0.1
            ][:3]
            if top3:
                _blank()
                hog_str = c("  Top procs  ", C.SUBTEXT)
                parts   = [c(f"{n}", C.TEXT) + c(f" {m:.1f}%", C.SUBTEXT) for n, m in top3]
                print(f"  {hog_str}  {'   ·   '.join(parts)}")
        except Exception:
            pass



    def check_ports(self):
        _section("Ports")
        _blank()
        active, quiet = [], []
        for port in config.CRITICAL_PORTS:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    active.append(port)
            except OSError:
                quiet.append(port)

        if active:
            active_str = "  ".join(c(f":{p}", C.OK) for p in active)
            print(f"  {c('Active   ', C.SUBTEXT)}  {active_str}")
            _blank()

        if quiet:
            quiet_str  = "  ".join(c(f":{p}", C.FAINT) for p in quiet)
            print(f"  {c('Quiet    ', C.SUBTEXT)}  {quiet_str}")
        elif not active:
            print(c("  All ports quiet", C.SUBTEXT))

    def check_docker(self):
        _section("Docker")
        _blank()
        try:
            res = subprocess.run(
                ["docker", "ps", "-q"], capture_output=True, text=True, timeout=3
            )
            if res.returncode != 0:
                print(c("  Daemon not running", C.SUBTEXT))
            else:
                count = len(res.stdout.splitlines())
                if count:
                    print(f"  {c(str(count), C.WARN)}  {c('container(s) active', C.TEXT)}")
                else:
                    print(c("  No containers running", C.SUBTEXT))
        except FileNotFoundError:
            print(c("  Not installed", C.SUBTEXT))
        except subprocess.TimeoutExpired:
            print(c("  Timed out", C.SUBTEXT))

    def check_git(self):
        _section("Projects")
        _blank()
        projects = Path(config.PROJECTS_DIR)
        if not projects.exists():
            print(c("  Projects directory not found", C.SUBTEXT))
            return

        clean, dirty, unpushed = [], [], []
        for item in sorted(projects.iterdir()):
            if not (item.is_dir() and (item / ".git").exists()):
                continue
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(item),
                capture_output=True, text=True
            ).stdout.strip()
            ahead_raw = subprocess.run(
                ["git", "rev-list", "--count", "@{u}..HEAD"],
                cwd=str(item), capture_output=True, text=True
            ).stdout.strip()
            ahead = int(ahead_raw) if ahead_raw.isdigit() else 0

            if status:
                dirty.append(item.name)
            elif ahead:
                unpushed.append((item.name, ahead))
            else:
                clean.append(item.name)

        total = len(clean) + len(dirty) + len(unpushed)
        print(f"  {c(str(total), C.TEXT)} repo(s) found\n")

        if dirty:
            for name in dirty:
                print(f"  {c('●', C.WARN)}  {c(name, C.TEXT)}{c('  uncommitted changes', C.SUBTEXT)}")
        if unpushed:
            for name, n in unpushed:
                print(f"  {c('↑', C.INFO)}  {c(name, C.TEXT)}{c(f'  {n} commit(s) ahead', C.SUBTEXT)}")
        if clean:
            clean_str = c(f"  {len(clean)} clean", C.OK)
            names     = c("  " + ", ".join(clean[:4]) + ("…" if len(clean) > 4 else ""), C.SUBTEXT)
            print(f"{clean_str}{names}")

    def compact(self):
        """One-line status bar — shown on every new terminal. Fast (no git/docker/network)."""
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        _, _, free = shutil.disk_usage("/")
        free_gb = free // (2 ** 30)

        cpu_col  = C.ERR  if cpu > 80        else (C.WARN if cpu > 60  else C.OK)
        ram_col  = C.ERR  if mem.percent > 85 else (C.WARN if mem.percent > 70 else C.OK)
        disk_col = C.ERR  if free_gb < 15     else (C.WARN if free_gb < 30     else C.OK)

        parts = [
            c("🏨 GBH", C.GOLD, C.BOLD),
            c(f"CPU {cpu:.0f}%",       cpu_col),
            c(f"RAM {mem.percent:.0f}%", ram_col),
            c(f"Disk {free_gb}GB",     disk_col),
        ]

        try:
            bat = psutil.sensors_battery()
            if bat:
                icon = "⚡" if bat.power_plugged else "🔋"
                bat_col = C.ERR if bat.percent < 15 else (C.WARN if bat.percent < 30 else C.SUBTEXT)
                parts.append(c(f"{icon}{bat.percent:.0f}%", bat_col))
        except Exception:
            pass

        # Quick dirty repo count — fast because we only check porcelain, no network
        dirty = 0
        projects = Path(config.PROJECTS_DIR)
        if projects.exists():
            for item in projects.iterdir():
                if item.is_dir() and (item / ".git").exists():
                    r = subprocess.run(
                        ["git", "status", "--porcelain"], cwd=str(item),
                        capture_output=True, text=True, timeout=2
                    )
                    if r.stdout.strip():
                        dirty += 1

        if dirty:
            parts.append(c(f"● {dirty} dirty", C.WARN))

        sep = c("  ·  ", C.FAINT)
        print(sep.join(parts))

    def report(self):
        self._header()
        self.check_vitals()
        self.check_ports()
        self.check_docker()
        self.check_git()
        _blank()
        print(c("  ━" * (WIDTH // 2), C.GOLD_DK))
        _blank()

    def notify(self):
        try:
            mem = psutil.virtual_memory().percent
            _, _, free = shutil.disk_usage("/")
            free_gb = free // (2 ** 30)
            dirty_count = 0
            projects = Path(config.PROJECTS_DIR)
            if projects.exists():
                for item in projects.iterdir():
                    if item.is_dir() and (item / ".git").exists():
                        res = subprocess.run(
                            ["git", "status", "--porcelain"], cwd=str(item),
                            capture_output=True, text=True
                        )
                        if res.stdout.strip():
                            dirty_count += 1
            body = f"RAM {mem:.0f}% · Disk {free_gb}GB free"
            if dirty_count:
                body += f" · {dirty_count} dirty repo(s)"
            notify("Gustave", body)
        except Exception as e:
            print(f"❌ Notification error: {e}")


if __name__ == "__main__":
    g = Gustave()
    g.report()

