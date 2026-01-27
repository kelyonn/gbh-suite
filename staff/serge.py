import os
import shutil
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
SOURCE_DIR = os.path.expanduser("~/Downloads")
PROJECTS_DIR = os.path.expanduser("~/Documents/Projects")

DESTINATIONS = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".heic", ".webp"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".csv", ".xlsx", ".epub"],
    "Audio": [".mp3", ".wav", ".aac", ".flac", ".m4a"],
    "Video": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
    "Installers": [".dmg", ".pkg", ".app"],
    "Code": [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".sql", ".sh", ".json", ".ipynb"]
}

EMOJI_MAP = {
    "Images": "🖼️", "Documents": "📝", "Audio": "🎵", "Video": "🎥",
    "Archives": "📦", "Installers": "💿", "Code": "💻", "Others": "📂"
}

# --- LOGIC ---
def send_notification(title, message):
    try:
        safe_msg = message.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')
        os.system(f"""osascript -e 'display notification "{safe_msg}" with title "{safe_title}"'""")
    except Exception:
        pass

def make_unique(path):
    filename, extension = os.path.splitext(path)
    counter = 1
    while os.path.exists(path):
        path = f"{filename}({counter}){extension}"
        counter += 1
    return path

class SmartSorter(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.processing = set()  # Track files currently being processed
        self.processed = set()   # Track recently processed files to avoid duplicates
        
    def on_created(self, event):
        """Handle new files created in Downloads"""
        if event.is_directory:
            return
            
        # Only process files created directly in the source directory
        if os.path.dirname(event.src_path) != SOURCE_DIR:
            return
            
        self._handle_file(event.src_path)
    
    def on_moved(self, event):
        """Handle files moved into Downloads (ignore moves out)"""
        if event.is_directory:
            return
            
        # Only process files moved INTO the source directory
        if os.path.dirname(event.dest_path) != SOURCE_DIR:
            return
            
        self._handle_file(event.dest_path)
    
    def _handle_file(self, file_path):
        """Process a file if it's valid and not already being processed"""
        # Normalize path to handle symlinks
        abs_path = os.path.abspath(file_path)
        
        # Skip if already processing or recently processed
        if abs_path in self.processing or abs_path in self.processed:
            return
        
        # Check if file exists and is in source directory
        if not os.path.exists(file_path):
            return
        
        if os.path.isdir(file_path):
            return
        
        # Normalize the directory check
        if os.path.dirname(abs_path) != os.path.abspath(SOURCE_DIR):
            return
        
        filename = os.path.basename(file_path)
        
        # Skip hidden files and system files
        if filename == ".DS_Store" or filename.startswith("."):
            return
        
        # Skip incomplete downloads
        if filename.endswith((".tmp", ".crdownload", ".part")):
            return
        
        # Mark as processing
        self.processing.add(abs_path)
        
        try:
            self._sort_file(file_path, filename)
        finally:
            # Remove from processing, add to processed (with timeout)
            self.processing.discard(abs_path)
            self.processed.add(abs_path)
            # Clean up processed set periodically (keep last 100)
            if len(self.processed) > 100:
                # Remove oldest entries (simple FIFO approximation)
                self.processed = set(list(self.processed)[-50:])
    
    def _sort_file(self, file_path, filename):
        """Sort a file into the appropriate category"""
        # Wait for file to be fully written (especially for downloads)
        time.sleep(0.5)
        
        # Double-check file still exists and is in source directory
        if not os.path.exists(file_path):
            return
        
        abs_path = os.path.abspath(file_path)
        if os.path.dirname(abs_path) != os.path.abspath(SOURCE_DIR):
            return
        
        # Identify category by extension
        category = "Others"
        _, extension = os.path.splitext(filename)
        extension = extension.lower()
        
        for cat, exts in DESTINATIONS.items():
            if extension in exts:
                category = cat
                break
        
        # Determine destination directory
        if category == "Code":
            dest_dir = PROJECTS_DIR
        else:
            dest_dir = os.path.join(SOURCE_DIR, category)
        
        # Create destination directory if needed
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        
        # Move file
        try:
            dest_path = os.path.join(dest_dir, filename)
            final_dest = make_unique(dest_path)
            shutil.move(file_path, final_dest)
            
            icon = EMOJI_MAP.get(category, "📂")
            send_notification(f"Moved to {category} {icon}", filename)
            print(f"✅ Moved {filename} -> {category}", flush=True)
        except Exception as e:
            print(f"❌ Error moving {filename}: {e}", flush=True)

def _sort_existing_files():
    """Sort any existing files in Downloads on startup"""
    if not os.path.exists(SOURCE_DIR):
        return
    
    handler = SmartSorter()
    sorted_count = 0
    
    try:
        for filename in os.listdir(SOURCE_DIR):
            file_path = os.path.join(SOURCE_DIR, filename)
            
            # Skip directories and hidden files
            if os.path.isdir(file_path) or filename.startswith("."):
                continue
            
            # Skip incomplete downloads
            if filename.endswith((".tmp", ".crdownload", ".part")):
                continue
            
            # Process the file
            abs_path = os.path.abspath(file_path)
            if abs_path not in handler.processed:
                handler._handle_file(file_path)
                sorted_count += 1
    except Exception as e:
        print(f"❌ Error sorting existing files: {e}", flush=True)
    
    if sorted_count > 0:
        print(f"✅ Sorted {sorted_count} existing file(s) on startup", flush=True)

def start_watch():
    """Start the file watcher service"""
    # Ensure directories exist
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)
    
    if not os.path.exists(SOURCE_DIR):
        print(f"❌ Source directory does not exist: {SOURCE_DIR}", flush=True)
        return
    
    # Sort existing files first
    _sort_existing_files()
    
    # Set up observer for new files
    observer = Observer()
    handler = SmartSorter()
    observer.schedule(handler, SOURCE_DIR, recursive=False)
    observer.start()
    
    # Send startup notification
    send_notification("Serge Active 🎩", "I am watching the door.")
    print(f"🎩 Serge is watching {SOURCE_DIR}", flush=True)
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()
