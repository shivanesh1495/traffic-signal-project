"""
Tests for FastAPI backend endpoints.

Tests every required endpoint: start, pause, reset, state, tick,
emergency/dispatch, network, metrics, events.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from backend.main import app
from backend.api.routes import get_engine


@pytest.fixture(autouse=True)
def reset_engine():
    """Reset simulation state before each test."""
    engine = get_engine()
    engine.reset()
    yield
    engine.reset()


@pytest.fixture
def client():
    return TestClient(app)


class TestNetworkEndpoint:
    def test_get_network(self, client):
        resp = client.get("/api/network")
        assert resp.status_code == 200
        data = resp.json()
        assert "intersections" in data
        assert len(data["intersections"]) == 5
        assert "edges" in data

    def test_network_has_five_intersections(self, client):
        resp = client.get("/api/network")
        data = resp.json()
        ids = set(data["intersections"].keys())
        assert ids == {"I1", "I2", "I3", "I4", "I5"}


class TestSimulationStart:
    def test_start_default_scenario(self, client):
        resp = client.post("/api/simulation/start", json={"scenario_id": "S1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

    def test_start_s0_scenario(self, client):
        resp = client.post("/api/simulation/start", json={"scenario_id": "S0"})
        assert resp.status_code == 200

    def test_state_after_start(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.get("/api/simulation/state")
        assert resp.status_code == 200
        state = resp.json()
        assert state["status"] == "running"


class TestSimulationPause:
    def test_pause_running_sim(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/simulation/pause")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("paused", "resumed")

    def test_pause_then_resume(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        client.post("/api/simulation/pause")   # -> paused
        resp = client.post("/api/simulation/pause")  # -> resumed
        assert resp.status_code == 200


class TestSimulationReset:
    def test_reset_returns_reset_status(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/simulation/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"

    def test_state_after_reset_is_idle(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        client.post("/api/simulation/reset")
        state = client.get("/api/simulation/state").json()
        assert state["status"] == "idle"
        assert state["current_time"] == 0.0


class TestSimulationTick:
    def test_tick_advances_time(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/simulation/tick")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tick"] == 1
        assert data["simulation_time"] == pytest.approx(1.0, abs=0.01)

    def test_tick_fails_when_not_started(self, client):
        resp = client.post("/api/simulation/tick")
        assert resp.status_code == 400

    def test_multiple_ticks_advance_correctly(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        for _ in range(5):
            client.post("/api/simulation/tick")
        state = client.get("/api/simulation/state").json()
        assert state["tick"] == 5
        assert state["current_time"] == pytest.approx(5.0, abs=0.01)


class TestEmergencyDispatch:
    def test_dispatch_returns_route(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/emergency/dispatch", json={
            "emergency_id": "EV01",
            "start_node": "I1",
            "destination": "I5",
            "vehicle_type": "ambulance",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dispatched"
        assert "route" in data
        assert data["route"][0] == "I1"
        assert data["route"][-1] == "I5"

    def test_dispatch_returns_eta_map(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/emergency/dispatch", json={
            "emergency_id": "EV01",
            "start_node": "I1",
            "destination": "I5",
            "vehicle_type": "ambulance",
        })
        data = resp.json()
        assert "eta_map" in data
        assert len(data["eta_map"]) > 0

    def test_dispatch_invalid_destination_returns_422(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        resp = client.post("/api/emergency/dispatch", json={
            "emergency_id": "EV01",
            "start_node": "I1",
            "destination": "IX_INVALID",
            "vehicle_type": "ambulance",
        })
        assert resp.status_code == 422

    def test_dispatch_fails_without_start(self, client):
        resp = client.post("/api/emergency/dispatch", json={
            "emergency_id": "EV01",
            "start_node": "I1",
            "destination": "I5",
            "vehicle_type": "ambulance",
        })
        assert resp.status_code == 400  # sim not started


class TestMetricsEndpoint:
    def test_metrics_endpoint_accessible(self, client):
        resp = client.get("/api/metrics")
        assert resp.status_code == 200

    def test_metrics_has_required_fields(self, client):
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "emergency_travel_time" in data
        assert "average_waiting_time" in data
        assert "throughput" in data
        assert "route_cost" in data


class TestEventsEndpoint:
    def test_events_endpoint_accessible(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200

    def test_events_returns_list(self, client):
        resp = client.get("/api/events")
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_events_populated_after_dispatch(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        client.post("/api/emergency/dispatch", json={
            "emergency_id": "EV01",
            "start_node": "I1",
            "destination": "I5",
            "vehicle_type": "ambulance",
        })
        # Run a few ticks to generate events
        for _ in range(5):
            client.post("/api/simulation/tick")
        resp = client.get("/api/events")
        events = resp.json()["events"]
        assert len(events) > 0


class TestSimulationStateContents:
    def test_state_has_all_required_fields(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        state = client.get("/api/simulation/state").json()
        assert "status" in state
        assert "current_time" in state
        assert "intersections" in state
        assert "edges" in state
        assert "signals" in state
        assert "vehicles" in state
        assert "emergency_vehicles" in state
        assert "metrics" in state

    def test_state_has_five_signal_states(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        state = client.get("/api/simulation/state").json()
        assert len(state["signals"]) == 5

    def test_vehicles_present_after_start(self, client):
        client.post("/api/simulation/start", json={"scenario_id": "S1"})
        state = client.get("/api/simulation/state").json()
        assert len(state["vehicles"]) > 0
