"""
A* Route Planning Algorithm – Emergency Vehicle Agent only.

This module implements a custom A* search over the road network graph.

f(n) = g(n) + h(n)
  g(n) = accumulated dynamic edge cost from start to n
  h(n) = admissible heuristic: straight-line distance / max_emergency_speed
  f(n) = estimated total route cost

Edge costs are dynamic – they reflect current traffic state every time
the algorithm is called.

A* does NOT control traffic signals.  It only selects the route.
The Emergency Vehicle Agent then sends priority messages to signal agents.

Note on optimality: the heuristic divides geometric distance by the
maximum emergency speed, giving an estimate in normalised cost units.
Since edge costs are weighted sums of normalised components (all ≥ 0),
and the travel-time component alone is ≥ (distance / max_speed) / free_flow_time,
the heuristic is admissible for the travel-time component.  The full
multi-component cost may not be strictly optimal if congestion and waiting
push the actual cost above travel-time alone; therefore A* is documented
here as the selected informed search strategy rather than claiming formal
optimality.
"""
from __future__ import annotations

import heapq
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Scale factor to make the heuristic commensurate with the edge cost formula.
# The travel-time weight in the cost formula is 0.50, so the heuristic
# should be scaled similarly to remain admissible.
HEURISTIC_SCALE = 0.50


@dataclass(order=True)
class _Node:
    f: float
    g: float = field(compare=False)
    node_id: str = field(compare=False)
    parent: Optional["_Node"] = field(compare=False, default=None)


class AStarRouter:
    """
    A* search for the road network graph.

    Parameters
    ----------
    network : RoadNetwork
        The road network providing edge costs and geometry.
    max_emergency_speed_kmh : float
        Maximum allowed emergency vehicle speed used in the heuristic.
    """

    def __init__(self, network, max_emergency_speed_kmh: float = 60.0) -> None:
        self._network = network
        # Convert km/h to m/s for distance/time heuristic
        self._max_speed_ms = max_emergency_speed_kmh * 1000.0 / 3600.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_route(
        self,
        start: str,
        goal: str,
    ) -> Tuple[Optional[List[str]], float]:
        """
        Find the minimum-cost route from start to goal.

        Returns
        -------
        (route, cost) where route is a list of intersection IDs from
        start to goal (inclusive), or (None, inf) if unreachable.
        """
        if start == goal:
            return [start], 0.0

        if start not in self._network.intersections:
            logger.error("Start node '%s' not in network", start)
            return None, float("inf")

        if goal not in self._network.intersections:
            logger.error("Goal node '%s' not in network", goal)
            return None, float("inf")

        open_set: List[_Node] = []
        # best g-cost found for each node
        g_costs: Dict[str, float] = {start: 0.0}
        # For reconstruction: parent node_id
        came_from: Dict[str, Optional[str]] = {start: None}

        start_h = self._heuristic(start, goal)
        heapq.heappush(open_set, _Node(f=start_h, g=0.0, node_id=start))

        explored: set = set()

        while open_set:
            current = heapq.heappop(open_set)

            if current.node_id in explored:
                continue
            explored.add(current.node_id)

            if current.node_id == goal:
                route = self._reconstruct(came_from, goal)
                cost = g_costs[goal]
                logger.info(
                    "A* route found: %s  cost=%.4f",
                    " -> ".join(route),
                    cost,
                )
                return route, cost

            for neighbor_id, _ in self._network.neighbors(current.node_id):
                if neighbor_id in explored:
                    continue

                step_cost = self._network.edge_cost(current.node_id, neighbor_id)
                if step_cost == float("inf"):
                    continue  # edge unavailable

                tentative_g = g_costs[current.node_id] + step_cost

                if neighbor_id not in g_costs or tentative_g < g_costs[neighbor_id]:
                    g_costs[neighbor_id] = tentative_g
                    came_from[neighbor_id] = current.node_id
                    h = self._heuristic(neighbor_id, goal)
                    heapq.heappush(
                        open_set,
                        _Node(f=tentative_g + h, g=tentative_g, node_id=neighbor_id),
                    )

        logger.warning("A* found no route from '%s' to '%s'", start, goal)
        return None, float("inf")

    # ------------------------------------------------------------------
    # Heuristic
    # ------------------------------------------------------------------

    def _heuristic(self, node: str, goal: str) -> float:
        """
        Admissible heuristic: straight-line distance / max_emergency_speed.

        This gives an estimated minimum travel time in seconds, scaled by
        HEURISTIC_SCALE to stay commensurate with the travel-time component
        of the edge-cost formula.
        """
        dist = self._network.euclidean_distance(node, goal)
        # Minimum time to cover this distance at max speed
        min_time_s = dist / self._max_speed_ms if self._max_speed_ms > 0 else 0.0
        # Free-flow travel time on a typical edge (approximate)
        # We use the ratio approach: h is in the same normalised unit as g
        # by dividing by a representative free-flow time constant.
        # Baseline: use 10 seconds as representative free-flow constant so the
        # heuristic stays < 1 for nearby nodes and remains admissible.
        REPRESENTATIVE_FF_TIME = 10.0
        norm_h = min_time_s / REPRESENTATIVE_FF_TIME
        return HEURISTIC_SCALE * norm_h

    # ------------------------------------------------------------------
    # Path reconstruction
    # ------------------------------------------------------------------

    @staticmethod
    def _reconstruct(came_from: Dict[str, Optional[str]], goal: str) -> List[str]:
        path = []
        current: Optional[str] = goal
        while current is not None:
            path.append(current)
            current = came_from.get(current)
        path.reverse()
        return path
