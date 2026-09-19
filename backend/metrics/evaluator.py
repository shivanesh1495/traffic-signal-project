"""
Metrics Evaluator.

Calculates and tracks all required evaluation metrics:
  - Emergency travel time   : arrival_time - dispatch_time
  - Emergency delay         : actual travel time - estimated free-flow travel time
  - Average waiting time    : total waiting / number of vehicles
  - Throughput              : vehicles completed / evaluation period
  - Route cost              : sum of edge costs along selected route
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.communication.schemas import EmergencyVehicleModel, MetricsModel

logger = logging.getLogger(__name__)


class MetricsEvaluator:
    """Computes and aggregates simulation metrics."""

    def __init__(self, network) -> None:
        self._network = network
        self._metrics = MetricsModel()
        self._total_waiting_accumulated: float = 0.0
        self._vehicle_count_for_avg: int = 0

    def reset(self) -> None:
        self._metrics = MetricsModel()
        self._total_waiting_accumulated = 0.0
        self._vehicle_count_for_avg = 0

    # ------------------------------------------------------------------
    # Update methods called by simulation engine
    # ------------------------------------------------------------------

    def update_vehicle_metrics(
        self,
        total_waiting: float,
        completed_count: int,
        current_time: float,
    ) -> None:
        """Update waiting time and throughput metrics."""
        self._metrics.total_waiting_accumulated = total_waiting
        self._metrics.total_vehicles_completed = completed_count
        self._metrics.evaluation_period = current_time

        if completed_count > 0:
            self._metrics.average_waiting_time = total_waiting / max(1, completed_count)
        if current_time > 0:
            self._metrics.throughput = completed_count / current_time

    def update_emergency_metrics(
        self,
        ev_model: EmergencyVehicleModel,
    ) -> None:
        """Calculate emergency-specific metrics when vehicle arrives."""
        if ev_model.arrival_time is None or ev_model.dispatch_time is None:
            return

        travel_time = ev_model.arrival_time - ev_model.dispatch_time
        self._metrics.emergency_travel_time = travel_time

        # Free-flow travel time along the route
        free_flow = self._free_flow_travel_time(ev_model.route)
        self._metrics.emergency_delay = max(0.0, travel_time - free_flow)

        self._metrics.route_cost = ev_model.route_cost

        logger.info(
            "Emergency metrics: travel_time=%.1fs  free_flow=%.1fs  delay=%.1fs  route_cost=%.4f",
            travel_time,
            free_flow,
            self._metrics.emergency_delay,
            self._metrics.route_cost,
        )

    def _free_flow_travel_time(self, route: List[str]) -> float:
        """Estimate free-flow traversal time for a route in seconds."""
        total = 0.0
        for i in range(len(route) - 1):
            total += self._network.free_flow_time(route[i], route[i + 1])
        return total

    # ------------------------------------------------------------------
    # Accessor
    # ------------------------------------------------------------------

    def get_metrics(self) -> MetricsModel:
        return self._metrics
