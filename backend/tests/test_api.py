"""API endpoint tests."""

from __future__ import annotations

import time


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["simulated"] is True
    assert body["current_state"] == "ONLINE_AGENT"


def test_ready(client):
    assert client.get("/api/v1/ready").json()["ready"] is True


def test_system_status_and_state(client):
    status = client.get("/api/v1/system/status").json()
    assert status["current_state"] == "ONLINE_AGENT"
    assert status["controller_authority"] == "agent"
    state = client.get("/api/v1/system/state").json()
    assert state["current_state"] == "ONLINE_AGENT"


def test_simulation_controls(client):
    assert client.post("/api/v1/simulation/scenario", json={"scenario": "heatwave"}).status_code == 200
    assert client.post("/api/v1/simulation/agent", json={"mode": "unsafe_angle"}).status_code == 200
    assert client.post("/api/v1/simulation/failure", json={"mode": "timeout"}).status_code == 200
    state = client.get("/api/v1/simulation/state").json()
    assert state["device"]["scenario"] == "heatwave"
    assert state["transport_failure_mode"] == "timeout"
    assert client.post("/api/v1/simulation/scenario", json={"scenario": "nope"}).status_code == 422


def test_safety_validate_dry_run(client):
    response = client.post(
        "/api/v1/safety/validate",
        json={
            "proposal_id": "p-1",
            "action": "servo_move",
            "parameters": {"angle_degrees": 250},
            "source": "agent",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is False
    assert body["reason_code"] == "ANGLE_OUT_OF_RANGE"
    assert body["checks"]["range"] == "FAIL"


def test_unknown_action_at_api_boundary(client):
    response = client.post(
        "/api/v1/actions/propose", json={"action": "fly_drone", "parameters": {}}
    )
    assert response.status_code == 422


def test_telemetry_latest_is_flagged_simulated(live_client):
    # Allow a few control cycles to run.
    time.sleep(0.3)
    body = live_client.get("/api/v1/telemetry/latest").json()
    assert body["available"] is True
    assert body["simulated"] is True
    assert "temperature_c" in body["readings"]
    assert body["readings"]["temperature_c"]["simulated"] is True


def test_telemetry_history(live_client):
    time.sleep(0.3)
    body = live_client.get("/api/v1/telemetry/history?sensor=temperature_c").json()
    assert body["total"] > 0
    assert all(item["sensor"] == "temperature_c" for item in body["items"])


def test_events_are_recorded_and_filterable(live_client):
    time.sleep(0.3)
    body = live_client.get("/api/v1/events").json()
    assert body["total"] > 0
    first_category = body["items"][0]["category"]
    filtered = live_client.get(f"/api/v1/events?category={first_category}").json()
    assert all(item["category"] == first_category for item in filtered["items"])


def test_events_export_csv(live_client):
    time.sleep(0.3)
    response = live_client.get("/api/v1/events/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "event_id" in response.text


def test_events_stats(live_client):
    time.sleep(0.3)
    body = live_client.get("/api/v1/events/stats").json()
    assert "by_category" in body
    assert isinstance(body["by_category"], dict)


def test_event_not_found(client):
    assert client.get("/api/v1/events/does-not-exist").status_code == 404


def test_valid_proposal_is_approved_and_dispatched(live_client):
    time.sleep(0.3)
    response = live_client.post(
        "/api/v1/actions/propose",
        json={"action": "servo_move", "parameters": {"angle_degrees": 90}, "reason": "api test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["approved"] is True
    assert body["command"]["status"] in ("ACKNOWLEDGED", "STATE_CONFIRMED")


def test_unsafe_proposal_is_rejected_and_not_dispatched(live_client):
    time.sleep(0.3)
    response = live_client.post(
        "/api/v1/actions/propose",
        json={"action": "servo_move", "parameters": {"angle_degrees": 250}, "reason": "unsafe"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"]["approved"] is False
    assert body["command"] is None


def test_commands_and_latest(live_client):
    time.sleep(0.3)
    live_client.post(
        "/api/v1/actions/propose",
        json={"action": "set_status_led", "parameters": {"color": "green"}},
    )
    body = live_client.get("/api/v1/actions/commands").json()
    assert body["total"] > 0
    latest = live_client.get("/api/v1/actions/latest").json()
    assert latest["decision"] is not None


def test_system_lockdown_and_reset(client):
    # Uses the loop-disabled client so state transitions are deterministic.
    lockdown = client.post("/api/v1/system/lockdown")
    assert lockdown.status_code == 200
    assert lockdown.json()["new_state"] == "SAFE_LOCKDOWN"

    reset = client.post("/api/v1/system/reset")
    assert reset.status_code == 200
    assert reset.json()["new_state"] == "RECOVERY"

    # RECOVERY -> DEGRADED is not an allowed transition.
    illegal = client.post(
        "/api/v1/system/state",
        json={"state": "DEGRADED", "reason_code": "MANUAL_OVERRIDE", "reason": "x"},
    )
    assert illegal.status_code == 409

    # SAFE_LOCKDOWN may only exit to RECOVERY.
    client.post("/api/v1/system/lockdown")
    bad_exit = client.post(
        "/api/v1/system/state",
        json={"state": "ONLINE_AGENT", "reason_code": "MANUAL_OVERRIDE", "reason": "x"},
    )
    assert bad_exit.status_code == 409


def test_system_transitions_recorded(client):
    client.post("/api/v1/system/lockdown")
    body = client.get("/api/v1/system/transitions").json()
    assert body["total"] >= 1
    assert body["items"][0]["new_state"] == "SAFE_LOCKDOWN"


def test_websocket_snapshot_and_ping(live_client):
    with live_client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert "system" in message["data"]
        assert message["data"]["simulated"] is True

        websocket.send_json({"type": "ping"})
        # Drain any broadcast messages until we see the pong.
        for _ in range(50):
            reply = websocket.receive_json()
            if reply["type"] == "pong":
                break
        else:  # pragma: no cover
            raise AssertionError("No pong received")


# ---------------------------------------------------------------------------
# Newer endpoints: telemetry ingest, predefined safety tests, decisions alias
# ---------------------------------------------------------------------------
def test_telemetry_ingest(client):
    response = client.post(
        "/api/v1/telemetry/ingest",
        json={
            "device_id": "esp32s3-clawsense-01",
            "simulated": False,
            "readings": {
                "temperature_c": {"value": 21.5, "unit": "C", "status": "OK"},
                "humidity_percent": {"value": 44.0, "unit": "%", "status": "OK"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["readings"] == 2

    latest = client.get("/api/v1/telemetry/latest").json()
    assert latest["available"] is True
    assert latest["simulated"] is False
    assert latest["readings"]["temperature_c"]["value"] == 21.5


def test_telemetry_ingest_rejects_bad_payload(client):
    response = client.post("/api/v1/telemetry/ingest", json={"readings": {}})
    assert response.status_code == 422


def test_predefined_safety_tests_all_pass(client):
    response = client.post("/api/v1/safety/test")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "software_validation"
    assert body["hardware_tested"] is False
    assert body["total"] == 6
    assert body["passed"] == 6, [r["key"] for r in body["results"] if not r["passed"]]

    by_key = {item["key"]: item for item in body["results"]}
    assert by_key["valid_servo_command"]["result"]["approved"] is True
    assert by_key["out_of_range_servo_angle"]["result"]["reason_code"] == "ANGLE_OUT_OF_RANGE"
    assert by_key["unknown_action"]["result"]["reason_code"] == "UNKNOWN_ACTION"
    assert by_key["malformed_command"]["result"]["reason_code"] == "SCHEMA_INVALID"
    assert by_key["invalid_operating_state"]["result"]["reason_code"] == "INVALID_SYSTEM_STATE"
    assert by_key["duplicate_command"]["result"]["approved"] is False
    # Rejected proposals must never be dispatched.
    assert by_key["out_of_range_servo_angle"]["result"]["dispatch_attempted"] is False


def test_safety_events_endpoint(client):
    client.post(
        "/api/v1/safety/validate",
        json={
            "proposal_id": "p-safety-events",
            "action": "servo_move",
            "parameters": {"angle_degrees": 250},
            "source": "agent",
        },
    )
    # The dry-run endpoint does not persist; trigger a real rejection instead.
    client.post(
        "/api/v1/actions/propose",
        json={"action": "servo_move", "parameters": {"angle_degrees": 250}},
    )
    body = client.get("/api/v1/safety/events").json()
    assert body["total"] >= 1
    assert all(
        item["category"] in ("safety_approval", "safety_rejection")
        for item in body["items"]
    )


def test_decisions_alias(client):
    response = client.post(
        "/api/v1/decisions/propose",
        json={"action": "servo_move", "parameters": {"angle_degrees": 250}},
    )
    assert response.status_code == 200
    assert response.json()["decision"]["approved"] is False

    listing = client.get("/api/v1/decisions").json()
    assert listing["total"] >= 1
    decision_id = listing["items"][0]["decision_id"]
    single = client.get(f"/api/v1/decisions/{decision_id}")
    assert single.status_code == 200
    assert client.get("/api/v1/decisions/nope").status_code == 404
