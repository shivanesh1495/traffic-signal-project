"""
Tests for road network graph and virtual sensor functions.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.simulation.network import RoadNetwork


@pytest.fixture
def network():
    return RoadNetwork()


class TestNetworkTopology:
    def test_five_intersections(self, network):
        assert len(network.intersections) == 5

    def test_intersection_ids(self, network):
        assert set(network.intersections.keys()) == {"I1", "I2", "I3", "I4", "I5"}

    def test_intersection_has_required_fields(self, network):
        for iid, node in network.intersections.items():
            assert node.id == iid
            assert isinstance(node.x, (int, float))
            assert isinstance(node.y, (int, float))
            assert isinstance(node.neighbors, list)
            assert node.signal_agent_id.startswith("TSA-")

    def test_correct_topology(self, network):
        """Verify the specified topology from the spec."""
        expected = {
            "I1": {"I2", "I4"},
            "I2": {"I1", "I3", "I4"},
            "I3": {"I2", "I5"},
            "I4": {"I1", "I2", "I5"},
            "I5": {"I3", "I4"},
        }
        for iid, expected_neighbors in expected.items():
            actual_neighbors = set(network.intersections[iid].neighbors)
            assert actual_neighbors == expected_neighbors, \
                f"{iid}: expected {expected_neighbors}, got {actual_neighbors}"

    def test_five_tsa_agents(self, network):
        agent_ids = {node.signal_agent_id for node in network.intersections.values()}
        assert agent_ids == {"TSA-1", "TSA-2", "TSA-3", "TSA-4", "TSA-5"}

    def test_edges_exist_for_all_adjacencies(self, network):
        """Every neighbour relationship must have a corresponding directed edge."""
        for iid, node in network.intersections.items():
            for neighbor in node.neighbors:
                edge = network.get_edge(iid, neighbor)
                assert edge is not None, \
                    f"Missing edge {iid} -> {neighbor}"

    def test_edge_has_length_and_speed_limit(self, network):
        for eid, edge in network.edges.items():
            assert edge.length > 0, f"Edge {eid} has zero length"
            assert edge.speed_limit > 0, f"Edge {eid} has zero speed limit"


class TestEdgeCosts:
    def test_edge_cost_non_negative(self, network):
        cost = network.edge_cost("I1", "I2")
        assert cost >= 0.0

    def test_edge_cost_between_0_and_1_for_free_flow(self, network):
        """Under free-flow conditions, edge cost equals w_t * base_cost."""
        edge = network.get_edge("I1", "I2")
        edge.congestion_ratio = 0.0
        edge.waiting_time = 0.0
        edge.travel_time = network._free_flow_time(edge)
        cost = network.edge_cost("I1", "I2")
        # At free-flow: congestion_factor=1.0, norm_travel = base_cost (0.34 for I1->I2)
        # cost = w_t * base_cost + 0 + 0 = 0.50 * 0.34 = 0.17
        w_t = network.cost_weights.get("travel_time_weight", 0.50)
        expected = w_t * edge.base_cost
        assert abs(cost - expected) < 0.01

    def test_edge_cost_increases_with_congestion(self, network):
        edge = network.get_edge("I2", "I3")
        edge.congestion_ratio = 0.0
        cost_low = network.edge_cost("I2", "I3")
        edge.congestion_ratio = 1.0
        cost_high = network.edge_cost("I2", "I3")
        assert cost_high > cost_low

    def test_nonexistent_edge_cost_is_infinity(self, network):
        cost = network.edge_cost("I1", "I3")  # no direct edge
        assert cost == float("inf")

    def test_route_cost_is_sum_of_edges(self, network):
        route = ["I1", "I2", "I3"]
        expected = network.edge_cost("I1", "I2") + network.edge_cost("I2", "I3")
        actual = network.route_cost(route)
        assert abs(actual - expected) < 1e-9

    def test_free_flow_time_correct(self, network):
        """Free-flow time = length / (speed_limit km/h → m/s)."""
        edge = network.get_edge("I1", "I2")
        expected = edge.length / (edge.speed_limit * 1000 / 3600)
        actual = network.free_flow_time("I1", "I2")
        assert abs(actual - expected) < 0.001

    def test_euclidean_distance(self, network):
        import math
        a = network.intersections["I1"]
        b = network.intersections["I2"]
        expected = math.hypot(b.x - a.x, b.y - a.y)
        actual = network.euclidean_distance("I1", "I2")
        assert abs(actual - expected) < 0.001
