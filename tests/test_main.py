"""Tests for main.py — the CLI arg parser, focused on the two bugs fixed in
this pass: `gbh clean --old <non-digit>` crashing, and `gbh focus pomodoro`
not forwarding blocked apps.
"""

import main


def test_flag_value_returns_next_arg():
    import sys
    old_argv = sys.argv
    sys.argv = ["main.py", "clean", "--old", "45"]
    try:
        assert main._flag_value("--old") == "45"
    finally:
        sys.argv = old_argv


def test_flag_value_returns_default_when_flag_is_last():
    import sys
    old_argv = sys.argv
    sys.argv = ["main.py", "clean", "--old"]
    try:
        assert main._flag_value("--old", default="30") == "30"
    finally:
        sys.argv = old_argv


def test_flag_value_returns_default_when_followed_by_another_flag():
    """Regression case for `gbh clean --old --dupes ~/Downloads`: --old has no
    value of its own, the next token is another flag, not a number."""
    import sys
    old_argv = sys.argv
    sys.argv = ["main.py", "clean", "--old", "--dupes", "~/Downloads"]
    try:
        assert main._flag_value("--old") is None
    finally:
        sys.argv = old_argv


def test_flag_value_missing_flag_returns_default():
    import sys
    old_argv = sys.argv
    sys.argv = ["main.py", "clean"]
    try:
        assert main._flag_value("--old", default="x") == "x"
    finally:
        sys.argv = old_argv


def test_clean_old_with_non_digit_value_does_not_raise(monkeypatch, capsys):
    """Regression test: `gbh clean --old foo` used to raise an unhandled
    ValueError from int(sys.argv[...]) with no argument-shape validation."""
    import sys

    from staff import zero as zero_mod

    called = []
    monkeypatch.setattr(
        zero_mod.Zero, "archive_old_downloads", lambda self, days=None: called.append(days)
    )

    old_argv = sys.argv
    sys.argv = ["main.py", "clean", "--old", "foo"]
    try:
        main.main()  # must not raise
    finally:
        sys.argv = old_argv

    assert called == []  # archive_old_downloads must not have been reached
    assert "not a number" in capsys.readouterr().out


def test_clean_old_with_digit_value_still_works(monkeypatch):
    import sys

    from staff import zero as zero_mod

    called = []
    monkeypatch.setattr(
        zero_mod.Zero, "archive_old_downloads", lambda self, days=None: called.append(days)
    )

    old_argv = sys.argv
    sys.argv = ["main.py", "clean", "--old", "45"]
    try:
        main.main()
    finally:
        sys.argv = old_argv

    assert called == [45]


def test_focus_pomodoro_forwards_configured_blocked_apps(monkeypatch):
    """Regression test: `gbh focus pomodoro` called
    iv.pomodoro(config.FOCUS_BLOCKLIST, cycles) without blocked_apps, so
    config.FOCUS_BLOCKED_APPS was silently ignored from the CLI entry point
    even after ivan.py's pomodoro() gained the parameter."""
    import sys

    import config
    from staff import ivan as ivan_mod

    captured = {}
    monkeypatch.setattr(
        ivan_mod.Ivan,
        "pomodoro",
        lambda self, blocklist, cycles, blocked_apps=None: captured.update(
            blocklist=blocklist, cycles=cycles, blocked_apps=blocked_apps
        ),
    )

    old_argv = sys.argv
    sys.argv = ["main.py", "focus", "pomodoro", "2"]
    try:
        main.main()
    finally:
        sys.argv = old_argv

    assert captured["cycles"] == 2
    assert captured["blocked_apps"] == config.FOCUS_BLOCKED_APPS


def test_doctor_notify_flag_forwarded(monkeypatch):
    import sys

    from staff.doctor import Doctor

    captured = {}
    monkeypatch.setattr(Doctor, "run", lambda self, notify=False: captured.update(notify=notify))

    old_argv = sys.argv
    sys.argv = ["main.py", "doctor", "--notify"]
    try:
        main.main()
    finally:
        sys.argv = old_argv

    assert captured["notify"] is True


def test_doctor_without_flag_does_not_request_notify(monkeypatch):
    import sys

    from staff.doctor import Doctor

    captured = {}
    monkeypatch.setattr(Doctor, "run", lambda self, notify=False: captured.update(notify=notify))

    old_argv = sys.argv
    sys.argv = ["main.py", "doctor"]
    try:
        main.main()
    finally:
        sys.argv = old_argv

    assert captured["notify"] is False
