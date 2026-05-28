"""
GBH Concierge Server v2 — FastAPI backend for the dashboard.
Real-time vitals, Serge feed, Ivan focus, Zero actions via REST + WebSocket.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import psutil
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config  # noqa: E402
from staff import serge as serge_mod  # noqa: E402
from staff import zero as zero_mod  # noqa: E402
from staff.ivan import Ivan as IvanClass  # noqa: E402

BROADCAST_INTERVAL = 0.5
ZERO_CHECK_INTERVAL = 60
ZERO_LOG = BASE_DIR / "zero_last_run.txt"


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


def _serge_moves_today() -> int:
    log = Path.home() / ".gbh" / "serge_moves.jsonl"
    if not log.exists():
        return 0
    today = datetime.now().date().isoformat()
    count = 0
    for line in log.read_text().splitlines():
        try:
            import json
            entry = json.loads(line)
            if entry.get("ts", "").startswith(today):
                count += 1
        except Exception:
            pass
    return count


def get_vitals() -> Vitals:
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

    return Vitals(
        cpu_percent=cpu,
        ram_percent=mem.percent,
        disk_free_gb=free_gb,
        battery_percent=bat_pct,
        battery_plugged=bat_plug,
        staff=_get_staff(),
        focus=FocusStatus(**focus_raw),
        zero_last_run=_zero_last_run(),
        ports=_get_ports(),
        serge_moves_today=_serge_moves_today(),
    )


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
    while True:
        if broadcaster._conns:
            vitals = get_vitals()
            await broadcaster.broadcast(vitals.to_dict())
        zero_tick += BROADCAST_INTERVAL
        if zero_tick >= ZERO_CHECK_INTERVAL:
            zero_tick = 0
            if _zero_last_run() not in ("today",):
                try:
                    z = zero_mod.Zero()
                    z.clean_screenshots(days_old=0)
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


app = FastAPI(title="GBH Concierge v2", lifespan=lifespan)
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
