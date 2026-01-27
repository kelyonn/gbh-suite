# --- DIMITRI'S HIT LIST ---

# Ports to watch on startup.
# Dimitri will ping these silently and notify you when they wake up.
PERMANENT_PORTS = [3000, 8000, 5432, 8080]

# Log files to watch on startup.
# Dimitri will tail these for "Error" or "Exception".
PERMANENT_LOGS = [
    # os.path.expanduser("~/Documents/Projects/my_app/debug.log"),
    # os.path.expanduser("~/Library/Logs/nginx/error.log"),
]