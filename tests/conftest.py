"""
Shared fixtures. The one rule for this whole test suite: nothing here may
touch the real ~/Downloads, ~/Desktop, ~/.Trash, or ~/.gbh, and nothing may
fire a real macOS notification or flip a real networksetup proxy setting.

Every module under staff/ binds its data-file paths as module-level constants
at import time (e.g. serge.MOVE_LOG, ivan.FOCUS_STATE_FILE), so isolation is
just monkeypatching those attributes onto tmp_path before the test runs —
the functions under test read the (now-patched) module attribute at call
time, not a copy.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from staff import ivan as ivan_mod
from staff import serge as serge_mod
from staff import zero as zero_mod


@pytest.fixture
def gbh_home(tmp_path, monkeypatch):
    """Redirect every staff module's runtime-data paths into tmp_path.

    Returns a namespace of the resulting paths for tests that want to poke
    at them directly (e.g. pre-seed a state file before calling status()).
    """
    data_dir = tmp_path / ".gbh"
    data_dir.mkdir()

    monkeypatch.setattr(serge_mod, "GBH_DATA", data_dir)
    monkeypatch.setattr(serge_mod, "MOVE_LOG", data_dir / "serge_moves.jsonl")

    monkeypatch.setattr(ivan_mod, "GBH_DATA", data_dir)
    monkeypatch.setattr(ivan_mod, "FOCUS_STATE_FILE", data_dir / "focus_state.json")
    monkeypatch.setattr(ivan_mod, "FOCUS_HISTORY", data_dir / "focus_history.jsonl")
    monkeypatch.setattr(ivan_mod, "PAC_FILE", data_dir / "ivan_block.pac")

    desktop = tmp_path / "Desktop"
    downloads = tmp_path / "Downloads"
    trash = tmp_path / "Trash"
    desktop.mkdir()
    downloads.mkdir()
    trash.mkdir()
    monkeypatch.setattr(zero_mod, "DESKTOP", desktop)
    monkeypatch.setattr(zero_mod, "DOWNLOADS", downloads)
    monkeypatch.setattr(zero_mod, "TRASH_DIR", trash)

    class Paths:
        pass

    p = Paths()
    p.data_dir = data_dir
    p.desktop = desktop
    p.downloads = downloads
    p.trash = trash
    return p


@pytest.fixture
def no_real_network_side_effects(monkeypatch):
    """Neuter Ivan's networksetup/process-signal calls.

    Any test that exercises start()/pause()/resume()/stop()/status() must use
    this fixture — those functions call _block_sites()/_unblock_sites(),
    which shell out to the real `networksetup` and would flip the *actual*
    machine's proxy config, and _suspend_apps()/_resume_apps(), which send
    real POSIX signals to whatever process happens to match a blocked app
    name. Records calls instead so assertions can still check they happened.
    """
    calls = {"blocked": [], "unblocked": 0, "suspended": [], "resumed": []}

    def _fake_block_sites(blocklist):
        calls["blocked"].append(list(blocklist))
        return True

    def _fake_unblock_sites():
        calls["unblocked"] += 1

    def _fake_suspend_apps(app_names):
        calls["suspended"].append(list(app_names))
        return {}

    def _fake_resume_apps(pid_map):
        calls["resumed"].append(dict(pid_map))

    monkeypatch.setattr(ivan_mod, "_block_sites", _fake_block_sites)
    monkeypatch.setattr(ivan_mod, "_unblock_sites", _fake_unblock_sites)
    monkeypatch.setattr(ivan_mod, "_suspend_apps", _fake_suspend_apps)
    monkeypatch.setattr(ivan_mod, "_resume_apps", _fake_resume_apps)
    return calls


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    """Prevent every test in the suite from popping a real macOS notification.

    Autouse: notify() is called from deep inside staff modules incidentally
    (e.g. Serge logs a move), so opting in per-test isn't reliable enough —
    this has to apply everywhere.
    """
    import subprocess

    calls = []
    real_run = subprocess.run

    def _fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and (
            "terminal-notifier" in cmd[0] or cmd[0] == "osascript"
        ):
            calls.append(cmd)

            class _Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return _Result()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return calls
