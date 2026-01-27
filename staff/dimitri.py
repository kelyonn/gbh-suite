import os
import socket
import time
import urllib.request
import threading
from urllib.error import URLError

class Dimitri:
    def _notify(self, title, message):
        safe_msg = message.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')
        os.system(f"""osascript -e 'display notification "{safe_msg}" with title "{safe_title}"'""")

    # --- JOB 1: THE WAITER ---
    def wait_for_port(self, port):
        url = f"http://localhost:{port}"
        # We don't print to console here because this runs in background
        
        try:
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            self._notify("System Ready 🚀", f"Port {port} is now active.")
                            return # Job done, stop watching this port
                except (URLError, ConnectionRefusedError, socket.timeout):
                    time.sleep(2) # Check every 2 seconds
        except Exception:
            pass

    # --- JOB 2: THE SENTINEL ---
    def watch_log(self, filepath):
        if not os.path.exists(filepath): return

        triggers = ["error", "exception", "traceback", "failed", "critical"]
        
        try:
            with open(filepath, "r") as f:
                f.seek(0, 2) # Go to end
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                        continue
                    
                    if any(t in line.lower() for t in triggers):
                        self._notify("Log Alert ⚠️", f"{os.path.basename(filepath)}: Error detected")
        except Exception:
            pass

    # --- JOB 3: THE PATROL (Multitasking) ---
    def start_patrol(self, ports, logs):
        print(f"🕵️ Dimitri is starting patrol...")
        
        # 1. Start Port Watchers
        for port in ports:
            t = threading.Thread(target=self.wait_for_port, args=(port,))
            t.daemon = True
            t.start()
            print(f"   - Watching Port {port}")

        # 2. Start Log Watchers
        for log_path in logs:
            if os.path.exists(log_path):
                t = threading.Thread(target=self.watch_log, args=(log_path,))
                t.daemon = True
                t.start()
                print(f"   - Watching Log {os.path.basename(log_path)}")

        # Keep the main thread alive so the helper threads don't die
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass