"""
Ivan — Focus Mode Manager
Blocks distracting sites by running a local block-proxy server and routing
all blocked domains to it via a PAC file + networksetup.

No sudo required. When a blocked site is requested the browser hits the
local proxy, which returns an HTTP 403 block page (or refuses the CONNECT
tunnel for HTTPS). Because the proxy IS listening there is no DIRECT fallback.
"""

import json
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

GBH_DATA         = Path.home() / ".gbh"
FOCUS_STATE_FILE = GBH_DATA / "focus_state.json"
PAC_FILE         = GBH_DATA / "ivan_block.pac"
BLOCK_PORT       = 2526   # local proxy port — must not conflict with 2525 (dashboard)

LOOP_TICK_SEC = 5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from staff.notify import notify as _send_notify

# ── Block-page content ────────────────────────────────────────────

_BLOCK_HTML = b"""\
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Focus Mode</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e2e2e2;font-family:-apple-system,sans-serif;
     display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{text-align:center;padding:3rem 2rem;max-width:420px}
h1{color:#c9a84c;font-size:2rem;margin-bottom:.5rem;letter-spacing:.04em}
p{color:#888;font-size:.95rem;line-height:1.6;margin-top:.75rem}
code{background:#1c1c1c;color:#c9a84c;padding:.15em .4em;border-radius:4px;font-size:.9em}
</style></head>
<body><div class="card">
  <h1>&#x1F515; Focus Mode</h1>
  <p>Ivan has blocked this site.</p>
  <p>Run <code>gbh focus pause</code> if you need a break,<br>
     or <code>gbh focus stop</code> to end the session.</p>
</div></body></html>
"""

_HTTP_RESPONSE = (
    b"HTTP/1.1 403 Forbidden\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"Content-Length: " + str(len(_BLOCK_HTML)).encode() + b"\r\n"
    b"Connection: close\r\n"
    b"\r\n"
) + _BLOCK_HTML

# For HTTPS CONNECT tunnels — browser shows a connection-refused style error.
_CONNECT_DENY = b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


# ── Block-proxy server ────────────────────────────────────────────

_stop_event: threading.Event | None = None


def _handle_conn(conn: socket.socket) -> None:
    try:
        conn.settimeout(5)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            chunk = conn.recv(512)
            if not chunk:
                break
            data += chunk
        # Serve PAC file over HTTP so Chrome/Safari will actually load it
        # (browsers reject file:// PAC URLs since ~2018)
        if b"GET /ivan.pac" in data:
            pac_content = PAC_FILE.read_bytes() if PAC_FILE.exists() else b""
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/x-ns-proxy-autoconfig\r\n"
                b"Content-Length: " + str(len(pac_content)).encode() + b"\r\n"
                b"Cache-Control: no-cache\r\n"
                b"Connection: close\r\n"
                b"\r\n"
            ) + pac_content
            conn.sendall(response)
        elif data.upper().startswith(b"CONNECT"):
            conn.sendall(_CONNECT_DENY)
        elif data:
            conn.sendall(_HTTP_RESPONSE)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _run_server(stop: threading.Event) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", BLOCK_PORT))
    except OSError:
        return   # another process already has it — that's fine
    srv.listen(32)
    srv.settimeout(1.0)
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle_conn, args=(conn,), daemon=True).start()
        except socket.timeout:
            continue
        except Exception:
            break
    try:
        srv.close()
    except Exception:
        pass


def _server_is_running() -> bool:
    """Return True if a block-proxy is already listening on BLOCK_PORT."""
    try:
        s = socket.create_connection(("127.0.0.1", BLOCK_PORT), timeout=0.3)
        s.close()
        return True
    except OSError:
        return False


def _start_block_server() -> threading.Event | None:
    """Start the local block proxy if not already running. Returns the stop event."""
    global _stop_event
    if _server_is_running():
        return None   # already up (another process)
    _stop_event = threading.Event()
    t = threading.Thread(target=_run_server, args=(_stop_event,), daemon=True)
    t.start()
    time.sleep(0.15)   # give it time to bind
    return _stop_event


def _stop_block_server() -> None:
    global _stop_event
    if _stop_event:
        _stop_event.set()
        _stop_event = None


# ── Network helpers ───────────────────────────────────────────────

