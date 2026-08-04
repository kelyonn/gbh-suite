"""Tests for staff/ivan.py — PAC generation, history bucketing, and the two
correctness bugs fixed in this pass: the expiry path skipping app-resume, and
pomodoro() dropping blocked_apps.
"""

import json
from datetime import datetime, timedelta

from staff import ivan


def test_write_pac_includes_domain_and_www_variant(gbh_home):
    path = ivan._write_pac(["reddit.com"])

    content = ivan.PAC_FILE.read_text()
    assert path == str(ivan.PAC_FILE)
    assert '"reddit.com"' in content
    assert '"www.reddit.com"' in content
    assert f"127.0.0.1:{ivan.BLOCK_PORT}" in content


def test_write_pac_lowercases_and_dedupes(gbh_home):
    ivan._write_pac(["Reddit.com", "www.reddit.com"])

    content = ivan.PAC_FILE.read_text()
    # Only one of each variant should appear, despite mixed case and an
    # explicit www. entry duplicating the auto-added one.
    assert content.count('"reddit.com"') == 1
    assert content.count('"www.reddit.com"') == 1


def test_write_pac_output_is_syntactically_plausible_js(gbh_home):
    ivan._write_pac(["example.com"])

    content = ivan.PAC_FILE.read_text()
    assert "function FindProxyForURL(url, host)" in content
    assert content.count("{") == content.count("}")


def test_get_history_buckets_by_date_within_window(gbh_home):
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    outside_window = today - timedelta(days=10)

    ivan.GBH_DATA.mkdir(exist_ok=True)
    with open(ivan.FOCUS_HISTORY, "w") as f:
        f.write(json.dumps({"date": today.isoformat(), "focused_sec": 600}) + "\n")
        f.write(json.dumps({"date": today.isoformat(), "focused_sec": 300}) + "\n")
        f.write(json.dumps({"date": yesterday.isoformat(), "focused_sec": 900}) + "\n")
        f.write(json.dumps({"date": outside_window.isoformat(), "focused_sec": 99999}) + "\n")

    history = ivan.get_history(days=7)
    by_date = {h["date"]: h for h in history}

    assert len(history) == 7  # one bucket per day in the window, zero-filled
    assert by_date[today.isoformat()]["total_sec"] == 900
    assert by_date[today.isoformat()]["sessions"] == 2
    assert by_date[yesterday.isoformat()]["total_sec"] == 900
    assert outside_window.isoformat() not in by_date


def test_get_history_on_missing_file_returns_empty(gbh_home):
    assert ivan.get_history(days=7) == []


def test_status_when_no_session_active(gbh_home):
    status = ivan.Ivan().status()
    assert status == {"active": False, "paused": False, "remaining_sec": 0,
                       "duration_min": 0, "ends_at": None}


def test_status_on_expired_session_resumes_apps_and_records_history(
    gbh_home, no_real_network_side_effects
):
    """Regression test for the bug where status() detecting an expired
    session (e.g. after a reboot, or simply the next poll after end-of-timer)
    unblocked sites and cleared state but never SIGCONT'd the apps it had
    SIGSTOP'd — they stayed frozen until the machine was rebooted — and never
    recorded the session to focus_history.jsonl.
    """
    started_at = datetime.now() - timedelta(minutes=30)
    ends_at = datetime.now() - timedelta(seconds=5)  # already expired
    ivan._write_state({
        "active": True,
        "started_at": started_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "duration_min": 25,
        "blocklist": ["reddit.com"],
        "blocked_apps": ["Slack"],
        "suspended_app_pids": {"Slack": 4242},
        "paused": False,
        "paused_at": None,
        "remaining_at_pause_sec": None,
    })

    status = ivan.Ivan().status()

    assert status["active"] is False
    assert no_real_network_side_effects["unblocked"] == 1
    assert no_real_network_side_effects["resumed"] == [{"Slack": 4242}]
    assert not ivan.FOCUS_STATE_FILE.exists()

    history_lines = ivan.FOCUS_HISTORY.read_text().strip().splitlines()
    assert len(history_lines) == 1
    record = json.loads(history_lines[0])
    assert record["duration_min"] == 25


def test_pomodoro_forwards_blocked_apps_to_start(gbh_home, monkeypatch):
    """Regression test: pomodoro() used to call self.start(minutes, blocklist)
    without blocked_apps, so app suspension silently no-op'd for every
    pomodoro cycle even when the user had configured FOCUS_BLOCKED_APPS."""
    captured = []
    monkeypatch.setattr(ivan.Ivan, "start", lambda self, *a: captured.append(a))

    ivan.Ivan().pomodoro(["reddit.com"], cycles=1, blocked_apps=["Slack", "Discord"])

    assert captured == [(25, ["reddit.com"], ["Slack", "Discord"])]
