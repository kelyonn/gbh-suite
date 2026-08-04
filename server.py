"""
GBH Concierge Server v2 — FastAPI backend for the dashboard.
Real-time vitals, Serge feed, Ivan focus, Zero actions via REST + WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config  # noqa: E402
from staff import serge as serge_mod  # noqa: E402
from staff import zero as zero_mod  # noqa: E402
from staff.ivan import Ivan as IvanClass  # noqa: E402

BROADCAST_INTERVAL = 0.5
ZERO_CHECK_INTERVAL = 60
ZERO_LOG = BASE_DIR / "zero_last_run.txt"

# How many broadcast ticks between refreshes of the "slow" vitals (staff,
# ports, serge count) sent over the WebSocket — see the note above
# broadcast_loop() for why these are decoupled from the 0.5s fast tick.
SLOW_TICKS = round(5 / BROADCAST_INTERVAL)


# ── Data Models ──────────────────────────────────────────────────

@dataclass
class StaffStatus:
    serge: bool = False
    dimitri: bool = False
    jopling: bool = False
    henckels: bool = False
    server: bool = True


@dataclass
class FocusStatus:
    active: bool = False
    paused: bool = False
    remaining_sec: int = 0
    duration_min: int = 0
    ends_at: str | None = None


@dataclass
class Vitals:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    disk_free_gb: int = 0
    battery_percent: float | None = None
    battery_plugged: bool | None = None
    staff: StaffStatus = field(default_factory=StaffStatus)
    focus: FocusStatus = field(default_factory=FocusStatus)
    zero_last_run: str = "never"
    ports: list = field(default_factory=list)
    serge_moves_today: int = 0

    def to_dict(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_percent": round(self.ram_percent, 1),
            "disk_free": self.disk_free_gb,
            "battery_percent": self.battery_percent,
            "battery_plugged": self.battery_plugged,
            "staff": asdict(self.staff),
            "focus": asdict(self.focus),
            "zero_last_run": self.zero_last_run,
            "ports": self.ports,
            "serge_moves_today": self.serge_moves_today,
        }


# ── Helpers ──────────────────────────────────────────────────────

def _get_staff() -> StaffStatus:
    serge = dimitri = jopling = henckels = False
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "main.py" in cmd:
                if "sort" in cmd:
                    serge = True
                if "patrol" in cmd:
                    dimitri = True
                if "jopling" in cmd:
                    jopling = True
                if "henckels" in cmd:
                    henckels = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return StaffStatus(serge=serge, dimitri=dimitri, jopling=jopling, henckels=henckels, server=True)


def _zero_last_run() -> str:
    if not ZERO_LOG.exists():
        return "never"
    try:
        text = ZERO_LOG.read_text().strip()
        d = datetime.strptime(text, "%Y-%m-%d").date()
        today = datetime.now().date()
        if d == today:
            return "today"
        return d.strftime("%b %d")
    except Exception:
        return "never"


def _zero_save_run():
    ZERO_LOG.write_text(datetime.now().strftime("%Y-%m-%d"))


def _get_ports() -> list[dict]:
    out = []
    for port in config.PERMANENT_PORTS:
        live = False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                live = True
        except OSError:
            pass
        out.append({"port": port, "live": live})
    return out


# Cache for _serge_moves_today(): re-parsing the whole jsonl file (which only
# ever grows) on every call was the worst offender in the old 0.5s broadcast
# loop. Keyed on (mtime, size, date) so a real change — a new move logged, or
# the day rolling over — still gets picked up; anything else is a cache hit.
_serge_moves_cache: dict = {"mtime": None, "size": None, "date": None, "count": 0}


def _serge_moves_today() -> int:
    # Reuse serge.py's own MOVE_LOG constant rather than reconstructing the
    # same path here — two hardcoded copies of "~/.gbh/serge_moves.jsonl"
    # is exactly the kind of duplication that silently drifts apart.
    log = serge_mod.MOVE_LOG
    today = datetime.now().date().isoformat()
    cache = _serge_moves_cache

    if not log.exists():
        cache.update(mtime=None, size=None, date=today, count=0)
        return 0

    st = log.stat()
    if cache["mtime"] == st.st_mtime and cache["size"] == st.st_size and cache["date"] == today:
        return cache["count"]

    count = 0
    for line in log.read_text().splitlines():
        try:
            entry = json.loads(line)
            if entry.get("ts", "").startswith(today):
                count += 1
        except Exception:
            pass
    cache.update(mtime=st.st_mtime, size=st.st_size, date=today, count=count)
    return count


def _compute_fast_vitals() -> dict:
    """cpu/ram/disk/battery/focus — cheap (psutil reads + one small state-file
    read), and focus in particular drives the dashboard's live countdown
    timer, so this is safe and worth recomputing on every broadcast tick."""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    _, _, free = shutil.disk_usage("/")
    free_gb = free // (2 ** 30)

    bat_pct = bat_plug = None
    try:
        bat = psutil.sensors_battery()
        if bat:
            bat_pct  = round(bat.percent, 1)
            bat_plug = bat.power_plugged
    except Exception:
        pass

    ivan = IvanClass()
    focus_raw = ivan.status()

    return dict(
        cpu_percent=cpu,
        ram_percent=mem.percent,
        disk_free_gb=free_gb,
        battery_percent=bat_pct,
        battery_plugged=bat_plug,
        focus=FocusStatus(**focus_raw),
    )


def _compute_slow_vitals() -> dict:
    """staff/ports/serge-count/zero — each does real blocking work:
    _get_staff() walks every process on the system, _get_ports() opens up to
    len(PERMANENT_PORTS) blocking sockets with a 0.3s timeout apiece (worst
    case over a second, stalling the whole single-threaded event loop, not
    just this coroutine), and _serge_moves_today() re-reads a log file. None
    of it needs sub-second freshness — the dashboard only ever shows these as
    coarse dots/counters/timestamps — so broadcast_loop() only calls this
    once every SLOW_TICKS instead of every 0.5s tick."""
    return dict(
        staff=_get_staff(),
        zero_last_run=_zero_last_run(),
        ports=_get_ports(),
        serge_moves_today=_serge_moves_today(),
    )


def get_vitals() -> Vitals:
    """Full, fresh computation of every field. Used by the on-demand HTTP
    routes (`/`, `/api/vitals`), which aren't called often enough for the
    fast/slow split in broadcast_loop() to matter — correctness over cost."""
    return Vitals(**_compute_fast_vitals(), **_compute_slow_vitals())


# ── WebSocket broadcaster ────────────────────────────────────────

class Broadcaster:
    def __init__(self):
        self._conns: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._conns.append(ws)

    def disconnect(self, ws: WebSocket):
        self._conns = [c for c in self._conns if c is not ws]

    async def broadcast(self, payload: dict):
        dead = []
        for conn in self._conns:
            try:
                await conn.send_json(payload)
            except Exception:
                dead.append(conn)
        for c in dead:
            self.disconnect(c)


broadcaster = Broadcaster()


async def broadcast_loop():
    zero_tick = 0
    slow_vitals: dict | None = None
    slow_tick = 0
    while True:
        if broadcaster._conns:
            # Refresh the slow fields at most once every SLOW_TICKS — and
            # only while someone's actually watching, same as the original
            # "do nothing with no viewers" behavior this loop always had.
            if slow_vitals is None or slow_tick >= SLOW_TICKS:
                slow_vitals = _compute_slow_vitals()
                slow_tick = 0
            vitals = Vitals(**_compute_fast_vitals(), **slow_vitals)
            await broadcaster.broadcast(vitals.to_dict())
            slow_tick += 1
        zero_tick += BROADCAST_INTERVAL
        if zero_tick >= ZERO_CHECK_INTERVAL:
            zero_tick = 0
            if _zero_last_run() not in ("today",):
                try:
                    z = zero_mod.Zero()
                    z.clean_screenshots()
                    _zero_save_run()
                except Exception:
                    pass
        await asyncio.sleep(BROADCAST_INTERVAL)


# ── App ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(broadcast_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── Cross-origin / cross-site request guard ─────────────────────
#
# This server binds to 127.0.0.1 with no auth, on the assumption that only
# the machine's own user can reach it. That assumption breaks the moment any
# page you have open in a browser can also reach it: a "simple" cross-site
# POST (no custom headers, so no CORS preflight) to e.g. /api/clean or
# /api/focus/stop lands with the browser silently attaching your cookies —
# there are none here, but the request still executes and has a real side
# effect. This isn't a CORS problem (CORS only gates whether JS can *read*
# the response) — it's a same-origin-request-forgery problem, so the fix is
# to reject mutating requests that didn't originate from this app's own
# pages, not to add CORS headers.
_ALLOWED_ORIGINS = {
    f"http://{config.SERVER_HOST}:{config.SERVER_PORT}",
    f"http://localhost:{config.SERVER_PORT}",
}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in _MUTATING_METHODS:
            # Modern Chromium/Firefox: authoritative, can't be spoofed by page JS.
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site is not None:
                if fetch_site not in ("same-origin", "none"):
                    return JSONResponse({"detail": "cross-site request rejected"}, status_code=403)
            else:
                # Older browsers / non-browser clients: fall back to Origin,
                # which browsers attach to same-origin POSTs too. Only reject
                # when it's present AND wrong — curl/scripts send neither
                # header and are trusted, matching "only reachable from this
                # machine" the same way the bare 127.0.0.1 bind always was.
                origin = request.headers.get("origin")
                if origin is not None and origin not in _ALLOWED_ORIGINS:
                    return JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
        return await call_next(request)


app = FastAPI(title="GBH Concierge v2", lifespan=lifespan)
app.add_middleware(OriginGuardMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[config.SERVER_HOST, "localhost"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Routes ───────────────────────────────────────────────────────

@app.get("/")
def index(request: Request):
    vitals = get_vitals()
    resp = templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"vitals": vitals.to_dict()},
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/vitals")
def api_vitals():
    return get_vitals().to_dict()


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "gbh-concierge-v2"}


@app.websocket("/ws/vitals")
async def ws_vitals(websocket: WebSocket):
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)


@app.post("/api/clean")
async def api_clean():
    try:
        z = zero_mod.Zero()
        z.clean_screenshots(days_old=0)
        _zero_save_run()
        return {"status": "success", "message": "Zero swept the Desktop."}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/clean/old")
async def api_clean_old():
    try:
        z = zero_mod.Zero()
        count = z.archive_old_downloads()
        return {"status": "success", "message": f"Archived {count} old file(s) from Downloads."}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/serge/log")
def api_serge_log():
    return {"moves": serge_mod.get_recent_moves(20)}


@app.post("/api/serge/undo")
async def api_serge_undo():
    results = serge_mod.undo_last_moves(1)
    return {"results": results}


@app.get("/api/focus")
def api_focus():
    return IvanClass().status()


@app.get("/api/focus/history")
def api_focus_history(days: int = 7):
    from staff.ivan import get_history
    return {"history": get_history(days)}


@app.post("/api/focus/start")
async def api_focus_start(request: Request):
    body = await request.json()
    minutes = int(body.get("minutes", config.FOCUS_DEFAULT_MINUTES))
    # Run in a background thread — Ivan.start() blocks for the whole session.
    # State is written before the slow networksetup calls, so we just need a
    # short yield to let the thread get scheduled before we read it back.
    import threading
    iv = IvanClass()
    t = threading.Thread(target=iv.start, args=(minutes, config.FOCUS_BLOCKLIST, config.FOCUS_BLOCKED_APPS), daemon=True)
    t.start()
    await asyncio.sleep(0.2)   # let thread write state file
    return IvanClass().status()


@app.post("/api/focus/stop")
async def api_focus_stop():
    IvanClass().stop()
    return IvanClass().status()


@app.post("/api/focus/pause")
async def api_focus_pause():
    IvanClass().pause()
    return IvanClass().status()


@app.post("/api/focus/resume")
async def api_focus_resume():
    IvanClass().resume()
    return IvanClass().status()


@app.get("/api/large")
def api_large():
    z = zero_mod.Zero()
    files = z.find_large_files(str(Path.home()), config.LARGE_FILE_THRESHOLD_MB)
    return {"files": files[:20]}
