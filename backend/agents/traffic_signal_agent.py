"""
Traffic Signal Agent (TSA).

One TSA instance per intersection (TSA-1 through TSA-5).

Each TSA:
- Maintains and controls only its own traffic signal (via SignalController).
- Perceives local vehicle density, queue length, signal state, and
  neighbor messages – all from virtual simulation functions.
- Communicates directly with its configured neighboring TSAs.
- Applies rule-based local decisions for normal traffic coordination
  and emergency priority.
- MUST NOT directly control another agent's signal.

Emergency priority rules implemented:
  R1 – Emergency approaching on route → EMERGENCY_PREPARE / EMERGENCY_GREEN
  R2 – On route but ETA not imminent → prepare timing only
  R3 – Emergency passed → EMERGENCY_CLEAR → recovery
  R4 – Not on route → normal operation
  R5 – Stale / invalid message → ignore and log
"""
from __future__ import annotations

import logging
import time as walltime
from typing import Dict, Optional, Set

from backend.communication.message_bus import MessageBus
from backend.communication.schemas import (
    AgentMessage,
    AckPayload,
    EmergencyPassedPayload,
    EmergencyPriorityPayload,
    MessageType,
    RouteForwardPayload,
    SignalState,
    SignalStatusPayload,
    TrafficUpdatePayload,
)
from backend.simulation.signals import SignalController

logger = logging.getLogger(__name__)

# How close the ETA must be (seconds) before activating EMERGENCY_GREEN
ETA_IMMINENT_THRESHOLD = 10.0
# How often (ticks) to broadcast TRAFFIC_UPDATE to neighbours
TRAFFIC_UPDATE_INTERVAL = 5


