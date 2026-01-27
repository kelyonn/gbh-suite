import os
import shutil
import hashlib
import time

# --- CONFIGURATION ---
TRASH_DIR = os.path.expanduser("~/.Trash")
DESKTOP_DIR = os.path.expanduser("~/Desktop")

class Zero:
    def log(self, msg):
        print(f"🟣 {msg}")

    # --- JOB 1: SCREENSHOT SWEEPER ---
    def clean_screenshots(self, days_old=1):
        """Moves screenshots older than X days to Trash."""
        self.log(f"Sweeping Desktop for screenshots older than {days_old} day(s)...")
        
        now = time.time()
        cutoff = now - (days_old * 86400) # 86400 seconds in a day
        count = 0

        if not os.path.exists(DESKTOP_DIR):
            self.log("Desktop directory not found.")
            return

        for filename in os.listdir(DESKTOP_DIR):
            # Target standard Mac screenshots
            if "Screenshot" in filename and filename.endswith(".png"):
                file_path = os.path.join(DESKTOP_DIR, filename)
                try:
                    # Check creation time
                    if os.path.getctime(file_path) < cutoff:
                        shutil.move(file_path, TRASH_DIR)
                        print(f"   🗑️  Moved to Trash: {filename}")
                        count += 1
                except Exception as e:
                    print(f"   ❌ Error: {e}")

        if count == 0:
            self.log("Desktop is clean.")
        else:
            self.log(f"Finished. Moved {count} files to Trash.")

    # --- JOB 2: DUPLICATE HUNTER (SMART HASHING) ---
    def _get_hash(self, filepath, full=False):
        """
        Generates MD5 hash.
        If full=False: Reads only first 1KB (Super Fast).
        If full=True: Reads entire file (Accurate).
        """
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                if full:
                    # Read in chunks to save RAM
                    while chunk := f.read(8192):
                        hasher.update(chunk)
                else:
                    # Read only first 1KB
                    chunk = f.read(1024)
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return None

    def find_duplicates(self, directory):
        self.log(f"Hunting for duplicates in: {directory}")
        
        # Phase 1: Filter by SIZE (Fastest)
        # We only look at files that have the EXACT same byte size.
        files_by_size = {}
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.startswith(".") or filename == ".DS_Store": continue
                
                path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(path)
                    if size < 10240: continue # Ignore files smaller than 10KB
                    
                    if size not in files_by_size: files_by_size[size] = []
                    files_by_size[size].append(path)
                except OSError: pass

        # Only keep lists with >1 file
        potential_dupes = {s: p for s, p in files_by_size.items() if len(p) > 1}
        self.log(f"Phase 1 Complete: Found {len(potential_dupes)} groups with identical sizes.")

        # Phase 2: Filter by HASH (Accurate)
        duplicates = []
        
        for size, paths in potential_dupes.items():
            hashes = {}
            for path in paths:
                # Get FULL hash to be 100% sure
                file_hash = self._get_hash(path, full=True)
                if not file_hash: continue
                
                if file_hash not in hashes: hashes[file_hash] = []
                hashes[file_hash].append(path)
            
            # If multiple files share the hash, they are duplicates
            for _, file_list in hashes.items():
                if len(file_list) > 1:
                    duplicates.append(file_list)

        if not duplicates:
            self.log("No duplicates found. Your system is efficient.")
            return

        # Phase 3: Interactive Cleanup
        print(f"\n⚠️  Found {len(duplicates)} sets of duplicates.\n")
        
        total_saved = 0
        for group in duplicates:
            # Calculate size in MB
            size_mb = os.path.getsize(group[0]) / (1024 * 1024)
            
            print("-" * 50)
            print(f"📦 Duplicate Group (Size: {size_mb:.2f} MB)")
            for i, f in enumerate(group):
                print(f"   [{i+1}] {f}")
            
            choice = input("   👉 Type the number to KEEP (or 0 to skip): ")
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(group):
                    # User picked one to keep. Trash the rest.
                    for j, path_to_trash in enumerate(group):
                        if j != idx:
                            try:
                                shutil.move(path_to_trash, TRASH_DIR)
                                total_saved += size_mb
                                print(f"   🗑️  Trashed: {os.path.basename(path_to_trash)}")
                            except Exception as e:
                                print(f"   ❌ Error: {e}")
        
        print(f"\n✨ Cleanup Complete. You reclaimed {total_saved:.2f} MB of space.")