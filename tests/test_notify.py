"""Tests for staff/notify.py — subprocess argument construction for both the
terminal-notifier and osascript paths.

These force each path deterministically by monkeypatching NOTIFIER to a path
that either does or doesn't exist, rather than depending on whether the CI
runner happens to have terminal-notifier installed.
"""

from staff import notify


def test_terminal_notifier_path_builds_expected_args(
    tmp_path, monkeypatch, no_real_notifications
):
    fake_notifier = tmp_path / "terminal-notifier"
    fake_notifier.write_text("#!/bin/sh\n")
    monkeypatch.setattr(notify, "NOTIFIER", str(fake_notifier))

    notify.notify("Serge", "file.pdf → Documents")

    calls = no_real_notifications
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == str(fake_notifier)
    assert "-title" in cmd and "GBH  ·  Serge" in cmd
    assert "-message" in cmd and "file.pdf → Documents" in cmd
    assert "-subtitle" in cmd and "File Sorter" in cmd
    assert "-sound" in cmd and "Tink" in cmd  # Serge's per-staff sound
    assert "-sender" in cmd and "com.gbh.concierge" in cmd


def test_terminal_notifier_omits_sound_flag_when_default(
    tmp_path, monkeypatch, no_real_notifications
):
    fake_notifier = tmp_path / "terminal-notifier"
    fake_notifier.write_text("#!/bin/sh\n")
    monkeypatch.setattr(notify, "NOTIFIER", str(fake_notifier))

    notify.notify("Unknown Staff Member", "hello")

    cmd = no_real_notifications[0]
    assert "-sound" not in cmd  # STAFF_SOUNDS default is the string "default"


def test_osascript_fallback_used_when_notifier_missing(
    tmp_path, monkeypatch, no_real_notifications
):
    monkeypatch.setattr(notify, "NOTIFIER", str(tmp_path / "does-not-exist"))

    notify.notify("Ivan", "Blocking distractions for 25 minutes.")

    calls = no_real_notifications
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "osascript"
    script = cmd[2]
    assert "display notification" in script
    assert "Blocking distractions for 25 minutes." in script
    assert "Focus Mode" in script  # Ivan's subtitle


def test_urgent_overrides_default_sound(tmp_path, monkeypatch, no_real_notifications):
    """Regression test: `urgent` was accepted as a parameter and documented
    ("uses a more attention-grabbing sound") but never actually consulted —
    passing urgent=True changed nothing. Doctor's outage alert relies on it
    landing louder than a routine per-staff sound."""
    fake_notifier = tmp_path / "terminal-notifier"
    fake_notifier.write_text("#!/bin/sh\n")
    monkeypatch.setattr(notify, "NOTIFIER", str(fake_notifier))

    notify.notify("Gustave", "something's actually wrong", urgent=True)

    cmd = no_real_notifications[0]
    assert "-sound" in cmd
    assert cmd[cmd.index("-sound") + 1] == "Basso"


def test_explicit_sound_still_wins_over_urgent(tmp_path, monkeypatch, no_real_notifications):
    fake_notifier = tmp_path / "terminal-notifier"
    fake_notifier.write_text("#!/bin/sh\n")
    monkeypatch.setattr(notify, "NOTIFIER", str(fake_notifier))

    notify.notify("Gustave", "msg", sound="Frog", urgent=True)

    cmd = no_real_notifications[0]
    assert cmd[cmd.index("-sound") + 1] == "Frog"


def test_osascript_escapes_quotes_in_message(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "NOTIFIER", str(tmp_path / "does-not-exist"))

    notify.notify("Gustave", 'Disk has "low" space')

    script = no_real_notifications[0][2]
    assert '\\"low\\"' in script