class TrafficSignalAgent:
    """
    Decentralised Traffic Signal Agent.

    Parameters
    ----------
    agent_id         : Unique ID e.g. "TSA-1".
    intersection_id  : The intersection this agent controls.
    neighbor_ids     : List of neighboring TSA IDs for direct communication.
    signal_controller: The SignalController managing the physical (virtual) signal.
    message_bus      : Shared message bus.
    traffic_manager  : TrafficManager for virtual sensor reads.
    """

    def __init__(
        self,
        agent_id: str,
        intersection_id: str,
        neighbor_ids: list,
        signal_controller: SignalController,
        message_bus: MessageBus,
        traffic_manager,
    ) -> None:
        self.agent_id = agent_id
        self.intersection_id = intersection_id
        self.neighbor_ids: list = neighbor_ids
        self._signal = signal_controller
        self._bus = message_bus
        self._traffic = traffic_manager

        # Track active emergency contexts (emergency_id -> payload)
        self._active_emergencies: Dict[str, EmergencyPriorityPayload] = {}
        # Track processed message IDs to prevent duplicate actions
        self._processed_emergency_ids: Set[str] = set()
        # Tick counter for periodic broadcasts
        self._tick_count = 0
        # Last known neighbor traffic states
        self._neighbor_states: Dict[str, TrafficUpdatePayload] = {}

        # Register with the bus
        self._bus.register_handler(agent_id, self._handle_message)

    # ------------------------------------------------------------------
    # Main tick (called by simulation engine each tick)
    # ------------------------------------------------------------------

    def tick(self, current_time: float, dt: float) -> None:
        """Perform one simulation tick."""
        self._tick_count += 1

        # 1. Advance own signal state machine.
        # EMERGENCY_GREEN is normally held until EMERGENCY_PASSED is received,
        # but we still call tick() so the safety timeout counter advances.
        self._signal.tick(dt)

        # 2. Check if ETA is imminent for any active emergency and activate green
        self._check_eta_activation(current_time)

        # 3. Periodic neighbour traffic update broadcast
        if self._tick_count % TRAFFIC_UPDATE_INTERVAL == 0:
            self._broadcast_traffic_update(current_time)

    # ------------------------------------------------------------------
    # Emergency ETA check
    # ------------------------------------------------------------------

    def _check_eta_activation(self, current_time: float) -> None:
        """Activate EMERGENCY_GREEN when ETA becomes imminent."""
        for eid, payload in list(self._active_emergencies.items()):
            eta = payload.eta_to_intersection.get(self.intersection_id, float("inf"))
            time_until = eta - current_time
            if 0 <= time_until <= ETA_IMMINENT_THRESHOLD:
                if self._signal.state == SignalState.EMERGENCY_PREPARE:
                    self._signal.activate_emergency_green(eid)
                    logger.info(
                        "[%s] Activating EMERGENCY_GREEN (ETA imminent %.1fs)",
                        self.agent_id,
                        time_until,
                    )

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    def _handle_message(self, msg: AgentMessage) -> None:
        """Process an incoming message from the bus."""
        if msg.type == MessageType.EMERGENCY_PRIORITY:
            self._handle_emergency_priority(msg)
        elif msg.type == MessageType.ROUTE_FORWARD:
            self._handle_route_forward(msg)
        elif msg.type == MessageType.EMERGENCY_PASSED:
            self._handle_emergency_passed(msg)
        elif msg.type == MessageType.TRAFFIC_UPDATE:
            self._handle_traffic_update(msg)
        elif msg.type == MessageType.SIGNAL_STATUS:
            self._handle_signal_status(msg)
        elif msg.type == MessageType.ACK:
            pass  # Acknowledgements logged but no action required
        else:
            logger.debug("[%s] Unhandled message type %s", self.agent_id, msg.type)

    # ------------------------------------------------------------------
    # Emergency Priority (R1 / R2 / R4 / R5)
    # ------------------------------------------------------------------

    def _handle_emergency_priority(self, msg: AgentMessage) -> None:
        payload = EmergencyPriorityPayload(**msg.payload)
        eid = payload.emergency_id

        # R5 – duplicate guard: ignore if already processing OR already completed/passed
        if eid in self._processed_emergency_ids:
            # Allow re-entry only if the intersection has no active emergency state
            # and the signal is in a normal state (not already recovered from this EV)
            already_active = eid in self._active_emergencies
            from backend.communication.schemas import SignalState as _SS
            signal_in_emergency = self._signal.state in (
                _SS.EMERGENCY_PREPARE, _SS.EMERGENCY_GREEN, _SS.EMERGENCY_CLEAR
            )
            if already_active or not signal_in_emergency:
                # Either already handling it, or signal already recovered → ignore duplicate
                if already_active:
                    logger.debug("[%s] Duplicate emergency %s – already active, ignored", self.agent_id, eid)
                else:
                    logger.debug("[%s] Duplicate emergency %s – already processed and recovered, ignored", self.agent_id, eid)
                self._send_ack(msg)
                return

        self._processed_emergency_ids.add(eid)

        # R4 – is this intersection on the route?
        if self.intersection_id not in payload.route:
            logger.debug(
                "[%s] R4 – intersection not on emergency route %s",
                self.agent_id,
                eid,
            )
            self._send_ack(msg)
            return

        # R1 / R2 – intersection is on route
        eta = payload.eta_to_intersection.get(self.intersection_id, float("inf"))
        self._active_emergencies[eid] = payload
        self._signal.prepare_emergency(eid, eta, msg.timestamp)

        # Forward route information to next relevant TSA
        self._forward_route_to_next(payload, msg.timestamp)
        self._send_ack(msg)

    def _handle_route_forward(self, msg: AgentMessage) -> None:
        payload = RouteForwardPayload(**msg.payload)
        eid = payload.emergency_id

        if self.intersection_id != payload.next_intersection:
            return  # Not addressed to this intersection

        if eid in self._active_emergencies:
            return  # Already handling this emergency

        self._processed_emergency_ids.add(eid)
        eta = payload.full_eta_map.get(self.intersection_id, payload.eta)

        # Reconstruct a minimal EmergencyPriorityPayload from forward data
        ep = EmergencyPriorityPayload(
            emergency_id=eid,
            route=payload.route,
            priority=self._active_emergencies.get(eid, EmergencyPriorityPayload(
                emergency_id=eid, route=payload.route,
                priority=__import__("backend.communication.schemas", fromlist=["EmergencyPriority"]).EmergencyPriority.HIGH,
                eta_to_intersection=payload.full_eta_map,
            )).priority,
            eta_to_intersection=payload.full_eta_map,
        )
        self._active_emergencies[eid] = ep
        self._signal.prepare_emergency(eid, eta, msg.timestamp)
        self._forward_route_to_next(ep, msg.timestamp)
        self._send_ack(msg)

    def _forward_route_to_next(self, payload: EmergencyPriorityPayload, current_time: float) -> None:
        """
        Notify the next TSA on the route (TSA coordination for green corridor).
        Each TSA notifies only the next relevant TSA – no broadcast to all.
        """
        route = payload.route
        try:
            idx = route.index(self.intersection_id)
        except ValueError:
            return

        if idx + 1 >= len(route):
            return  # This is the last intersection on the route

        next_intersection = route[idx + 1]
        next_agent_id = self._intersection_to_agent(next_intersection)
        if next_agent_id is None or next_agent_id not in self.neighbor_ids:
            return  # Next hop is not a direct neighbor

        next_eta = payload.eta_to_intersection.get(next_intersection, float("inf"))
        fwd_msg = AgentMessage(
            type=MessageType.ROUTE_FORWARD,
            sender_id=self.agent_id,
            receiver_id=next_agent_id,
            timestamp=current_time,
            payload=RouteForwardPayload(
                emergency_id=payload.emergency_id,
                route=payload.route,
                next_intersection=next_intersection,
                eta=next_eta,
                full_eta_map=payload.eta_to_intersection,
            ).model_dump(),
        )
        self._bus.post(fwd_msg)
        logger.debug(
            "[%s] Forwarded route to %s for emergency %s",
            self.agent_id,
            next_agent_id,
            payload.emergency_id,
        )

    def _intersection_to_agent(self, intersection_id: str) -> Optional[str]:
        """Map intersection ID to TSA agent ID."""
        mapping = {"I1": "TSA-1", "I2": "TSA-2", "I3": "TSA-3", "I4": "TSA-4", "I5": "TSA-5"}
        return mapping.get(intersection_id)

    # ------------------------------------------------------------------
    # Emergency Passed (R3)
    # ------------------------------------------------------------------

    def _handle_emergency_passed(self, msg: AgentMessage) -> None:
        payload = EmergencyPassedPayload(**msg.payload)
        eid = payload.emergency_id

        if payload.intersection_id != self.intersection_id:
            return  # Not for this intersection

        if self._signal.emergency_passed(eid):
            logger.info("[%s] R3 – recovery started for emergency %s", self.agent_id, eid)
            self._active_emergencies.pop(eid, None)
        self._send_ack(msg)

    # ------------------------------------------------------------------
    # Normal traffic coordination
    # ------------------------------------------------------------------

    def _broadcast_traffic_update(self, current_time: float) -> None:
        """Send local traffic state to all configured neighbours."""
        vehicle_count = self._traffic.get_vehicle_count(self.intersection_id)
        queue_length = self._traffic.get_queue_length(self.intersection_id)
        congestion = self._traffic.get_congestion_ratio(self.intersection_id)
        avg_speed = self._traffic.get_average_speed(self.intersection_id)

        payload = TrafficUpdatePayload(
            vehicle_count=vehicle_count,
            queue_length=queue_length,
            signal_state=self._signal.state,
            congestion_ratio=round(congestion, 3),
            average_speed=round(avg_speed, 1),
        )
        for neighbor_id in self.neighbor_ids:
            msg = AgentMessage(
                type=MessageType.TRAFFIC_UPDATE,
                sender_id=self.agent_id,
                receiver_id=neighbor_id,
                timestamp=current_time,
                payload=payload.model_dump(),
            )
            self._bus.post(msg)

    def _handle_traffic_update(self, msg: AgentMessage) -> None:
        payload = TrafficUpdatePayload(**msg.payload)
        self._neighbor_states[msg.sender_id] = payload
        # Local rule: if a neighbour has excessive queue, consider extending green
        # (Rule-based – no global optimizer)
        if payload.queue_length > 8 and self._signal.state == SignalState.NORMAL_GREEN:
            # Extend this green slightly by resetting elapsed – conservative
            # This is a local heuristic, not a central decision
            pass  # Simple implementation: no forced extension to keep it clean

    def _handle_signal_status(self, msg: AgentMessage) -> None:
        # Log for awareness; no direct action needed
        pass

    # ------------------------------------------------------------------
    # ACK helper
    # ------------------------------------------------------------------

    def _send_ack(self, original: AgentMessage) -> None:
        ack = AgentMessage(
            type=MessageType.ACK,
            sender_id=self.agent_id,
            receiver_id=original.sender_id,
            timestamp=original.timestamp,
            payload=AckPayload(
                message_id=original.message_id,
                receiver_id=self.agent_id,
                status="OK",
            ).model_dump(),
        )
        self._bus.post(ack)

    # ------------------------------------------------------------------
    # Virtual sensor reads (expose state to engine/API)
    # ------------------------------------------------------------------

    def get_signal_state_model(self):
        from backend.communication.schemas import SignalStateModel
        return SignalStateModel(
            state=self._signal.state,
            phase_elapsed=round(self._signal.phase_elapsed, 2),
            phase_remaining=round(self._signal.phase_remaining, 2),
        )

    def reset(self, cycle_offset: float = 0.0) -> None:
        self._active_emergencies.clear()
        self._processed_emergency_ids.clear()
        self._neighbor_states.clear()
        self._tick_count = 0
        self._signal.reset(cycle_offset)
