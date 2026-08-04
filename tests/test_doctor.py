"""Tests for staff/doctor.py — specifically the `--notify` behavior added in
this pass: notify only when something's actually broken, never on a clean
run, matching the "never nags" convention the rest of the suite (Kovacs,
Ludwig) already follows.
"""

import pytest

from staff import doctor


@pytest.fixture
def spy_notify(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "_send_notify", lambda *a, **kw: calls.append((a, kw)))
    return calls


def _stub_all_checks(monkeypatch, *, daemon_lines):
    """Force every section except daemons to report healthy, and control the
    daemons section directly — enough surface to drive the pass/fail path
    without needing a real LaunchAgent or a real dashboard listening."""
    monkeypatch.setattr(doctor, "check_daemons", lambda: daemon_lines)
    monkeypatch.setattr(doctor, "check_dashboard", lambda: [doctor._ok("Dashboard responding")])
    monkeypatch.setattr(doctor, "check_data_dir", lambda: [doctor._ok("~/.gbh/ exists")])
    monkeypatch.setattr(doctor, "check_tools", lambda: [doctor._ok("terminal-notifier installed")])
    monkeypatch.setattr(doctor, "check_focus_state", lambda: [doctor._ok("no active session")])


def test_no_notification_when_everything_is_healthy(monkeypatch, spy_notify):
    _stub_all_checks(monkeypatch, daemon_lines=[doctor._ok("Serge")])

    with pytest.raises(SystemExit) as exc:
        doctor.Doctor().run(notify=True)

    assert exc.value.code == 0
    assert spy_notify == []


def test_notifies_once_when_an_issue_is_found(monkeypatch, spy_notify):
    _stub_all_checks(monkeypatch, daemon_lines=[doctor._err("Server — not loaded")])

    with pytest.raises(SystemExit) as exc:
        doctor.Doctor().run(notify=True)

    assert exc.value.code == 1
    assert len(spy_notify) == 1
    args, kwargs = spy_notify[0]
    assert args[0] == "Doctor"
    assert "Server" in args[1]
    assert kwargs.get("urgent") is True


def test_no_notification_when_notify_flag_is_off_even_with_issues(monkeypatch, spy_notify):
    """`gbh doctor` (no flag) must stay exactly as before: a printed report,
    no notification, regardless of findings."""
    _stub_all_checks(monkeypatch, daemon_lines=[doctor._err("Server — not loaded")])

    with pytest.raises(SystemExit) as exc:
        doctor.Doctor().run(notify=False)

    assert exc.value.code == 1
    assert spy_notify == []


def test_notification_summarizes_multiple_issues(monkeypatch, spy_notify):
    _stub_all_checks(
        monkeypatch,
        daemon_lines=[
            doctor._err("Server — not loaded"),
            doctor._warn("Dimitri — loaded but not running"),
        ],
    )

    with pytest.raises(SystemExit):
        doctor.Doctor().run(notify=True)

    message = spy_notify[0][0][1]
    assert "2 issue" in message
    assert "Server" in message
    assert "Dimitri" in message
