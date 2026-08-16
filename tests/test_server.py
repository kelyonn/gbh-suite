"""Tests for server.py — API shape and the Host/Origin regression fixed in
Phase 2. Every test here fully sandboxes Ivan (via gbh_home +
no_real_network_side_effects) and redirects server.ZERO_LOG into tmp_path,
because get_vitals() and /api/clean both touch real machine state otherwise.

The TestClient is built without entering it as a context manager, so the
app's lifespan (which starts a background broadcast loop) never runs — the
routes under test don't depend on it, and skipping it means we never risk
that loop's own periodic Zero.clean_screenshots() call touching a real
Desktop mid-test-suite.
"""

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client(gbh_home, no_real_network_side_effects, monkeypatch):
    monkeypatch.setattr(server, "ZERO_LOG", gbh_home.data_dir / "zero_last_run.txt")
    return TestClient(server.app, base_url="http://127.0.0.1:2525")


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "gbh-concierge-v2"}


def test_vitals_endpoint_shape(client):
    resp = client.get("/api/vitals")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "cpu_percent", "ram_percent", "disk_free", "battery_percent",
        "battery_plugged", "staff", "focus", "zero_last_run", "ports",
        "serge_moves_today",
    ):
        assert key in body
    assert isinstance(body["ports"], list)
    assert set(body["staff"].keys()) == {"serge", "dimitri", "jopling", "henckels", "server"}
    assert body["focus"] == {
        "active": False, "paused": False, "remaining_sec": 0,
        "duration_min": 0, "ends_at": None,
    }


def test_serge_log_endpoint_empty_by_default(client):
    resp = client.get("/api/serge/log")
    assert resp.status_code == 200
    assert resp.json() == {"moves": []}


# ── Host header validation (regression: forged Host used to be accepted) ──

def test_forged_host_header_rejected(client):
    resp = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert resp.status_code == 400


def test_legitimate_host_header_accepted(client):
    resp = client.get("/api/health", headers={"Host": "127.0.0.1:2525"})
    assert resp.status_code == 200


def test_localhost_host_header_accepted(client):
    resp = client.get("/api/health", headers={"Host": "localhost:2525"})
    assert resp.status_code == 200


# ── Cross-origin / cross-site POST rejection ───────────────────────────────

def test_cross_site_post_rejected_via_sec_fetch_site(client):
    resp = client.post("/api/clean", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403


def test_cross_origin_post_rejected_via_origin_header(client):
    resp = client.post("/api/clean", headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403


def test_same_origin_post_accepted_via_sec_fetch_site(client):
    resp = client.post(
        "/api/clean",
        headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://127.0.0.1:2525"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_plain_post_with_no_origin_signal_still_accepted(client):
    """Non-browser clients (curl, local scripts) send neither Sec-Fetch-Site
    nor Origin. They must keep working — the guard is scoped to browsers."""
    resp = client.post("/api/clean")
    assert resp.status_code == 200


def test_get_requests_are_never_blocked_by_origin_guard(client):
    """The guard only applies to mutating methods; a cross-site GET is still
    just a GET (read-only), which is what TrustedHostMiddleware and normal
    browser same-origin policy already govern."""
    resp = client.get("/api/vitals", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 200


# ── WebSocket host validation ───────────────────────────────────────────
# TrustedHostMiddleware checks scope["type"] in ("http", "websocket"), so the
# same forged-Host defense must hold for the /ws/vitals upgrade too — this is
# the one endpoint the Origin guard above doesn't cover, since it's not a
# POST/PUT/PATCH/DELETE.

def test_websocket_with_forged_host_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/vitals", headers={"Host": "evil.example.com"}):
            pass


def test_websocket_with_legitimate_host_connects(client):
    with client.websocket_connect("/ws/vitals", headers={"Host": "127.0.0.1:2525"}) as ws:
        ws.close()


# ── Phase 5: broadcast-loop fast/slow split and the serge-count cache ─────

def test_fast_and_slow_vitals_together_cover_every_dataclass_field(
    gbh_home, no_real_network_side_effects
):
    """Regression test for the fast/slow split: _compute_fast_vitals() and
    _compute_slow_vitals() together must supply exactly the Vitals dataclass's
    constructor fields, no more and no less — that's what guarantees
    Vitals(**fast, **slow) in both get_vitals() and broadcast_loop() actually
    constructs (no missing/unexpected kwargs) and produces the same payload
    shape the frontend has always received."""
    import dataclasses

    fast = server._compute_fast_vitals()
    slow = server._compute_slow_vitals()

    expected_fields = {f.name for f in dataclasses.fields(server.Vitals)}
    assert set(fast) | set(slow) == expected_fields
    assert set(fast) & set(slow) == set()  # no field computed by both

    # Must actually construct without error, exactly like both call sites do.
    vitals = server.Vitals(**fast, **slow)
    assert vitals.to_dict()["staff"] == dataclasses.asdict(slow["staff"])


def test_serge_moves_today_cache_hit_skips_reparsing(gbh_home):
    """Regression test: the old implementation re-read and re-parsed the
    entire jsonl file on every call (twice a second, forever, in the
    broadcast loop) and did `import json` inside that per-line loop.

    Proven directly rather than by spying on Path.read_text (which would
    have to be patched at the Path class level, risking interference with
    unrelated code running during the test): plant an impossible sentinel
    count in the cache dict alongside the file's real (mtime, size, date).
    If _serge_moves_today() actually re-reads and re-parses the file when
    called again, the true count would overwrite the sentinel. If it trusts
    the cache — the behavior being tested — the sentinel comes straight
    back.
    """
    import server as server_mod
    from staff import serge as serge_mod

    serge_mod._log_move("/src/a.png", "/dst/a.png", "Images")
    server_mod._serge_moves_today()  # populate the cache with real values

    st = serge_mod.MOVE_LOG.stat()
    today = server_mod.datetime.now().date().isoformat()
    server_mod._serge_moves_cache.update(
        mtime=st.st_mtime, size=st.st_size, date=today, count=999999
    )

    assert server_mod._serge_moves_today() == 999999


def test_serge_moves_today_cache_invalidates_on_new_move(gbh_home):
    import server as server_mod
    from staff import serge as serge_mod

    serge_mod._log_move("/src/a.png", "/dst/a.png", "Images")
    assert server_mod._serge_moves_today() == 1

    serge_mod._log_move("/src/b.png", "/dst/b.png", "Images")
    assert server_mod._serge_moves_today() == 2


def test_serge_moves_today_missing_file_returns_zero(gbh_home):
    import server as server_mod
    assert server_mod._serge_moves_today() == 0
