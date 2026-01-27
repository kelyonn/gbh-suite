import os
import shutil
import subprocess
import psutil
from datetime import datetime

# --- CONFIGURATION ---
PROJECTS_DIR = os.path.expanduser("~/Documents/Projects")
CRITICAL_PORTS = [3000, 5432, 6379, 8000, 8080]

# --- COLORS ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class Gustave:
    def _print_header(self):
        print("\n" + "="*60)
        print(f"{Colors.HEADER}{Colors.BOLD}🎩 GUSTAVE'S MORNING BRIEFING | {datetime.now().strftime('%d %b, %I:%M %p')}{Colors.ENDC}")
        print("="*60 + "\n")

    def section(self, name):
        print(f"{Colors.BOLD}[ {name} ]{Colors.ENDC}")

    # --- TERMINAL REPORT METHODS ---
    def check_vitals(self):
        self.section("VITALS")
        total, used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)
        disk_color = Colors.GREEN if free_gb > 20 else Colors.RED
        print(f"  💾 Disk Storage:  {disk_color}{free_gb} GB Free{Colors.ENDC}")

        mem = psutil.virtual_memory()
        ram_color = Colors.GREEN if mem.percent < 80 else Colors.RED
        print(f"  🧠 Memory Usage:  {ram_color}{mem.percent}%{Colors.ENDC}")

        try:
            battery = psutil.sensors_battery()
            if battery:
                plugged = "⚡ Plugged In" if battery.power_plugged else "🔋 On Battery"
                color = Colors.GREEN if battery.percent > 20 else Colors.RED
                print(f"  🔋 Battery:       {color}{battery.percent}% ({plugged}){Colors.ENDC}")
        except Exception:
            pass
        print("")

    def check_services(self):
        self.section("FACTORY FLOOR")
        try:
            res = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"  🐳 Docker:        {Colors.RED}Daemon Not Running{Colors.ENDC}")
            else:
                count = len(res.stdout.splitlines())
                color = Colors.YELLOW if count > 0 else Colors.BLUE
                print(f"  🐳 Docker:        {color}{count} Containers Active{Colors.ENDC}")
        except FileNotFoundError:
            print(f"  🐳 Docker:        {Colors.BLUE}Not Installed{Colors.ENDC}")

        busy_ports = []
        for port in CRITICAL_PORTS:
            res = subprocess.run(["lsof", "-i", f":{port}"], capture_output=True)
            if res.returncode == 0:
                busy_ports.append(str(port))
        
        if busy_ports:
            print(f"  🚧 Busy Ports:    {Colors.YELLOW}{', '.join(busy_ports)}{Colors.ENDC}")
        else:
            print(f"  ✨ Localhost:     {Colors.GREEN}All Clear{Colors.ENDC}")
        print("")

    def check_git(self):
        self.section("PROJECTS")
        if not os.path.exists(PROJECTS_DIR): 
            print("  📂 Projects dir not found.")
            return

        clean_count = 0
        dirty_repos = []

        for item in os.listdir(PROJECTS_DIR):
            repo_path = os.path.join(PROJECTS_DIR, item)
            if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, ".git")):
                res = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True)
                if res.stdout.strip():
                    dirty_repos.append(item)
                else:
                    clean_count += 1
        
        print(f"  ✅ Clean Repos:   {Colors.GREEN}{clean_count}{Colors.ENDC}")
        
        if dirty_repos:
            print(f"  ⚠️  Uncommitted:   {Colors.RED}{', '.join(dirty_repos)}{Colors.ENDC}")
        else:
            print(f"  ✨ All Clear:     {Colors.GREEN}Ready to code.{Colors.ENDC}")
        print("")

    def report(self):
        self._print_header()
        self.check_vitals()
        self.check_services()
        self.check_git()
        print("="*60 + "\n")

    # --- NEW: NOTIFICATION METHOD ---
    def notify(self):
            """Generates a notification with aggressive string cleaning"""
            # 1. Gather Data
            try:
                mem = psutil.virtual_memory().percent
                total, used, free = shutil.disk_usage("/")
                free_gb = free // (2**30)
                
                docker_count = 0
                try:
                    res = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True)
                    if res.returncode == 0:
                        lines = res.stdout.strip().splitlines()
                        docker_count = len(lines)
                except Exception:
                    pass

                dirty_count = 0
                if os.path.exists(PROJECTS_DIR):
                    for item in os.listdir(PROJECTS_DIR):
                        repo = os.path.join(PROJECTS_DIR, item)
                        if os.path.isdir(repo) and os.path.exists(os.path.join(repo, ".git")):
                            try:
                                res = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True)
                                if res.stdout.strip(): 
                                    dirty_count += 1
                            except Exception:
                                pass

                # 2. Build Message (Simple text only)
                status_word = "Healthy"
                if mem > 85 or free_gb < 15: 
                    status_word = "Check System"
                
                title = f"Gustave: System {status_word}"
                
                # We use commas instead of pipes to be safe
                body = f"RAM {mem}% , Disk {free_gb}GB Free"
                if docker_count > 0: 
                    body += f" , Docker {docker_count}"
                if dirty_count > 0: 
                    body += f" , Uncommitted {dirty_count}"

                # 3. Send Notification (Safe Mode)
                # escape double quotes just in case
                safe_body = body.replace('"', '')
                safe_title = title.replace('"', '')
                
                os.system(f"osascript -e 'display notification \"{safe_body}\" with title \"{safe_title}\"'")

            except Exception as e:
                print(f"❌ Notification Error: {e}")


if __name__ == "__main__":
    g = Gustave()
    g.report()