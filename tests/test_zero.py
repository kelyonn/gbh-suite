"""Tests for staff/zero.py — screenshot sweep, large-file scan, duplicate
finder, and the SCREENSHOT_MAX_AGE_DAYS wiring bug fixed in this pass.
"""

import os
import time

import config
from staff import zero


def _freeze_clock_forward(monkeypatch, days_ahead):
    """Make clean_screenshots()'s cutoff calculation see "now" as
    *days_ahead* days in the future, relative to real wall-clock time.

    We can't age a file's ctime directly: os.utime() only ever sets
    atime/mtime — the kernel always stamps ctime with the real wall clock
    the moment any metadata changes, on both macOS and Linux (verified: an
    os.utime() backdate attempt left st_ctime at "now" and only moved
    st_mtime). So instead of aging the file, we age the code's notion of
    "now" for a file created at real "now" — same effect, without a real
    multi-day sleep.
    """
    fake_now = time.time() + days_ahead * 86400
    monkeypatch.setattr(zero.time, "time", lambda: fake_now)


def test_clean_screenshots_default_does_not_trash_a_fresh_screenshot(gbh_home):
    """Regression test: server.py's auto-sweep used to call
    clean_screenshots(days_old=0), which sets cutoff=now — so a screenshot
    taken seconds ago (ctime ~ now) satisfied `ctime < cutoff` and got
    trashed. No time-mocking needed here: this is exactly what a freshly
    created file naturally looks like, and it must survive the *default*
    call (i.e. config.SCREENSHOT_MAX_AGE_DAYS, not 0)."""
    fresh_shot = gbh_home.desktop / "Screenshot fresh.png"
    fresh_shot.write_text("data")

    count = zero.Zero().clean_screenshots()  # no days_old passed

    assert count == 0
    assert fresh_shot.exists()


def test_clean_screenshots_sweeps_files_older_than_the_configured_window(
    gbh_home, monkeypatch
):
    monkeypatch.setattr(config, "SCREENSHOT_MAX_AGE_DAYS", 1)
    shot = gbh_home.desktop / "Screenshot old.png"
    shot.write_text("data")
    _freeze_clock_forward(monkeypatch, days_ahead=2)  # simulate 2 days later

    count = zero.Zero().clean_screenshots()  # uses the config default (1)

    assert count == 1
    assert not shot.exists()


def test_clean_screenshots_explicit_days_old_still_works(gbh_home, monkeypatch):
    shot = gbh_home.desktop / "Screenshot old.png"
    shot.write_text("data")
    _freeze_clock_forward(monkeypatch, days_ahead=5)

    count = zero.Zero().clean_screenshots(days_old=1)

    assert count == 1
    assert not shot.exists()


def test_clean_screenshots_ignores_non_screenshot_pngs(gbh_home):
    other = gbh_home.desktop / "vacation.png"
    other.write_text("data")

    count = zero.Zero().clean_screenshots(days_old=1)

    assert count == 0
    assert other.exists()


def test_archive_old_downloads_moves_stale_files(gbh_home, monkeypatch, tmp_path):
    archive_dir = tmp_path / "Archive"
    monkeypatch.setattr(config, "ARCHIVE_DIR", str(archive_dir))
    stale = gbh_home.downloads / "old.zip"
    stale.write_text("data")
    old_time = time.time() - (40 * 86400)
    os.utime(stale, (old_time, old_time))

    count = zero.Zero().archive_old_downloads(days=30)

    assert count == 1
    assert not stale.exists()
    assert (archive_dir / "OldDownloads" / "old.zip").exists()


def test_find_large_files_respects_threshold(tmp_path):
    small = tmp_path / "small.bin"
    big = tmp_path / "big.bin"
    small.write_bytes(b"0" * 1024)
    big.write_bytes(b"0" * (2 * 1024 * 1024))

    results = zero.Zero().find_large_files(str(tmp_path), threshold_mb=1)

    paths = [r["path"] for r in results]
    assert str(big) in paths
    assert str(small) not in paths


def test_find_large_files_skips_venv_and_git_dirs(tmp_path):
    skip_dir = tmp_path / "venv"
    skip_dir.mkdir()
    (skip_dir / "big.bin").write_bytes(b"0" * (2 * 1024 * 1024))

    results = zero.Zero().find_large_files(str(tmp_path), threshold_mb=1)

    assert results == []


def test_find_duplicate_groups_finds_identical_content(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 20000)
    (tmp_path / "b.txt").write_bytes(b"x" * 20000)  # identical content
    (tmp_path / "c.txt").write_bytes(b"y" * 20000)  # different content, same size

    groups = zero.Zero().find_duplicate_groups(str(tmp_path))

    assert len(groups) == 1
    assert {os.path.basename(p) for p in groups[0]} == {"a.txt", "b.txt"}


def test_find_duplicate_groups_ignores_files_below_size_floor(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    (tmp_path / "b.txt").write_bytes(b"x" * 100)

    # Both under the 10KB floor in find_duplicate_groups — same-size bucketing
    # only fires above that, by design (not worth hashing tiny files).
    groups = zero.Zero().find_duplicate_groups(str(tmp_path))

    assert groups == []


def test_find_duplicate_groups_no_duplicates(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 20000)
    (tmp_path / "b.txt").write_bytes(b"y" * 20000)

    assert zero.Zero().find_duplicate_groups(str(tmp_path)) == []


def test_hash_file_matches_for_identical_content(tmp_path):
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"same content")
    f2.write_bytes(b"same content")

    z = zero.Zero()
    assert z._hash_file(str(f1)) == z._hash_file(str(f2))


def test_hash_file_on_missing_file_returns_none(tmp_path):
    assert zero.Zero()._hash_file(str(tmp_path / "nope.bin")) is None
