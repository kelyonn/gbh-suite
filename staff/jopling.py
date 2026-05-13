"""
Jopling — Silent Enforcer
Watches for runaway processes (CPU hogs, memory leaks).
Notifies and optionally kills offenders. Always running.
"""

import os
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify

GBH_DATA = Path.home() / ".gbh"

# Thresholds
CPU_THRESHOLD   = 85.0   # % CPU sustained for this many seconds triggers alert
CPU_WINDOW_SEC  = 120    # 2 minutes
RAM_THRESHOLD   = 88.0   # % total RAM
CHECK_INTERVAL  = 15     # seconds between checks

# Processes to never alert on (system/known-heavy)
WHITELIST = {"kernel_task", "mds", "mds_stores", "Spotlight", "com.apple.WebKit"}




def run():
    print("🔪 Jopling: Watching for runaway processes...", flush=True)

    # pid → list of (timestamp, cpu%) samples
    cpu_history: dict[int, list[tuple[float, float]]] = {}
    alerted_cpu: set[int]  = set()
    alerted_ram: bool      = False

    while True:
        now = time.time()

        # ── RAM check ────────────────────────────────────────────
        mem = psutil.virtual_memory()
        if mem.percent >= RAM_THRESHOLD and not alerted_ram:
            # Find top offender
            procs = sorted(
                psutil.process_iter(["name", "memory_percent"]),
                key=lambda p: p.info.get("memory_percent") or 0,
                reverse=True,
            )
            top = next((p for p in procs if p.info.get("name") not in WHITELIST), None)
            msg = f"RAM at {mem.percent:.0f}%"
            if top:
                msg += f" — {top.info['name']} using {top.info['memory_percent']:.1f}%"
            notify("Jopling", msg)
            alerted_ram = True
        elif mem.percent < RAM_THRESHOLD - 5:
            alerted_ram = False

        # ── CPU sustained check ───────────────────────────────────
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                pid  = proc.info["pid"]
                name = proc.info["name"] or ""
                cpu  = proc.info["cpu_percent"] or 0.0

                if name in WHITELIST or cpu < CPU_THRESHOLD:
                    cpu_history.pop(pid, None)
                    continue

                history = cpu_history.setdefault(pid, [])
                history.append((now, cpu))

                # Prune old samples
                history[:] = [(t, c) for t, c in history if now - t <= CPU_WINDOW_SEC]

                if len(history) >= (CPU_WINDOW_SEC // CHECK_INTERVAL) and pid not in alerted_cpu:
                    avg = sum(c for _, c in history) / len(history)
                    notify("Jopling", f"{name} has been at {avg:.0f}% CPU for {CPU_WINDOW_SEC//60}+ minutes")
                    alerted_cpu.add(pid)
                    print(f"⚠️  Alerted: {name} (PID {pid}) avg CPU {avg:.0f}%", flush=True)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Clean up dead PIDs from alerted set
        live_pids = {p.pid for p in psutil.process_iter(["pid"])}
        alerted_cpu &= live_pids

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
