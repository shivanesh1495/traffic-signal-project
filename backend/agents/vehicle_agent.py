"""
Vehicle Agent – represents ordinary road vehicles.

Each Vehicle Agent perceives its virtual environment (position, speed,
signal state, nearby traffic) and decides whether to continue, slow,
stop, or follow its selected route.

Movement logic is handled by the TrafficManager (which owns the vehicle
state). The VehicleAgent wrapper exists to satisfy the PEAS architecture
and can be extended with more sophisticated decision-making.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.communication.schemas import SignalState, VehicleModel, VehicleType

logger = logging.getLogger(__name__)


class VehicleAgent:
    """
    Thin agent wrapper around a VehicleModel.

    Perception : current road/intersection, speed, signal state, nearby traffic.
    Decision   : continue, slow, stop, or follow route.
    Action     : update position and speed via TrafficManager.
    """

    def __init__(self, vehicle_model: VehicleModel, traffic_manager) -> None:
        self.vehicle_id = vehicle_model.id
        self._model = vehicle_model
        self._traffic = traffic_manager

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------

    def perceive(self, signals: dict) -> dict:
        """
        Read virtual sensor functions and build a local perception snapshot.
        """
        m = self._model
        signal_state: Optional[SignalState] = None

        # Get signal state at the next intersection on route
        if m.route and m.route_index < len(m.route) - 1:
            next_node = m.route[m.route_index + 1]
            sig = signals.get(next_node)
            if sig:
                signal_state = sig.state

        return {
            "vehicle_id": m.id,
            "current_node": m.current_node,
            "current_edge": m.current_edge,
            "position": m.position,
            "speed": m.speed,
            "signal_at_next": signal_state,
            "destination": m.destination,
            "route_index": m.route_index,
            "waiting": m.waiting,
        }

    # ------------------------------------------------------------------
    # Decision (rule-based)
    # ------------------------------------------------------------------

    def decide(self, perception: dict) -> str:
        """
        Simple rule-based decision.

        Returns: "go", "slow", "stop"
        """
        signal = perception.get("signal_at_next")
        position = perception.get("position", 0.0)
        approaching = position > 0.6

        if signal is None:
            return "go"

        if approaching:
            if signal in (SignalState.NORMAL_RED, SignalState.EMERGENCY_PREPARE):
                return "stop"
            if signal == SignalState.NORMAL_YELLOW:
                return "slow"

        return "go"

    # ------------------------------------------------------------------
    # Model access
    # ------------------------------------------------------------------

    @property
    def model(self) -> VehicleModel:
        return self._model
