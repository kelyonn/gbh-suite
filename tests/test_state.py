"""Tests for staff/state.py — atomic JSON read/write/delete/append."""

import json

from staff import state


def test_write_then_read_roundtrip(tmp_path):
    path = tmp_path / "focus_state.json"
    state.write_json(path, {"active": True, "duration_min": 25})

    assert state.read_json(path) == {"active": True, "duration_min": 25}


def test_read_missing_file_returns_none(tmp_path):
    assert state.read_json(tmp_path / "nope.json") is None


def test_read_unparseable_file_returns_none(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")

    assert state.read_json(path) is None


def test_write_is_atomic_no_partial_file_left_behind(tmp_path):
    path = tmp_path / "state.json"
    state.write_json(path, {"a": 1})

    # write_json must go through a temp file in the same directory, then
    # os.replace() it into place — no .tmp/.stateXXXX leftovers after success.
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json" and p.suffix != ".lock"]
    assert leftovers == []
    assert json.loads(path.read_text()) == {"a": 1}


def test_write_overwrites_existing_file_completely(tmp_path):
    path = tmp_path / "state.json"
    state.write_json(path, {"a": 1, "b": 2, "c": 3})
    state.write_json(path, {"a": 1})  # smaller payload

    # A naive open("w") + write (no truncate-via-replace) could leave trailing
    # bytes from the longer previous write. os.replace() can't do that.
    assert state.read_json(path) == {"a": 1}


def test_delete_removes_file(tmp_path):
    path = tmp_path / "state.json"
    state.write_json(path, {"a": 1})

    state.delete_json(path)

    assert not path.exists()
    assert state.read_json(path) is None


def test_delete_on_missing_file_does_not_raise(tmp_path):
    state.delete_json(tmp_path / "never_existed.json")  # must not raise


def test_delete_leaves_lock_file_in_place(tmp_path):
    """Regression test for the delete_json lock-unlink-while-held bug.

    delete_json() used to unlink its own .lock file from *inside* the `with
    open(lock) as lf: flock(lf, LOCK_EX)` block. That's a use-after-free on
    the lock's identity: a concurrent process blocked on flock() holds an fd
    to the old inode; once the path is unlinked, the *next* write recreates a
    fresh lock file and acquires it immediately, while the still-blocked
    waiter believes it's holding the lock on an inode nothing points to
    anymore. The fix leaves the (empty) lock file in place after delete.
    """
    path = tmp_path / "state.json"
    lock = path.with_suffix(".lock")
    state.write_json(path, {"a": 1})
    assert lock.exists()

    state.delete_json(path)

    assert not path.exists()
    assert lock.exists()


def test_append_jsonl_appends_one_record_per_line(tmp_path):
    path = tmp_path / "history.jsonl"
    state.append_jsonl(path, {"n": 1})
    state.append_jsonl(path, {"n": 2})

    lines = path.read_text().strip().splitlines()
    assert [json.loads(line) for line in lines] == [{"n": 1}, {"n": 2}]


def test_write_json_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "deep" / "state.json"
    state.write_json(path, {"a": 1})

    assert state.read_json(path) == {"a": 1}
