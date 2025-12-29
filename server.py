from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import psutil
import shutil
import sys
import os
import asyncio

# --- IMPORT THE STAFF ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
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

# --- HELPER: CHECK IF STAFF IS WORKING ---
def check_staff_status():
    """Scans running processes to see if Serge or Dimitri are alive"""
    staff_report = {
        "serge": False,
        "dimitri": False
    }
    
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline:
                # Convert list of args to a single string for easy searching
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
    
    # Get Staff Status
    staff = check_staff_status()
    
    return {
        "ram_percent": mem.percent,
        "disk_free": free_gb,
        "cpu_percent": cpu,
        "staff": staff # <--- NEW DATA
    }

# --- BACKGROUND LOOP ---
async def broadcast_loop():
    while True:
        if manager.active_connections:
            data = get_system_vitals()
            await manager.broadcast(data)
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
        return JSONResponse({"status": "success", "message": "Zero has swept the Desktop screenshots."})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})