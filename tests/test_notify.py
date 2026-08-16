"""Tests for staff/notify.py — delivery cascade, no silent -sender, audit log."""

import json

from staff import notify


def test_osascript_primary_path_succeeds(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)  # force osascript only

    ok = notify.notify("Serge", "file.pdf → Documents")

    assert ok is True
    calls = no_real_notifications
    assert len(calls) >= 1
    assert calls[0][0] == "osascript"
    script = calls[0][2]
    assert "display notification" in script
    assert "file.pdf → Documents" in script
    assert "GBH  ·  Serge" in script

    audit = json.loads((tmp_path / "notify_audit.jsonl").read_text().strip().splitlines()[-1])
    assert audit["ok"] is True
    assert audit["via"] == "osascript"
    assert audit["staff"] == "Serge"


def test_never_passes_sender_flag(tmp_path, monkeypatch, no_real_notifications):
    """Regression: -sender com.gbh.concierge silently dropped banners for months."""
    fake = tmp_path / "terminal-notifier"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)

    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    # Make osascript fail so we exercise terminal-notifier path
    monkeypatch.setattr(notify, "_send_osascript", lambda *a, **k: False)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: str(fake))
    monkeypatch.setattr(notify, "_tn_list", lambda *a, **k: True)

    notify.notify("Ludwig", "weekly digest")

    tn_calls = [c for c in no_real_notifications if c and "terminal-notifier" in str(c[0])]
    assert tn_calls, f"expected terminal-notifier call, got {no_real_notifications}"
    cmd = tn_calls[0]
    assert "-sender" not in cmd
    assert "-group" in cmd
    assert "-title" in cmd


def test_falls_back_to_terminal_notifier_when_osascript_fails(
    tmp_path, monkeypatch, no_real_notifications
):
    fake = tmp_path / "terminal-notifier"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)

    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_send_osascript", lambda *a, **k: False)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: str(fake))
    monkeypatch.setattr(notify, "_tn_list", lambda *a, **k: True)

    ok = notify.notify("Kovacs", "13 uncommitted")
    assert ok is True
    audit = json.loads((tmp_path / "notify_audit.jsonl").read_text().strip().splitlines()[-1])
    assert audit["via"] == "terminal-notifier"
    assert audit["ok"] is True


def test_returns_false_and_audits_when_all_paths_fail(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_send_osascript", lambda *a, **k: False)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)

    ok = notify.notify("Doctor", "should fail")
    assert ok is False
    audit = json.loads((tmp_path / "notify_audit.jsonl").read_text().strip().splitlines()[-1])
    assert audit["ok"] is False
    assert audit["via"] is None


def test_urgent_uses_basso(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)

    notify.notify("Gustave", "outage", urgent=True)

    script = no_real_notifications[0][2]
    assert "Basso" in script


def test_explicit_sound_wins_over_urgent(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)

    notify.notify("Gustave", "msg", sound="Frog", urgent=True)
    script = no_real_notifications[0][2]
    assert "Frog" in script
    assert "Basso" not in script


def test_osascript_escapes_quotes(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)

    notify.notify("Gustave", 'Disk has "low" space')
    script = no_real_notifications[0][2]
    assert '\\"low\\"' in script


def test_probe_reports_failure_clearly(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(notify, "AUDIT_LOG", tmp_path / "notify_audit.jsonl")
    monkeypatch.setattr(notify, "GBH_DATA", tmp_path)
    monkeypatch.setattr(notify, "_send_osascript", lambda *a, **k: False)
    monkeypatch.setattr(notify, "_resolve_notifier", lambda: None)

    result = notify.probe()
    assert result["ok"] is False
    assert result["fix_hint"]
    assert "terminal-notifier" in result["detail"] or "osascript" in result["detail"]
