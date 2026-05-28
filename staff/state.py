"""
GBH — Atomic JSON state helpers.

All staff that persist state to ~/.gbh/*.json should use these helpers
instead of plain read_text/write_text so that:

  • Writes are atomic (temp file + os.replace — no half-written JSON on crash)
  • Concurrent readers/writers (CLI process vs server process) are serialised
    with an advisory fcntl lock on a companion .lock file
"""

import fcntl
import json
import os
import tempfile
from pathlib import Path


def _lock_path(path: Path) -> Path:
    return path.with_suffix(".lock")


def read_json(path: Path) -> dict | None:
    """Read and parse a JSON file with a shared (read) lock.

    Returns None if the file does not exist or is unparseable.
    """
    if not path.exists():
        return None
    lock = _lock_path(path)
    try:
        with open(lock, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            return json.loads(path.read_text())
    except Exception:
        return None


def write_json(path: Path, data: dict) -> None:
    """Write *data* to *path* atomically with an exclusive lock.

    Writes to a temp file in the same directory, then os.replace()s it
    into place so readers always see a complete file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def delete_json(path: Path) -> None:
    """Delete a JSON state file (and its lock file) if they exist."""
    lock = _lock_path(path)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        path.unlink(missing_ok=True)
    lock.unlink(missing_ok=True)


def append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON record (one line) to a .jsonl file with an exclusive lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(path)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
