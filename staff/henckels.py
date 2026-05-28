"""
Henckels — Network Sentinel
Monitors internet connectivity and WiFi network changes.
Notifies on outages, recoveries, and unknown networks. Always running.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify

GBH_DATA      = Path.home() / ".gbh"
CHECK_INTERVAL = 30   # seconds
PING_HOST      = "1.1.1.1"
PING_TIMEOUT   = 3




def _is_online() -> bool:
    try:
        socket.setdefaulttimeout(PING_TIMEOUT)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((PING_HOST, 53))
        return True
    except OSError:
        return False


def _get_wifi_ssid() -> str | None:
    try:
        result = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if " SSID:" in line:
                return line.split("SSID:")[-1].strip()
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["networksetup", "-getairportnetwork", "en0"],
            capture_output=True, text=True, timeout=3
        )
        if "Current Wi-Fi Network:" in result.stdout:
            return result.stdout.split("Current Wi-Fi Network:")[-1].strip()
    except Exception:
        pass
    return None


def _known_networks() -> set[str]:
    f = GBH_DATA / "known_networks.txt"
    if not f.exists():
        return set()
    return set(f.read_text().splitlines())


def _save_known_networks(networks: set[str]):
    GBH_DATA.mkdir(exist_ok=True)
    (GBH_DATA / "known_networks.txt").write_text("\n".join(sorted(networks)))


def run():
    print("🎖️ Henckels: Network sentinel active.", flush=True)

    was_online   = _is_online()
    last_ssid    = _get_wifi_ssid()
    known        = _known_networks()

    if last_ssid and last_ssid not in known:
        known.add(last_ssid)
        _save_known_networks(known)

    while True:
        time.sleep(CHECK_INTERVAL)

        online = _is_online()
        ssid   = _get_wifi_ssid()

        # ── Connectivity changes ──────────────────────────────────
        if was_online and not online:
            notify("Henckels", "Connection lost.")
            print("❌ Internet went down", flush=True)
        elif not was_online and online:
            notify("Henckels", f"Back online{(' on ' + ssid) if ssid else ''}.")
            print("✅ Internet restored", flush=True)
        was_online = online

        # ── WiFi network changes ──────────────────────────────────
        if ssid and ssid != last_ssid:
            if ssid not in known:
                notify("Henckels", f"Joined unknown network: {ssid}")
                print(f"⚠️  Unknown network: {ssid}", flush=True)
                known.add(ssid)
                _save_known_networks(known)
            else:
                print(f"📶 Switched to: {ssid}", flush=True)
            last_ssid = ssid


if __name__ == "__main__":
    run()
