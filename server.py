"""
GBH Concierge Server — Grand Budapest Hotel dashboard API.
Serves real-time vitals, staff status, Zero cleanup, and port status via REST + WebSocket.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import psutil
import shutil
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "zero_last_run.txt"
sys.path.insert(0, str(BASE_DIR))

from staff import zero

try:
    import config as gbh_config
except ImportError:
    gbh_config = None

# --- Config ---
BROADCAST_INTERVAL_SEC = 1.0
ZERO_DAILY_CHECK_INTERVAL_SEC = 60

# --- Data models ---


@dataclass
class StaffStatus:
    serge: bool
    dimitri: bool


@dataclass
class Vitals:
    cpu_percent: float
    ram_percent: float
    disk_free_gb: int
    staff: StaffStatus
    zero_last_run: str = "never"
    ports: list | None = None

    def __post_init__(self):
        if self.ports is None:
            self.ports = []

    def to_dict(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_percent": round(self.ram_percent, 1),
            "disk_free": self.disk_free_gb,
            "staff": asdict(self.staff),
            "zero_last_run": self.zero_last_run,
            "ports": self.ports,
        }


# --- Services ---


def get_vitals() -> Vitals:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    _, _, free_bytes = shutil.disk_usage("/")
    free_gb = free_bytes // (2**30)
    staff = get_staff_status()
    return Vitals(
        cpu_percent=cpu,
        ram_percent=mem.percent,
        disk_free_gb=free_gb,
        staff=staff,
        zero_last_run=zero_last_run_str(),
        ports=get_port_status(),
    )


def get_staff_status() -> StaffStatus:
    serge = dimitri = False
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmd = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmd)
            if "main.py" not in cmd_str:
                continue
            if "sort" in cmd_str:
                serge = True
            if "patrol" in cmd_str:
                dimitri = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return StaffStatus(serge=serge, dimitri=dimitri)


def zero_last_run_date() -> date | None:
    if not LOG_FILE.exists():
        return None
    try:
        text = LOG_FILE.read_text().strip()
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def zero_last_run_str() -> str:
    d = zero_last_run_date()
    if d is None:
        return "never"
    today = datetime.now().date()
    if d == today:
        return "today"
    return d.strftime("%b %d")


def zero_save_run_date(d: datetime) -> None:
    LOG_FILE.write_text(d.strftime("%Y-%m-%d"))


def get_port_status() -> list[dict]:
    if not gbh_config or not getattr(gbh_config, "PERMANENT_PORTS", None):
        return []
    out = []
    for port in gbh_config.PERMANENT_PORTS:
        live = False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                live = True
        except OSError:
            pass
        out.append({"port": port, "live": live})
    return out


async def maybe_run_zero_daily() -> None:
    today = datetime.now().date()
    last = zero_last_run_date()
    if last == today:
        return
    try:
        z = zero.Zero()
        z.clean_screenshots(days_old=0)
        zero_save_run_date(datetime.now())
        print(f"[GBH] Zero ran daily cleanup for {today}")
    except Exception as e:
        print(f"[GBH] Zero daily run failed: {e}")


# --- WebSocket manager ---


class VitalsBroadcaster:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        dead = []
        for conn in self._connections:
            try:
                await conn.send_json(payload)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


broadcaster = VitalsBroadcaster()


async def broadcast_loop() -> None:
    zero_check_counter = 0
    while True:
        if broadcaster._connections:
            vitals = get_vitals()
            await broadcaster.broadcast(vitals.to_dict())

        zero_check_counter += 1
        if zero_check_counter * BROADCAST_INTERVAL_SEC >= ZERO_DAILY_CHECK_INTERVAL_SEC:
            zero_check_counter = 0
            await maybe_run_zero_daily()

        await asyncio.sleep(BROADCAST_INTERVAL_SEC)


# --- App ---


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


app = FastAPI(title="GBH Concierge", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# --- Routes ---


@app.get("/")
def index(request: Request):
    vitals = get_vitals()
    resp = templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "vitals": vitals.to_dict()},
    )
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/api/vitals")
def api_vitals():
    return get_vitals().to_dict()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "gbh-concierge"}


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
        z = zero.Zero()
        z.clean_screenshots(days_old=0)
        zero_save_run_date(datetime.now())
        return {"status": "success", "message": "Zero has swept the Desktop screenshots."}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )


