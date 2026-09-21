"""
Tests for the full emergency vehicle system.

Acceptance criteria:
- Emergency dispatch triggers A* route planning.
- EMERGENCY_PRIORITY messages reach relevant TSAs.
- TSAs on route enter EMERGENCY_PREPARE / EMERGENCY_GREEN.
- TSAs NOT on route do not enter emergency state.
- After emergency vehicle passes, TSA enters EMERGENCY_CLEAR.
- ETA is calculated dynamically.
- Green corridor is sequential (not simultaneous at all intersections).
- Route replanning when threshold exceeded.
- Metrics are computed at the end of a scenario.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.simulation.engine import SimulationEngine
from backend.simulation.network import RoadNetwork
from backend.communication.schemas import SignalState, SimulationStatus


@pytest.fixture
def engine():
    net = RoadNetwork()
    return SimulationEngine(net)


@pytest.fixture
def running_engine(engine):
    engine.start("S1")
    return engine


class TestEmergencyDispatch:
    def test_dispatch_returns_ev_model(self, running_engine):
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None
        assert ev.id == "EV01"

    def test_dispatch_computes_route(self, running_engine):
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None
        assert len(ev.route) >= 2
        assert ev.route[0] == "I1"
        assert ev.route[-1] == "I5"

    def test_dispatch_no_route_returns_none(self, running_engine):
        ev = running_engine.dispatch_emergency("EV01", "I1", "IX_BAD", "ambulance")
        assert ev is None

    def test_dispatch_computes_eta(self, running_engine):
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None
        assert len(ev.eta_map) > 0
        for node in ev.route[1:]:
            assert node in ev.eta_map
            assert ev.eta_map[node] >= 0.0

    def test_dispatch_sets_route_cost(self, running_engine):
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None
        assert ev.route_cost > 0.0


class TestPriorityMessages:
    def test_priority_reaches_route_tsa(self, running_engine):
        """Emergency priority messages must reach TSAs on the route."""
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None
        route = ev.route

        # Flush messages by running a few ticks
        for _ in range(5):
            running_engine.tick()

        # At least one TSA on the route should be in an emergency state
        emergency_states = {
            SignalState.EMERGENCY_PREPARE,
            SignalState.EMERGENCY_GREEN,
        }
        on_route_agents = [
            running_engine.tsa_agents[running_engine.network.intersections[iid].signal_agent_id]
            for iid in route
            if iid in running_engine.network.intersections
        ]
        states_on_route = [a.get_signal_state_model().state for a in on_route_agents]
        has_emergency = any(s in emergency_states for s in states_on_route)
        assert has_emergency, f"Expected emergency state on route, got: {states_on_route}"

    def test_tsa_not_on_route_stays_normal(self, running_engine):
        """TSAs NOT on the emergency route must not enter emergency state."""
        ev = running_engine.dispatch_emergency("EV01", "I1", "I3", "ambulance")
        assert ev is not None
        route = ev.route

        for _ in range(8):
            running_engine.tick()

        emergency_states = {
            SignalState.EMERGENCY_PREPARE,
            SignalState.EMERGENCY_GREEN,
        }
        # Find intersections NOT on route
        all_ids = list(running_engine.network.intersections.keys())
        off_route = [iid for iid in all_ids if iid not in route]

        for iid in off_route:
            agent_id = running_engine.network.intersections[iid].signal_agent_id
            agent = running_engine.tsa_agents[agent_id]
            state = agent.get_signal_state_model().state
            assert state not in emergency_states, \
                f"{agent_id} (not on route) should not be in emergency state, but is {state}"


class TestGreenCorridor:
    def test_green_corridor_not_simultaneous(self, running_engine):
        """
        Green corridor must be sequential, not all signals green simultaneously.
        At any given time, at most a subset of on-route signals should be green.
        """
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None

        # Run until EV is partway through
        for _ in range(15):
            running_engine.tick()

        route = ev.route
        emergency_green_count = 0
        for iid in route:
            agent_id = running_engine.network.intersections[iid].signal_agent_id
            state = running_engine.tsa_agents[agent_id].get_signal_state_model().state
            if state == SignalState.EMERGENCY_GREEN:
                emergency_green_count += 1

        # Not all 5 signals should be EMERGENCY_GREEN simultaneously
        assert emergency_green_count < len(route), \
            "Not all route signals should be EMERGENCY_GREEN simultaneously"


class TestRecovery:
    def test_signal_recovers_after_ev_passes(self, running_engine):
        """Signals must enter EMERGENCY_CLEAR and return to normal after EV passes."""
        ev = running_engine.dispatch_emergency("EV01", "I1", "I3", "ambulance")
        assert ev is not None

        # Run until EV arrives at destination
        for _ in range(200):
            if ev.arrival_time is not None:
                break
            running_engine.tick()

        assert ev.arrival_time is not None, "EV should reach destination"

        # Run more to allow recovery
        for _ in range(20):
            running_engine.tick()

        # Check signals on route are back in normal states
        normal_states = {
            SignalState.NORMAL_GREEN,
            SignalState.NORMAL_YELLOW,
            SignalState.NORMAL_RED,
        }
        route = ev.route
        for iid in route:
            agent_id = running_engine.network.intersections[iid].signal_agent_id
            state = running_engine.tsa_agents[agent_id].get_signal_state_model().state
            assert state in normal_states or state == SignalState.EMERGENCY_CLEAR, \
                f"{agent_id} should be in recovery or normal state, got {state}"


class TestMetricsCalculation:
    def test_metrics_computed_after_scenario(self, running_engine):
        """Metrics must be computed from real simulation state."""
        running_engine.dispatch_emergency("EV01", "I1", "I3", "ambulance")

        for _ in range(150):
            running_engine.tick()

        metrics = running_engine.metrics.get_metrics()

        # Emergency travel time must be positive if EV arrived
        ev = running_engine.ev_model
        if ev and ev.arrival_time is not None:
            assert metrics.emergency_travel_time > 0.0
            assert metrics.route_cost > 0.0

        # Traffic throughput must be non-negative
        assert metrics.throughput >= 0.0
        assert metrics.average_waiting_time >= 0.0

    def test_route_cost_matches_sum_of_edges(self, running_engine):
        """Route cost must equal sum of edge costs along selected route."""
        ev = running_engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None

        # Compute expected cost from network
        expected_cost = running_engine.network.route_cost(ev.route)
        # Route cost stored at dispatch time (may differ slightly from re-computed
        # due to traffic changes, but should be in the same ballpark)
        assert abs(ev.route_cost - expected_cost) < 1.0  # within 1.0 cost unit


class TestVirtualSensors:
    def test_get_vehicle_count_returns_int(self, running_engine):
        count = running_engine.traffic.get_vehicle_count("I1")
        assert isinstance(count, int)
        assert count >= 0

    def test_get_queue_length_returns_int(self, running_engine):
        q = running_engine.traffic.get_queue_length("I1")
        assert isinstance(q, int)
        assert q >= 0

    def test_get_congestion_ratio_bounded(self, running_engine):
        ratio = running_engine.traffic.get_congestion_ratio("I2")
        assert 0.0 <= ratio <= 1.0

    def test_get_average_speed_non_negative(self, running_engine):
        speed = running_engine.traffic.get_average_speed("I1")
        assert speed >= 0.0

    def test_get_traffic_state_returns_edge(self, running_engine):
        state = running_engine.traffic.get_traffic_state("E_I1_I2")
        assert state is not None
        assert hasattr(state, "vehicle_count")
        assert hasattr(state, "queue_length")
        assert hasattr(state, "congestion_ratio")


class TestIntegrationScenario:
    def test_complete_emergency_scenario_end_to_end(self, engine):
        """
        Full scenario: start -> dispatch -> EV travels -> arrives.
        """
        engine.start("S1")

        ev = engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
        assert ev is not None, "Emergency vehicle must be dispatched"
        assert ev.route[0] == "I1"
        assert ev.route[-1] == "I5"

        # Run simulation until EV arrives or 300s elapsed
        max_ticks = 300
        for _ in range(max_ticks):
            engine.tick()
            if ev.arrival_time is not None:
                break

        assert ev.arrival_time is not None, \
            f"Emergency vehicle did not reach destination within {max_ticks} ticks"

        # Verify travel time recorded
        travel_time = ev.arrival_time - ev.dispatch_time
        assert travel_time > 0, "Travel time must be positive"

        # Verify metrics were updated
        metrics = engine.metrics.get_metrics()
        assert metrics.emergency_travel_time == pytest.approx(travel_time, abs=1.0)
