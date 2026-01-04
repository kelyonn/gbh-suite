from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import psutil
import shutil
import sys
import os
import asyncio
from datetime import datetime

# --- SETUP PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "zero_last_run.txt")
sys.path.append(BASE_DIR)

# --- IMPORT THE STAFF ---
from staff import zero

# --- CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# --- HELPER: PERSISTENT MEMORY ---
def get_last_run_date():
    """Reads the file to see when Zero last worked."""
    if not os.path.exists(LOG_FILE):
        return None
    try:
        with open(LOG_FILE, "r") as f:
            date_str = f.read().strip()
            return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def save_last_run_date(date_obj):
    """Writes today's date to the file."""
    with open(LOG_FILE, "w") as f:
        f.write(date_obj.strftime("%Y-%m-%d"))

# --- HELPER: CHECK STAFF ---
def check_staff_status():
    staff_report = {"serge": False, "dimitri": False}
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline:
                cmd_str = " ".join(cmdline)
                if "serge.py" in cmd_str:
                    staff_report["serge"] = True
                if "dimitri.py" in cmd_str:
                    staff_report["dimitri"] = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return staff_report

# --- HELPER: VITALS ---
def get_system_vitals():
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    staff = check_staff_status()
    return {
        "ram_percent": mem.percent,
        "disk_free": free_gb,
        "cpu_percent": cpu,
        "staff": staff
    }

# --- BACKGROUND LOOP ---
async def broadcast_loop():
    while True:
        # 1. SEND VITALS (Fast)
        if manager.active_connections:
            data = get_system_vitals()
            await manager.broadcast(data)
        
        # 2. CHECK ZERO SCHEDULE (Daily)
        # We read from the file so this persists across reboots
        today = datetime.now().date()
        last_run = get_last_run_date()

        if last_run != today:
            # If the dates don't match, it means we haven't cleaned TODAY yet.
            print(f"[GBH] New day detected ({today}). Running Zero...")
            try:
                boy = zero.Zero()
                boy.clean_screenshots(days_old=0)
                # Save the date so we don't run again until tomorrow
                save_last_run_date(today)
            except Exception as e:
                print(f"[GBH] Zero failed: {e}")

        await asyncio.sleep(1)

# --- APP LIFECYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(broadcast_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# --- ROUTES ---
@app.get("/")
def home(request: Request):
    vitals = get_system_vitals()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "vitals": vitals
    })

@app.websocket("/ws/vitals")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/clean")
async def run_cleaner():
    try:
        boy = zero.Zero()
        boy.clean_screenshots(days_old=0)
        # Note: We do NOT update the daily log here. 
        # Manual clicks are "extra" cleanings, they shouldn't stop the daily schedule.
        return JSONResponse({"status": "success", "message": "Zero has swept the Desktop screenshots."})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})