def _network_services() -> list[str]:
    try:
        r = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True, timeout=5,
        )
        return [
            line.strip() for line in r.stdout.splitlines()
            if line.strip() and not line.startswith("An asterisk") and not line.startswith("*")
        ] or ["Wi-Fi"]
    except Exception:
        return ["Wi-Fi"]


def _write_pac(blocklist: list[str]) -> str:
    domains: set[str] = set()
    for d in blocklist:
        d = d.lower()
        domains.add(d)
        if not d.startswith("www."):
            domains.add("www." + d)

    entries = ",\n    ".join(f'"{d}"' for d in sorted(domains))
    pac = f"""\
// GBH Ivan — focus mode block list (auto-generated)
function FindProxyForURL(url, host) {{
    var blocked = [
    {entries}
    ];
    var h = host.toLowerCase();
    for (var i = 0; i < blocked.length; i++) {{
        if (h === blocked[i] || h.endsWith("." + blocked[i])) {{
            return "PROXY 127.0.0.1:{BLOCK_PORT}";
        }}
    }}
    return "DIRECT";
}}
"""
    GBH_DATA.mkdir(exist_ok=True)
    PAC_FILE.write_text(pac)
    return str(PAC_FILE)


def _block_sites(blocklist: list[str]) -> bool:
    """Start block server + enable PAC proxy on every network service."""
    _start_block_server()

    if not _server_is_running():
        print(f"❌ Could not start block server on port {BLOCK_PORT}.")
        return False

    _write_pac(blocklist)
    # Use HTTP URL so Chrome/Safari will actually fetch and apply the PAC.
    # Browsers silently ignore file:// PAC URLs (security restriction since ~2018).
    pac_url = f"http://127.0.0.1:{BLOCK_PORT}/ivan.pac"
    ok = False
    for svc in _network_services():
        try:
            r1 = subprocess.run(
                ["networksetup", "-setautoproxyurl", svc, pac_url],
                capture_output=True, timeout=5,
            )
            r2 = subprocess.run(
                ["networksetup", "-setautoproxystate", svc, "on"],
                capture_output=True, timeout=5,
            )
            if r1.returncode == 0 and r2.returncode == 0:
                ok = True
        except Exception:
            pass
    return ok


def _unblock_sites() -> None:
    """Disable PAC proxy, stop block server, delete PAC file."""
    for svc in _network_services():
        try:
            subprocess.run(
                ["networksetup", "-setautoproxystate", svc, "off"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
    _stop_block_server()
    if PAC_FILE.exists():
        PAC_FILE.unlink(missing_ok=True)


# ── State helpers ─────────────────────────────────────────────────

def _read_state() -> dict | None:
    if not FOCUS_STATE_FILE.exists():
        return None
    try:
        return json.loads(FOCUS_STATE_FILE.read_text())
    except Exception:
        return None


def _write_state(state: dict) -> None:
    GBH_DATA.mkdir(exist_ok=True)
    FOCUS_STATE_FILE.write_text(json.dumps(state))


def _clear_state() -> None:
    if FOCUS_STATE_FILE.exists():
        FOCUS_STATE_FILE.unlink()


# ── Ivan class ────────────────────────────────────────────────────

class Ivan:

    def start(self, minutes: int, blocklist: list[str]) -> None:
        state = _read_state()
        if state and state.get("active"):
            if state.get("paused"):
                print("⚠️  A paused session exists. Use `gbh focus resume` or `gbh focus stop`.")
            else:
                ends_at   = datetime.fromisoformat(state["ends_at"])
                remaining = max(0, int((ends_at - datetime.now()).total_seconds() // 60))
                print(f"⚠️  Focus already active — {remaining}m remaining.")
            return

        print(f"🔕 Ivan: Starting {minutes}-minute focus session…")

        # Write state BEFORE the slow networksetup calls so the dashboard
        # can reflect the session immediately; roll back on failure.
        ends_at = datetime.now() + timedelta(minutes=minutes)
        _write_state({
            "active": True,
            "started_at": datetime.now().isoformat(),
            "ends_at": ends_at.isoformat(),
            "duration_min": minutes,
            "blocklist": blocklist,
            "paused": False,
            "paused_at": None,
            "remaining_at_pause_sec": None,
        })

        if not _block_sites(blocklist):
            _clear_state()
            return

        _send_notify("Ivan", f"Blocking distractions for {minutes} minutes.")
        print(f"✅ Focus active until {ends_at.strftime('%I:%M %p')}. Sites blocked.")

        try:
            while True:
                s = _read_state()
                if not s or not s.get("active"):
                    return                   # stop() was called externally
                if s.get("paused"):
                    time.sleep(LOOP_TICK_SEC)
                    continue
                if datetime.now() >= datetime.fromisoformat(s["ends_at"]):
                    break
                time.sleep(LOOP_TICK_SEC)
        except KeyboardInterrupt:
            pass

        self.stop(send_notify=True)

    def pause(self) -> None:
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No active focus session.")
            return
        if state.get("paused"):
            print("ℹ️  Already paused.")
            return

        ends_at   = datetime.fromisoformat(state["ends_at"])
        remaining = max(0, int((ends_at - datetime.now()).total_seconds()))

        _unblock_sites()
        state.update({
            "paused": True,
            "paused_at": datetime.now().isoformat(),
            "remaining_at_pause_sec": remaining,
        })
        _write_state(state)

        mins, secs = divmod(remaining, 60)
        _send_notify("Ivan", f"Paused — {mins}m {secs}s left.")
        print(f"⏸️  Paused — {mins}m {secs}s left. Sites unblocked.")

    def resume(self) -> None:
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No session to resume.")
            return
        if not state.get("paused"):
            print("ℹ️  Not paused.")
            return

        remaining = int(state.get("remaining_at_pause_sec") or 0)
        if remaining <= 0:
            print("ℹ️  No time left — ending session.")
            _clear_state()
            return

        if not _block_sites(state.get("blocklist", [])):
            return

        new_ends_at = datetime.now() + timedelta(seconds=remaining)
        state.update({
            "paused": False,
            "paused_at": None,
            "remaining_at_pause_sec": None,
            "ends_at": new_ends_at.isoformat(),
        })
        _write_state(state)

        mins, secs = divmod(remaining, 60)
        _send_notify("Ivan", f"Resumed — {mins}m {secs}s to go.")
        print(f"▶️  Resumed until {new_ends_at.strftime('%I:%M %p')}.")

    def stop(self, send_notify: bool = False) -> None:
        state = _read_state()
        if not state or not state.get("active"):
            print("ℹ️  No active session.")
            return

        if not state.get("paused"):
            _unblock_sites()
        _clear_state()

        if send_notify:
            _send_notify("Ivan", "Great work. Sites unblocked.")
        print("✅ Session ended. Sites unblocked.")

    def status(self) -> dict:
        state = _read_state()
        if not state or not state.get("active"):
            return {"active": False, "paused": False, "remaining_sec": 0,
                    "duration_min": 0, "ends_at": None}

        if state.get("paused"):
            return {
                "active": True, "paused": True,
                "remaining_sec": int(state.get("remaining_at_pause_sec") or 0),
                "duration_min": state.get("duration_min", 25),
                "ends_at": state.get("ends_at"),
            }

        ends_at   = datetime.fromisoformat(state["ends_at"])
        remaining = max(0, int((ends_at - datetime.now()).total_seconds()))

        if remaining == 0:
            # Expired (e.g. Mac restarted mid-session) — clean up safely.
            _unblock_sites()
            _clear_state()
            return {"active": False, "paused": False, "remaining_sec": 0,
                    "duration_min": 0, "ends_at": None}

        return {
            "active": True, "paused": False,
            "remaining_sec": remaining,
            "duration_min": state.get("duration_min", 25),
            "ends_at": state.get("ends_at"),
        }

    def pomodoro(self, blocklist: list[str], cycles: int = 4) -> None:
        from config import FOCUS_DEFAULT_MINUTES, FOCUS_BREAK_MINUTES
        print(f"🍅 Pomodoro: {cycles} × {FOCUS_DEFAULT_MINUTES}m focus / {FOCUS_BREAK_MINUTES}m break")
        for i in range(cycles):
            print(f"\n── Cycle {i + 1}/{cycles} ──")
            self.start(FOCUS_DEFAULT_MINUTES, blocklist)
            if i < cycles - 1:
                _send_notify("Ivan", f"Break — {FOCUS_BREAK_MINUTES} minutes.")
                print(f"☕ Break for {FOCUS_BREAK_MINUTES} minutes…")
                time.sleep(FOCUS_BREAK_MINUTES * 60)
        _send_notify("Ivan", f"All {cycles} cycles done. Excellent focus!")
        print("\n🎉 Pomodoro complete!")
