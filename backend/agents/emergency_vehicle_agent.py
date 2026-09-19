"""
Emergency Vehicle Agent.

Responsibilities:
- Knows its own current simulated position (virtual GPS).
- Holds the destination from the scenario configuration.
- Uses the static road-network graph for connectivity.
- Reads dynamic traffic state from virtual sensor functions.
- Runs A* to select the minimum-cost route.
- Calculates per-intersection ETA.
- Sends EMERGENCY_PRIORITY to the first relevant TSA.
- Monitors progress and triggers route replanning when needed.
- Sends EMERGENCY_PASSED when it clears each intersection.
- Moves through the simulation at emergency speed.

The Emergency Vehicle Agent does NOT:
- Obtain the road map from Traffic Signal Agents.
- Directly control any traffic signal.
- Use physical sensors or GPS.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.algorithms.astar import AStarRouter
from backend.communication.message_bus import MessageBus
from backend.communication.schemas import (
    AgentMessage,
    EmergencyPassedPayload,
    EmergencyPriorityPayload,
    EmergencyPriority,
    EmergencyVehicleModel,
    MessageType,
    VehicleType,
)
from backend.simulation.network import RoadNetwork

logger = logging.getLogger(__name__)

# Rebuild route if remaining cost changes by this fraction
REPLAN_THRESHOLD_DEFAULT = 0.20

# Minimum seconds between replan checks
REPLAN_CHECK_INTERVAL = 5


class EmergencyVehicleAgent:
    """
    Emergency Vehicle Agent.

    Parameters
    ----------
    model            : EmergencyVehicleModel (the mutable simulation state).
    network          : Static road-network graph.
    message_bus      : Shared message bus for agent communication.
    traffic_manager  : Provides dynamic traffic sensor functions.
    replan_threshold : Fractional cost change that triggers replanning.
    """

    def __init__(
        self,
        model: EmergencyVehicleModel,
        network: RoadNetwork,
        message_bus: MessageBus,
        traffic_manager,
        replan_threshold: float = REPLAN_THRESHOLD_DEFAULT,
    ) -> None:
        self._model = model
        self._network = network
        self._bus = message_bus
        self._traffic = traffic_manager
        self._replan_threshold = replan_threshold

        self._router = AStarRouter(
            network,
            max_emergency_speed_kmh=float(
                network.sim_config.get("emergency_speed_kmh", 60)
            ),
        )
        self._tick_seconds: float = float(network.sim_config.get("tick_seconds", 1))
        self._emergency_speed: float = float(
            network.sim_config.get("emergency_speed_kmh", 60)
        )
        self._model.speed = self._emergency_speed

        # Track which intersections have already been passed
        self._passed_intersections: set = set()
        # Route cost at dispatch (for replan comparison)
        self._initial_route_cost: float = 0.0
        self._last_replan_check: float = 0.0
        # Flag: has the initial priority been sent?
        self._priority_sent: bool = False
        # Flag: send PASSED for start node after first priority message
        self._send_start_passed_on_first_tick: bool = False
        # Pending start-node PASSED to send one tick after PRIORITY
        self._start_passed_pending: Optional[str] = None

    # ------------------------------------------------------------------
    # Initialise / Plan
    # ------------------------------------------------------------------

    def plan_route(self, current_time: float) -> bool:
        """
        Run A* and initialise the emergency vehicle route.

        Returns True if a valid route was found.
        """
        start = self._model.current_node
        goal = self._model.destination

        if not start or not goal:
            logger.error("[EVA %s] No start or goal set", self._model.id)
            return False

        route, cost = self._router.find_route(start, goal)
        if route is None:
            logger.error(
                "[EVA %s] A* could not find route from %s to %s",
                self._model.id,
                start,
                goal,
            )
            return False

        self._model.route = route
        self._model.route_index = 0
        self._model.route_cost = cost
        self._initial_route_cost = cost
        self._passed_intersections.clear()
        self._priority_sent = False

        self._calculate_eta(current_time)
        logger.info(
            "[EVA %s] Route planned: %s  cost=%.4f",
            self._model.id,
            " -> ".join(route),
            cost,
        )

        # Schedule PASSED for the start node. The EV is already at route[0]
        # and will depart on tick 1, so the start signal must recover promptly.
        # We do NOT send it here (the PRIORITY hasn't been sent yet), but we
        # mark it for immediate dispatch on the first tick via a flag.
        self._send_start_passed_on_first_tick = True
        return True

    # ------------------------------------------------------------------
    # ETA calculation
    # ------------------------------------------------------------------

    def _calculate_eta(self, current_time: float) -> None:
        """
        Calculate ETA for each upcoming intersection in the route.

        ETA_segment = current_time + estimated_remaining_segment_time
        Segment time uses road length, emergency speed, and congestion delay.
        """
        route = self._model.route
        if not route:
            return

        eta_map: Dict[str, float] = {}
        cumulative_time = 0.0

        # Account for partial progress on current edge
        current_idx = self._model.route_index
        if self._model.current_edge:
            edge = self._network.edges.get(self._model.current_edge)
            if edge:
                remaining_fraction = 1.0 - self._model.position
                speed_ms = self._emergency_speed * 1000.0 / 3600.0
                base_time = (edge.length * remaining_fraction) / speed_ms
                # Congestion delay factor
                delay_factor = 1.0 + edge.congestion_ratio * 0.5
                cumulative_time += base_time * delay_factor

        for i in range(current_idx, len(route)):
            node = route[i]
            if i == 0:
                eta_map[node] = current_time
                continue

            prev_node = route[i - 1]
            edge = self._network.get_edge(prev_node, node)
            if edge:
                speed_ms = self._emergency_speed * 1000.0 / 3600.0
                base_time = edge.length / speed_ms
                delay_factor = 1.0 + edge.congestion_ratio * 0.5
                cumulative_time += base_time * delay_factor

            eta_map[node] = current_time + cumulative_time

        self._model.eta_map = eta_map

    # ------------------------------------------------------------------
    # Main tick
    # ------------------------------------------------------------------

    def tick(self, current_time: float) -> None:
        """Advance emergency vehicle by one simulation tick."""
        if not self._model.active:
            return

        dt = self._tick_seconds

        # Send initial priority if not yet sent
        if not self._priority_sent and self._model.route:
            self._send_emergency_priority(current_time)
            self._priority_sent = True
            # Immediately after sending priority, schedule PASSED for the
            # start intersection (the EV is already there and will depart now).
            if self._send_start_passed_on_first_tick and self._model.route:
                start_node = self._model.route[0]
                if start_node not in self._passed_intersections:
                    # Small delay: send on next tick so PRIORITY is flushed first
                    self._start_passed_pending = start_node
                self._send_start_passed_on_first_tick = False

        # Send pending PASSED for start node (one tick after PRIORITY)
        if getattr(self, '_start_passed_pending', None):
            self._on_intersection_reached(self._start_passed_pending, current_time)
            self._start_passed_pending = None

        # Move vehicle
        self._move(dt, current_time)

        # Check for replanning periodically
        if current_time - self._last_replan_check >= REPLAN_CHECK_INTERVAL:
            self._last_replan_check = current_time
            self._check_replan(current_time)

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def _move(self, dt: float, current_time: float) -> None:
        """Move the emergency vehicle along its route."""
        m = self._model
        route = m.route

        if m.route_index >= len(route) - 1:
            if not m.arrival_time:
                m.arrival_time = current_time
                m.active = False
                # Notify all remaining route intersections that EV has passed/arrived.
                # This ensures signals not yet cleared receive EMERGENCY_PASSED.
                for remaining_iid in route:
                    if remaining_iid not in self._passed_intersections:
                        self._on_intersection_reached(remaining_iid, current_time)
                logger.info(
                    "[EVA %s] Reached destination %s at t=%.1fs",
                    m.id,
                    m.destination,
                    current_time,
                )
            return

        current_node = route[m.route_index]
        next_node = route[m.route_index + 1]
        edge = self._network.get_edge(current_node, next_node)
        if edge is None:
            logger.warning("[EVA %s] Edge missing: %s -> %s", m.id, current_node, next_node)
            return

        m.current_edge = edge.id
        m.current_node = current_node

        # On the very first movement tick from the start node, immediately
        # send EMERGENCY_PASSED for the start intersection so its signal
        # begins recovery as soon as the EV departs.
        if m.position == 0.0 and current_node not in self._passed_intersections:
            self._on_intersection_reached(current_node, current_time)

        speed_ms = self._emergency_speed * 1000.0 / 3600.0
        fraction_per_tick = (speed_ms * dt) / edge.length
        m.position += fraction_per_tick

        if m.position >= 1.0:
            # Arrived at next intersection
            m.position = 0.0
            m.current_edge = None
            m.current_node = next_node
            m.route_index += 1
            self._on_intersection_reached(next_node, current_time)

    def _on_intersection_reached(self, intersection_id: str, current_time: float) -> None:
        """Called when emergency vehicle arrives at an intersection."""
        if intersection_id in self._passed_intersections:
            return
        self._passed_intersections.add(intersection_id)

        # Notify the TSA that the emergency vehicle has passed
        agent_id = self._intersection_to_agent(intersection_id)
        if agent_id:
            msg = AgentMessage(
                type=MessageType.EMERGENCY_PASSED,
                sender_id=self._model.id,
                receiver_id=agent_id,
                timestamp=current_time,
                payload=EmergencyPassedPayload(
                    emergency_id=self._model.id,
                    intersection_id=intersection_id,
                ).model_dump(),
            )
            self._bus.post(msg)
            logger.info(
                "[EVA %s] EMERGENCY_PASSED -> %s at t=%.1f",
                self._model.id,
                agent_id,
                current_time,
            )

        # Recalculate ETA for remaining intersections
        self._calculate_eta(current_time)

    # ------------------------------------------------------------------
    # Priority messaging
    # ------------------------------------------------------------------

    def _send_emergency_priority(self, current_time: float) -> None:
        """
        Send EMERGENCY_PRIORITY to the first TSA on the route.
        That TSA will forward to the next relevant TSA (chain communication).
        """
        route = self._model.route
        if not route:
            return

        # Find the first intersection on the route that has a TSA
        first_intersection = route[0] if len(route) > 0 else None
        if first_intersection is None:
            return

        first_agent = self._intersection_to_agent(first_intersection)
        if first_agent is None:
            return

        priority_payload = EmergencyPriorityPayload(
            emergency_id=self._model.id,
            route=route,
            priority=EmergencyPriority.HIGH,
            eta_to_intersection=dict(self._model.eta_map),
            vehicle_type=self._model.type,
        )

        msg = AgentMessage(
            type=MessageType.EMERGENCY_PRIORITY,
            sender_id=self._model.id,
            receiver_id=first_agent,
            timestamp=current_time,
            payload=priority_payload.model_dump(),
        )
        self._bus.post(msg)
        logger.info(
            "[EVA %s] EMERGENCY_PRIORITY sent to %s, route=%s",
            self._model.id,
            first_agent,
            " -> ".join(route),
        )

    def send_updated_priority(self, current_time: float) -> None:
        """Resend updated priority after replanning."""
        self._priority_sent = False
        self._send_emergency_priority(current_time)
        self._priority_sent = True

    # ------------------------------------------------------------------
    # Route replanning
    # ------------------------------------------------------------------

    def _check_replan(self, current_time: float) -> None:
        """
        Re-run A* if route cost has changed significantly.

        Triggers if:
        - Current remaining route cost changed by > replan_threshold, OR
        - A route edge became unavailable (infinite cost).
        """
        m = self._model
        if m.route_index >= len(m.route) - 1:
            return

        remaining_route = m.route[m.route_index:]

        # Check for unavailable edge
        for i in range(len(remaining_route) - 1):
            c = self._network.edge_cost(remaining_route[i], remaining_route[i + 1])
            if c == float("inf"):
                logger.warning(
                    "[EVA %s] Edge %s->%s unavailable – replanning",
                    m.id,
                    remaining_route[i],
                    remaining_route[i + 1],
                )
                self._replan(current_time)
                return

        # Check for significant cost change
        current_remaining_cost = self._network.route_cost(remaining_route)
        if self._initial_route_cost > 0:
            # Compare to proportionate original cost
            original_remaining = self._network.route_cost(m.route)
            if original_remaining > 0:
                change = abs(current_remaining_cost - original_remaining) / original_remaining
                if change >= self._replan_threshold:
                    logger.info(
                        "[EVA %s] Cost change %.1f%% >= %.1f%% threshold – replanning",
                        m.id,
                        change * 100,
                        self._replan_threshold * 100,
                    )
                    self._replan(current_time)

    def _replan(self, current_time: float) -> None:
        """Replan from current position."""
        m = self._model
        start = m.current_node or (m.route[m.route_index] if m.route else None)
        if not start:
            return

        old_route = list(m.route)
        route, cost = self._router.find_route(start, m.destination)
        if route and route != old_route:
            m.route = route
            m.route_index = 0
            m.route_cost = cost
            self._calculate_eta(current_time)
            self.send_updated_priority(current_time)
            logger.info(
                "[EVA %s] Route replanned: %s  cost=%.4f",
                m.id,
                " -> ".join(route),
                cost,
            )
        else:
            logger.debug("[EVA %s] Replan did not change route", m.id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _intersection_to_agent(intersection_id: str) -> Optional[str]:
        mapping = {"I1": "TSA-1", "I2": "TSA-2", "I3": "TSA-3", "I4": "TSA-4", "I5": "TSA-5"}
        return mapping.get(intersection_id)

    # ------------------------------------------------------------------
    # Virtual sensor functions
    # ------------------------------------------------------------------

    def get_location(self) -> Optional[str]:
        """Virtual GPS: return current intersection or edge."""
        return self._model.current_node

    def get_speed(self) -> float:
        """Virtual speed sensor."""
        return self._model.speed

    def get_eta(self, intersection_id: str) -> float:
        """Virtual ETA calculation."""
        return self._model.eta_map.get(intersection_id, float("inf"))

    @property
    def model(self) -> EmergencyVehicleModel:
        return self._model

    def reset(self) -> None:
        self._passed_intersections.clear()
        self._priority_sent = False
        self._send_start_passed_on_first_tick = False
        self._start_passed_pending = None
        self._last_replan_check = 0.0
        self._initial_route_cost = 0.0
