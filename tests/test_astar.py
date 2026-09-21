"""
Tests for A* route planning algorithm.

Acceptance criteria:
- A* returns a valid route when a path exists.
- A* returns None with clear failure when destination is unreachable.
- The selected route starts at the emergency vehicle's current node and ends at destination.
- Changing traffic conditions changes edge costs.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.simulation.network import RoadNetwork
from backend.algorithms.astar import AStarRouter


@pytest.fixture
def network():
    return RoadNetwork()


@pytest.fixture
def router(network):
    return AStarRouter(network, max_emergency_speed_kmh=60.0)


class TestAStarBasic:
    def test_valid_route_i1_to_i5(self, router):
        """A* finds a valid route between I1 and I5."""
        route, cost = router.find_route("I1", "I5")
        assert route is not None, "Expected a route but got None"
        assert len(route) >= 2, "Route must have at least 2 nodes"
        assert route[0] == "I1"
        assert route[-1] == "I5"
        assert cost < float("inf")

    def test_valid_route_i2_to_i3(self, router):
        """A* finds a direct path from I2 to I3."""
        route, cost = router.find_route("I2", "I3")
        assert route is not None
        assert route[0] == "I2"
        assert route[-1] == "I3"

    def test_route_same_node(self, router):
        """A* returns trivial route when start == goal."""
        route, cost = router.find_route("I3", "I3")
        assert route == ["I3"]
        assert cost == 0.0

    def test_unreachable_destination(self, router, network):
        """A* returns None when destination does not exist."""
        route, cost = router.find_route("I1", "IX_NONEXISTENT")
        assert route is None
        assert cost == float("inf")

    def test_unreachable_start(self, router):
        """A* returns None when start does not exist."""
        route, cost = router.find_route("IX_BAD", "I5")
        assert route is None

    def test_all_intersections_reachable(self, router):
        """All intersections are reachable from I1."""
        for dest in ["I2", "I3", "I4", "I5"]:
            route, cost = router.find_route("I1", dest)
            assert route is not None, f"Expected route to {dest}"
            assert route[-1] == dest

    def test_route_contains_only_valid_nodes(self, router, network):
        """All nodes in the route exist in the network."""
        route, _ = router.find_route("I1", "I5")
        assert route is not None
        for node in route:
            assert node in network.intersections

    def test_route_consecutive_edges_valid(self, router, network):
        """Consecutive node pairs in the route must be connected by an edge."""
        route, _ = router.find_route("I1", "I5")
        assert route is not None
        for i in range(len(route) - 1):
            edge = network.get_edge(route[i], route[i + 1])
            assert edge is not None, f"No edge from {route[i]} to {route[i+1]}"


class TestAStarDynamicCosts:
    def test_cost_changes_with_traffic(self, router, network):
        """Changing traffic state changes edge costs."""
        edge = network.get_edge("I1", "I2")
        assert edge is not None

        # Record cost with low congestion
        edge.congestion_ratio = 0.1
        edge.travel_time = edge.length / (edge.speed_limit * 1000 / 3600)
        edge.waiting_time = 5.0
        _, cost_low = router.find_route("I1", "I2")

        # Increase congestion
        edge.congestion_ratio = 0.9
        edge.waiting_time = 60.0
        _, cost_high = router.find_route("I1", "I2")

        assert cost_high > cost_low, "Higher congestion should increase route cost"

        # Restore
        edge.congestion_ratio = 0.0
        edge.waiting_time = 0.0

    def test_route_reconstruction_correct(self, router):
        """Route reconstruction produces a correct path from start to goal."""
        route, cost = router.find_route("I3", "I1")
        assert route is not None
        assert route[0] == "I3"
        assert route[-1] == "I1"

    def test_cost_is_positive(self, router):
        """Route cost must be positive for non-trivial routes."""
        _, cost = router.find_route("I1", "I5")
        assert cost > 0.0
