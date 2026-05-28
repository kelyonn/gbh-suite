"""
Dimitri v2 — Port, Log & Process Sentinel
Watches ports, HTTP health endpoints, log files, and processes.
"""

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from staff.notify import notify




class Dimitri:

    # ── Port Waiter ──────────────────────────────────────────────
    def wait_for_port(self, port: int):
        """Notify once when a port starts accepting connections."""
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    notify("Dimitri", f"Port {port} is now active.")
                    return
            except OSError:
                time.sleep(2)

    # ── HTTP Health Check ─────────────────────────────────────────
    def watch_health_url(self, url: str):
        """Notify when a URL returns non-200 (degraded) or recovers."""
        last_ok = True
        while True:
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    ok = (r.status == 200)
            except Exception:
                ok = False

            if not ok and last_ok:
                notify("Dimitri", f"Health check failed: {url}")
            elif ok and not last_ok:
                notify("Dimitri", f"Back online: {url}")
            last_ok = ok
            time.sleep(15)

    # ── Log Watcher ──────────────────────────────────────────────
    def watch_log(self, filepath: str):
        """Tail a log file and notify on errors, debounced."""
        if not os.path.exists(filepath):
            return
        triggers = ["error", "exception", "traceback", "failed", "critical"]
        recent: deque = deque(maxlen=100)  # track recent error times
        cooldown = 60  # seconds between repeated alerts for same file

        try:
            with open(filepath, "r") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        continue
                    if any(t in line.lower() for t in triggers):
                        now = time.time()
                        recent.append(now)
                        # Only alert if not alerted in last cooldown seconds
                        alerts_in_window = sum(1 for t in recent if now - t < cooldown)
                        if alerts_in_window == 1:
                            count = sum(1 for t in recent if now - t < 300)
                            suffix = f" ({count} in 5m)" if count > 1 else ""
                            notify("Dimitri", f"{os.path.basename(filepath)}: Error detected{suffix}"
                            )
        except Exception:
            pass

    # ── Process Watchdog ─────────────────────────────────────────
    def watch_process(self, name: str, restart_cmd: list[str] | None = None):
        """Monitor a process by name substring. Restart if it dies."""
        import psutil
        was_running = False
        while True:
            running = any(
                name in " ".join(p.info.get("cmdline") or [])
                for p in psutil.process_iter(["cmdline"])
                if not isinstance(p.info.get("cmdline"), type(None))
            )
            if was_running and not running:
                notify("Dimitri", f"{name} has stopped.")
                if restart_cmd:
                    try:
                        subprocess.Popen(restart_cmd, start_new_session=True)
                        notify("Dimitri", f"Relaunched: {name}")
                    except Exception as e:
                        notify("Dimitri", str(e))
            was_running = running
            time.sleep(10)

    # ── Patrol (Main LaunchAgent entry) ──────────────────────────
    def start_patrol(self, ports: list, logs: list):
        print("🕵️ Dimitri v2 starting patrol...", flush=True)

        threads: list[threading.Thread] = []

        for port in ports:
            t = threading.Thread(target=self.wait_for_port, args=(port,), daemon=True)
            t.start()
            threads.append(t)
            print(f"   📡 Watching port {port}", flush=True)

        for url in getattr(config, "HEALTH_CHECK_URLS", []):
            t = threading.Thread(target=self.watch_health_url, args=(url,), daemon=True)
            t.start()
            threads.append(t)
            print(f"   🏥 Health check: {url}", flush=True)

        for log_path in logs:
            if os.path.exists(log_path):
                t = threading.Thread(target=self.watch_log, args=(log_path,), daemon=True)
                t.start()
                threads.append(t)
                print(f"   📋 Watching log: {os.path.basename(log_path)}", flush=True)

        for proc_name in getattr(config, "WATCHDOG_PROCESSES", []):
            t = threading.Thread(target=self.watch_process, args=(proc_name,), daemon=True)
            t.start()
            threads.append(t)
            print(f"   🔍 Watching process: {proc_name}", flush=True)

        print("✅ Patrol active.", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass