"""Tests for staff/serge.py — file categorization, uniquing, move log, undo."""

import json

from staff import serge


def test_categorize_known_extension():
    assert serge._categorize("photo.PNG") == "Images"  # case-insensitive
    assert serge._categorize("report.pdf") == "Documents"
    assert serge._categorize("song.mp3") == "Audio"
    assert serge._categorize("clip.mov") == "Video"
    assert serge._categorize("bundle.zip") == "Archives"
    assert serge._categorize("main.py") == "Code"


def test_categorize_unknown_extension_falls_back_to_others():
    assert serge._categorize("mystery.xyz123") == "Others"
    assert serge._categorize("no_extension_at_all") == "Others"


def test_categorize_app_bundle_falls_back_to_others():
    """Regression test: `.app` was removed from config.SERGE_DESTINATIONS
    because it's a directory bundle and every sort path guards on
    os.path.isfile(), so it could never have matched Installers anyway."""
    assert serge._categorize("Some Program.app") == "Others"


def test_is_skip_hidden_and_partial_downloads():
    assert serge._is_skip(".DS_Store") is True
    assert serge._is_skip(".hidden") is True
    assert serge._is_skip("movie.mp4.crdownload") is True
    assert serge._is_skip("archive.zip.part") is True
    assert serge._is_skip("photo.jpg") is False


def test_make_unique_returns_plain_path_when_free(tmp_path):
    result = serge._make_unique(str(tmp_path), "file.txt", "20260101_000000")
    assert result == str(tmp_path / "file.txt")


def test_make_unique_appends_timestamp_on_collision(tmp_path):
    (tmp_path / "file.txt").write_text("existing")

    result = serge._make_unique(str(tmp_path), "file.txt", "20260101_000000")

    assert result == str(tmp_path / "file_20260101_000000.txt")


def test_log_move_and_get_recent_moves_roundtrip(gbh_home):
    serge._log_move("/src/a.png", "/dst/a.png", "Images")
    serge._log_move("/src/b.pdf", "/dst/b.pdf", "Documents")

    moves = serge.get_recent_moves(20)

    # Most recent first.
    assert [m["filename"] for m in moves] == ["b.pdf", "a.png"]
    assert moves[0]["category"] == "Documents"


def test_get_recent_moves_on_missing_log_returns_empty(gbh_home):
    assert serge.get_recent_moves() == []


def test_undo_last_moves_restores_file_and_trims_log(gbh_home, tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    dst_file = dst_dir / "file.txt"
    dst_file.write_text("content")

    serge._log_move(str(src_dir / "file.txt"), str(dst_file), "Documents")

    results = serge.undo_last_moves(1)

    assert not dst_file.exists()
    assert (src_dir / "file.txt").exists()
    assert "Restored" in results[0]
    # The log entry for the undone move must be gone.
    assert serge.MOVE_LOG.read_text().strip() == ""


def test_undo_last_moves_reports_missing_destination(gbh_home):
    serge._log_move("/src/gone.txt", "/dst/gone.txt", "Others")

    results = serge.undo_last_moves(1)

    assert "no longer at destination" in results[0]


def test_undo_last_moves_on_empty_log(gbh_home):
    assert serge.undo_last_moves(1) == ["No move history found."]


def test_get_recent_moves_skips_corrupt_lines(gbh_home):
    serge.GBH_DATA.mkdir(exist_ok=True)
    with open(serge.MOVE_LOG, "w") as f:
        f.write("not json at all\n")
        f.write(json.dumps({"ts": "2026-01-01T00:00:00", "filename": "ok.txt",
                             "category": "Others", "src": "s", "dst": "d"}) + "\n")

    moves = serge.get_recent_moves()

    assert len(moves) == 1
    assert moves[0]["filename"] == "ok.txt"
