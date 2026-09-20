"""
Road network graph.

Loads the static topology from network.json and provides connectivity,
edge lookups, and geometric distance calculations used by A* heuristic.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.communication.schemas import IntersectionModel, RoadEdgeModel

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "network.json"


class RoadNetwork:
    """
    Immutable road network graph.

    - Nodes are intersections.
    - Directed edges represent roads between intersections.
    - Edge dynamic state (vehicle_count, queue_length, etc.) is stored
      inside RoadEdgeModel and updated by the simulation engine each tick.
    """

    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        raw = json.loads(config_path.read_text(encoding="utf-8"))

        self.intersections: Dict[str, IntersectionModel] = {
            d["id"]: IntersectionModel(**d) for d in raw["intersections"]
        }

        self.edges: Dict[str, RoadEdgeModel] = {}
        # adjacency: node -> list of (neighbor_id, edge_id)
        self._adj: Dict[str, List[Tuple[str, str]]] = {i: [] for i in self.intersections}

        for d in raw["edges"]:
            edge = RoadEdgeModel(**d)
            self.edges[edge.id] = edge
            self._adj[edge.from_node].append((edge.to_node, edge.id))

        # Precompute free-flow travel times (seconds) for normalisation
        for edge in self.edges.values():
            edge.travel_time = self._free_flow_time(edge)
            edge.average_speed = edge.speed_limit

        self.sim_config: dict = raw.get("simulation", {})
        self.cost_weights: dict = raw.get("cost_weights", {
            "travel_time_weight": 0.50,
            "congestion_weight": 0.30,
            "waiting_time_weight": 0.20,
        })
        self.scenarios: dict = raw.get("scenarios", {})

        logger.info(
            "Network loaded: %d intersections, %d edges",
            len(self.intersections),
            len(self.edges),
        )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_edge(self, from_node: str, to_node: str) -> Optional[RoadEdgeModel]:
        """Return the directed edge from from_node to to_node, or None."""
        for neighbor, edge_id in self._adj.get(from_node, []):
            if neighbor == to_node:
                return self.edges[edge_id]
        return None

    def get_edge_by_id(self, edge_id: str) -> Optional[RoadEdgeModel]:
        return self.edges.get(edge_id)

    def neighbors(self, node_id: str) -> List[Tuple[str, str]]:
        """Return list of (neighbor_intersection_id, edge_id) for node."""
        return self._adj.get(node_id, [])

    def euclidean_distance(self, node_a: str, node_b: str) -> float:
        """Straight-line distance between two intersections (metres)."""
        a = self.intersections[node_a]
        b = self.intersections[node_b]
        return math.hypot(b.x - a.x, b.y - a.y)

    # ------------------------------------------------------------------
    # Free-flow helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _free_flow_time(edge: RoadEdgeModel) -> float:
        """Minimum traversal time in seconds at speed limit."""
        # speed_limit in km/h → convert to m/s
        speed_ms = edge.speed_limit * 1000.0 / 3600.0
        return edge.length / speed_ms

    def free_flow_time(self, from_node: str, to_node: str) -> float:
        edge = self.get_edge(from_node, to_node)
        if edge is None:
            return float("inf")
        return self._free_flow_time(edge)

    # ------------------------------------------------------------------
    # Dynamic edge cost (used by A*)
    # ------------------------------------------------------------------

    def edge_cost(self, from_node: str, to_node: str) -> float:
        """
        Compute dynamic edge cost:

          edge_cost = w_t * norm_travel_time
                    + w_c * congestion_ratio
                    + w_w * norm_waiting_time

        norm_travel_time:
          At free-flow = edge.base_cost (configured per edge, default 0.5).
          Under congestion it scales up proportionally:
            norm_travel_time = base_cost * (travel_time / free_flow_time)
          This preserves the formula structure while allowing per-edge tuning.

        norm_waiting_time = waiting_time / MAX_WAITING_TIME  (clamped 0-1)

        Weights come from network.json cost_weights (configurable).
        """
        edge = self.get_edge(from_node, to_node)
        if edge is None:
            return float("inf")

        MAX_WAITING_TIME: float = float(
            self.sim_config.get("max_waiting_time", 120)
        )

        ff = self._free_flow_time(edge)
        # Congestion multiplier: 1.0 at free-flow, higher under congestion
        congestion_factor = (edge.travel_time / ff) if ff > 0 else 1.0
        # Normalised travel-time component: base_cost scales with actual congestion
        norm_travel = min(1.0, edge.base_cost * max(1.0, congestion_factor))
        norm_waiting = min(1.0, edge.waiting_time / MAX_WAITING_TIME) if MAX_WAITING_TIME > 0 else 0.0
        congestion = min(1.0, max(0.0, edge.congestion_ratio))

        w_t = self.cost_weights.get("travel_time_weight", 0.50)
        w_c = self.cost_weights.get("congestion_weight", 0.30)
        w_w = self.cost_weights.get("waiting_time_weight", 0.20)

        return w_t * norm_travel + w_c * congestion + w_w * norm_waiting

    def route_cost(self, route: List[str]) -> float:
        """Total edge cost along a route (list of intersection IDs)."""
        total = 0.0
        for i in range(len(route) - 1):
            total += self.edge_cost(route[i], route[i + 1])
        return total
