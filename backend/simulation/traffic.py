"""
Virtual traffic generator and vehicle movement model.

Responsibilities:
- Spawn ordinary Vehicle Agents with random origins/destinations (seeded).
- Move vehicles along their routes tick-by-tick.
- Maintain per-edge traffic state (vehicle_count, queue_length,
  average_speed, congestion_ratio, travel_time, waiting_time).
- Expose virtual sensor functions used by Traffic Signal Agents and A*.

All values are derived from simulated vehicle positions and physics –
no external sensors or hardware are used.
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional, Tuple

from backend.communication.schemas import (
    SignalState,
    VehicleModel,
    VehicleType,
    RoadEdgeModel,
)

logger = logging.getLogger(__name__)

# Maximum capacity used for congestion normalisation (vehicles per edge).
# Lower value = congestion ratio rises faster with fewer vehicles,
# making A* edge costs more sensitive to actual traffic.
EDGE_CAPACITY = 8

# Speed at which a vehicle is considered "stopped/queued" (km/h)
STOPPED_THRESHOLD = 5.0


class TrafficManager:
    """
    Virtual traffic environment.

    Manages ordinary vehicles and their movement through the network.
    Computes per-edge traffic metrics that feed the signal agents and A*.
    """

    def __init__(
        self,
        network,
        sim_config: dict,
        random_seed: int = -1,
    ) -> None:
        self._network = network
        self._cfg = sim_config
        # seed == -1 means "use a different seed every run" so traffic
        # distribution varies and A* picks different routes based on live costs.
        effective_seed = None if random_seed == -1 else random_seed
        self._rng = random.Random(effective_seed)

        self._vehicles: Dict[str, VehicleModel] = {}
        self._vehicle_counter = 0
        self._spawn_accumulator = 0.0
        self._tick_seconds: float = float(sim_config.get("tick_seconds", 1))
        self._spawn_rate: float = float(sim_config.get("spawn_rate_per_second", 0.15))
        self._min_speed: float = float(sim_config.get("min_speed_kmh", 8))
        self._max_speed: float = float(sim_config.get("max_speed_kmh", 42))

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialise(self, initial_count: int, congestion_hotspot: Optional[List[str]] = None) -> None:
        """
        Spawn the initial vehicle population.

        congestion_hotspot: list of intersection IDs that should receive
        a disproportionate share of initial traffic. When provided, roughly
        60% of vehicles are routed through these intersections, causing
        measurable congestion on adjacent edges that A* must route around.
        """
        self._vehicles.clear()
        self._vehicle_counter = 0
        self._spawn_accumulator = 0.0
        self._congestion_hotspot = congestion_hotspot or []

        intersection_ids = list(self._network.intersections.keys())

        if self._congestion_hotspot:
            # Phase 1: spawn ~60% of vehicles with hotspot origins/destinations
            hotspot_count = int(initial_count * 0.60)
            for _ in range(hotspot_count):
                self._spawn_vehicle_near_hotspot(self._congestion_hotspot, intersection_ids)
            # Phase 2: spawn remaining vehicles fully randomly
            for _ in range(initial_count - hotspot_count):
                self._spawn_vehicle(intersection_ids)
        else:
            for _ in range(initial_count):
                self._spawn_vehicle(intersection_ids)

        logger.info(
            "Spawned %d initial vehicles (hotspot=%s)",
            len(self._vehicles),
            self._congestion_hotspot or 'none',
        )

    def _spawn_vehicle(self, intersection_ids: Optional[List[str]] = None) -> Optional[VehicleModel]:
        if intersection_ids is None:
            intersection_ids = list(self._network.intersections.keys())
        if len(intersection_ids) < 2:
            return None

        # Weighted origin selection: bias some vehicles toward high-traffic
        # intersections so congestion naturally clusters on different edges
        # each run due to the random seed, making A* route decisions vary.
        weights = [1 + self._rng.random() * 3 for _ in intersection_ids]
        origin = self._rng.choices(intersection_ids, weights=weights, k=1)[0]
        dest_candidates = [x for x in intersection_ids if x != origin]
        if not dest_candidates:
            return None
        dest_weights = [1 + self._rng.random() * 3 for _ in dest_candidates]
        destination = self._rng.choices(dest_candidates, weights=dest_weights, k=1)[0]

        # Simple route: BFS to find a path (not A* – vehicles use simple routing)
        route = self._bfs_route(origin, destination)
        if not route or len(route) < 2:
            return None

        speed = self._rng.uniform(self._min_speed, self._max_speed)
        vid = f"V{self._vehicle_counter:04d}"
        self._vehicle_counter += 1

        vehicle = VehicleModel(
            id=vid,
            type=VehicleType.NORMAL,
            current_node=origin,
            current_edge=None,
            position=0.0,
            speed=speed,
            destination=destination,
            route=route,
            route_index=0,
        )
        self._vehicles[vid] = vehicle
        return vehicle

    def _spawn_vehicle_near_hotspot(
        self,
        hotspot: List[str],
        all_ids: List[str],
    ) -> Optional[VehicleModel]:
        """
        Spawn a vehicle that originates from or travels through a hotspot
        intersection, ensuring those edges build real measurable congestion.
        """
        # Pick a hotspot node as origin or destination (50/50 chance)
        hotspot_node = self._rng.choice(hotspot)
        other_nodes = [x for x in all_ids if x != hotspot_node]
        if not other_nodes:
            return self._spawn_vehicle(all_ids)

        if self._rng.random() < 0.5:
            origin = hotspot_node
            destination = self._rng.choice(other_nodes)
        else:
            origin = self._rng.choice(other_nodes)
            destination = hotspot_node

        route = self._bfs_route(origin, destination)
        if not route or len(route) < 2:
            return self._spawn_vehicle(all_ids)

        # Randomise position along the route so vehicles spread across edges
        # rather than all starting at the origin node
        route_index = self._rng.randint(0, max(0, len(route) - 2))
        current_node = route[route_index]
        next_node = route[route_index + 1] if route_index + 1 < len(route) else None
        edge_id = None
        position = 0.0

        if next_node:
            edge = self._network.get_edge(current_node, next_node)
            if edge:
                edge_id = edge.id
                position = self._rng.uniform(0.05, 0.90)

        speed = self._rng.uniform(self._min_speed, self._max_speed)
        vid = f"V{self._vehicle_counter:04d}"
        self._vehicle_counter += 1

        vehicle = VehicleModel(
            id=vid,
            type=VehicleType.NORMAL,
            current_node=current_node,
            current_edge=edge_id,
            position=position,
            speed=speed,
            destination=destination,
            route=route,
            route_index=route_index,
        )
        self._vehicles[vid] = vehicle
        return vehicle

    def _bfs_route(self, start: str, goal: str) -> Optional[List[str]]:
        """BFS shortest-hop route for ordinary vehicles."""
        from collections import deque
        queue: deque = deque([[start]])
        visited = {start}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == goal:
                return path
            for neighbor, _ in self._network.neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    # ------------------------------------------------------------------
    # Per-tick update
    # ------------------------------------------------------------------

    def tick(self, current_time: float, signals: Dict[str, "SignalStateModel"]) -> None:
        """Advance all vehicles by one simulation tick."""
        # Spawn new vehicles according to spawn rate
        self._spawn_accumulator += self._spawn_rate * self._tick_seconds
        while self._spawn_accumulator >= 1.0:
            self._spawn_accumulator -= 1.0
            self._spawn_vehicle()

        dt = self._tick_seconds
        completed: List[str] = []

        for vid, v in self._vehicles.items():
            if v.reached_destination:
                completed.append(vid)
                continue
            self._move_vehicle(v, dt, signals, current_time)

        # Remove vehicles that have just reached destination in this tick
        # (we keep them one extra tick so metrics capture the arrival)
        for vid in completed:
            del self._vehicles[vid]

        # Update edge traffic state from vehicle positions
        self._update_edge_states()

    def _move_vehicle(
        self,
        v: VehicleModel,
        dt: float,
        signals: Dict[str, "SignalStateModel"],
        current_time: float,
    ) -> None:
        """Move a single vehicle along its route."""
        if v.route_index >= len(v.route) - 1:
            v.reached_destination = True
            return

        current_node = v.route[v.route_index]
        next_node = v.route[v.route_index + 1]
        edge = self._network.get_edge(current_node, next_node)
        if edge is None:
            v.reached_destination = True
            return

        v.current_edge = edge.id
        v.current_node = current_node

        # Check if signal at next_node allows passage
        signal = signals.get(next_node)
        approaching_signal = v.position > 0.7  # within last 30% of edge

        can_proceed = True
        if approaching_signal and signal is not None:
            state = signal.state
            if state in (SignalState.NORMAL_RED, SignalState.NORMAL_YELLOW, SignalState.EMERGENCY_PREPARE):
                can_proceed = False

        if not can_proceed:
            v.waiting = True
            v.waiting_time_accumulated += dt
            return

        v.waiting = False
        # Move vehicle along edge
        speed_ms = v.speed * 1000.0 / 3600.0  # km/h -> m/s
        distance_moved = speed_ms * dt
        edge_fraction_moved = distance_moved / edge.length if edge.length > 0 else 1.0
        v.position += edge_fraction_moved

        if v.position >= 1.0:
            # Arrived at next intersection
            v.route_index += 1
            v.current_node = next_node
            v.position = 0.0
            v.current_edge = None
            if v.route_index >= len(v.route) - 1:
                v.reached_destination = True

    # ------------------------------------------------------------------
    # Edge state update
    # ------------------------------------------------------------------

    def _update_edge_states(self) -> None:
        """Recompute per-edge traffic metrics from vehicle positions."""
        # Reset all edges
        for edge in self._network.edges.values():
            edge.vehicle_count = 0
            edge.queue_length = 0
            edge.average_speed = edge.speed_limit
            edge.congestion_ratio = 0.0

        # Count vehicles on each edge
        edge_vehicles: Dict[str, List[VehicleModel]] = {eid: [] for eid in self._network.edges}

        for v in self._vehicles.values():
            if v.current_edge and v.current_edge in edge_vehicles:
                edge_vehicles[v.current_edge].append(v)

        for edge_id, veh_list in edge_vehicles.items():
            edge = self._network.edges[edge_id]
            count = len(veh_list)
            edge.vehicle_count = count

            if count > 0:
                speeds = [v.speed for v in veh_list]
                edge.average_speed = sum(speeds) / len(speeds)
                queued = sum(1 for v in veh_list if v.waiting or v.speed <= STOPPED_THRESHOLD)
                edge.queue_length = queued
            else:
                edge.average_speed = edge.speed_limit
                edge.queue_length = 0

            # Congestion ratio: normalised vehicle density
            edge.congestion_ratio = min(1.0, count / EDGE_CAPACITY)

            # Travel time: length / current average speed (with congestion delay)
            if edge.average_speed > 0:
                speed_ms = edge.average_speed * 1000.0 / 3600.0
                edge.travel_time = edge.length / speed_ms
            else:
                edge.travel_time = edge.length / (10 * 1000.0 / 3600.0)  # minimum 10 km/h

            # Waiting time contribution from queued vehicles.
            # Multiply by 8 (was 5) so waiting time contributes more
            # meaningfully to the A* edge cost formula.
            edge.waiting_time = min(120.0, edge.queue_length * 8.0)

    # ------------------------------------------------------------------
    # Virtual sensor functions
    # ------------------------------------------------------------------

    def get_vehicle_count(self, intersection_id: str) -> int:
        """Count simulated vehicles on edges adjacent to intersection."""
        count = 0
        for v in self._vehicles.values():
            if v.current_node == intersection_id:
                count += 1
            elif v.current_edge:
                edge = self._network.edges.get(v.current_edge)
                if edge and (edge.from_node == intersection_id or edge.to_node == intersection_id):
                    count += 1
        return count

    def get_queue_length(self, intersection_id: str) -> int:
        """Count stopped/queued vehicles at intersection."""
        count = 0
        for v in self._vehicles.values():
            if v.current_edge:
                edge = self._network.edges.get(v.current_edge)
                if edge and edge.to_node == intersection_id:
                    if v.waiting or v.speed <= STOPPED_THRESHOLD:
                        count += 1
        return count

    def get_average_speed(self, intersection_id: str) -> float:
        """Average speed of vehicles near intersection (km/h)."""
        speeds = []
        for v in self._vehicles.values():
            if v.current_node == intersection_id or (
                v.current_edge
                and self._network.edges.get(v.current_edge)
                and self._network.edges[v.current_edge].to_node == intersection_id
            ):
                speeds.append(v.speed)
        return sum(speeds) / len(speeds) if speeds else 0.0

    def get_congestion_ratio(self, intersection_id: str) -> float:
        """Normalised congestion ratio for edges approaching intersection."""
        ratios = []
        for eid, edge in self._network.edges.items():
            if edge.to_node == intersection_id:
                ratios.append(edge.congestion_ratio)
        return sum(ratios) / len(ratios) if ratios else 0.0

    def get_traffic_state(self, road_id: str) -> Optional[RoadEdgeModel]:
        """Return current traffic metrics for a road edge."""
        return self._network.edges.get(road_id)

    def get_vehicle_state(self, vehicle_id: str) -> Optional[VehicleModel]:
        return self._vehicles.get(vehicle_id)

    def get_completed_count(self) -> int:
        """Number of vehicles that completed their journeys (approximated)."""
        return self._vehicle_counter - len(self._vehicles)

    def get_total_waiting(self) -> float:
        """Total accumulated waiting seconds across all vehicles."""
        return sum(v.waiting_time_accumulated for v in self._vehicles.values())

    def get_all_vehicles(self) -> List[VehicleModel]:
        return list(self._vehicles.values())

    def reset(self) -> None:
        self._vehicles.clear()
        self._vehicle_counter = 0
        self._spawn_accumulator = 0.0
        self._congestion_hotspot: List[str] = []
