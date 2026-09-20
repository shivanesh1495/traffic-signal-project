"""
Simulation Engine.

Orchestrates all simulation components:
  - Road network
  - Traffic manager (virtual traffic generator + vehicle movement)
  - Signal controllers (one per intersection)
  - Traffic Signal Agents (one per intersection)
  - Emergency Vehicle Agent
  - Message bus
  - Metrics evaluator

One simulation tick:
  1. Advance traffic (vehicle movement, spawning, edge state update)
  2. Tick all Traffic Signal Agents (state machine + rule checks)
  3. Flush message bus (deliver all queued messages)
  4. Tick Emergency Vehicle Agent (movement + priority messages)
  5. Flush message bus again (deliver EV-originated messages)
  6. Update metrics
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.agents.emergency_vehicle_agent import EmergencyVehicleAgent
from backend.agents.traffic_signal_agent import TrafficSignalAgent
from backend.communication.message_bus import MessageBus
from backend.communication.schemas import (
    EmergencyVehicleModel,
    SimulationStateModel,
    SimulationStatus,
    VehicleType,
)
from backend.metrics.evaluator import MetricsEvaluator
from backend.simulation.network import RoadNetwork
from backend.simulation.signals import SignalController
from backend.simulation.traffic import TrafficManager

logger = logging.getLogger(__name__)


class SimulationEngine:
    """
    Central simulation engine.

    Owns:
    - network       : static road graph
    - traffic       : vehicle management and virtual sensors
    - signals       : dict[intersection_id -> SignalController]
    - tsa_agents    : dict[agent_id -> TrafficSignalAgent]
    - ev_agent      : EmergencyVehicleAgent (or None)
    - bus           : MessageBus
    - metrics       : MetricsEvaluator
    """

    def __init__(self, network: RoadNetwork) -> None:
        self._network = network
        cfg = network.sim_config

        self._tick_seconds: float = float(cfg.get("tick_seconds", 1))
        self._default_duration: float = float(cfg.get("default_duration_seconds", 300))

        self._current_time: float = 0.0
        self._tick_count: int = 0
        self._status: SimulationStatus = SimulationStatus.IDLE

        # Message bus
        self._bus = MessageBus(
            stale_timeout=float(cfg.get("stale_message_timeout", 60))
        )

        # Traffic manager.
        # random_seed == -1 means "new random seed each run" (non-deterministic mode).
        # Any other value fixes the seed for reproducible experiments.
        self._traffic = TrafficManager(
            network=network,
            sim_config=cfg,
            random_seed=int(cfg.get("random_seed", -1)),
        )

        # Signal controllers + TSA agents
        self._signals: Dict[str, SignalController] = {}
        self._tsa_agents: Dict[str, TrafficSignalAgent] = {}
        self._build_agents()

        # Emergency vehicle agent (created when dispatched)
        self._ev_agent: Optional[EmergencyVehicleAgent] = None
        self._ev_model: Optional[EmergencyVehicleModel] = None

        # Metrics
        self._metrics = MetricsEvaluator(network)

        logger.info("SimulationEngine initialised")

    # ------------------------------------------------------------------
    # Build agents
    # ------------------------------------------------------------------

    def _build_agents(self) -> None:
        """Create one SignalController and one TrafficSignalAgent per intersection."""
        cfg = self._network.sim_config
        green = float(cfg.get("normal_green_seconds", 30))
        yellow = float(cfg.get("yellow_seconds", 5))
        all_red = float(cfg.get("all_red_seconds", 2))

        intersection_ids = list(self._network.intersections.keys())

        for idx, iid in enumerate(intersection_ids):
            intersection = self._network.intersections[iid]
            agent_id = intersection.signal_agent_id

            # Stagger cycles so not all lights start green simultaneously
            cycle_offset = idx * (green / len(intersection_ids))

            signal_ctrl = SignalController(
                intersection_id=iid,
                green_seconds=green,
                yellow_seconds=yellow,
                all_red_seconds=all_red,
                cycle_offset=cycle_offset,
            )
            self._signals[iid] = signal_ctrl

            # Build neighbor agent IDs (from network config)
            neighbor_agent_ids = [
                self._network.intersections[n].signal_agent_id
                for n in intersection.neighbors
                if n in self._network.intersections
            ]

            tsa = TrafficSignalAgent(
                agent_id=agent_id,
                intersection_id=iid,
                neighbor_ids=neighbor_agent_ids,
                signal_controller=signal_ctrl,
                message_bus=self._bus,
                traffic_manager=self._traffic,
            )
            self._tsa_agents[agent_id] = tsa

        logger.info("Created %d TSA agents", len(self._tsa_agents))

    # ------------------------------------------------------------------
    # Simulation lifecycle
    # ------------------------------------------------------------------

    def start(self, scenario_id: str = "S1") -> None:
        """Start the simulation with the given scenario."""
        self.reset()
        scenario = self._network.scenarios.get(scenario_id, {})
        initial_vehicles = int(scenario.get("initial_vehicles", 30))
        # congestion_hotspot biases initial vehicle placement onto specific
        # intersections so A* sees real congestion differences between routes.
        hotspot = scenario.get("congestion_hotspot") or []
        self._traffic.initialise(initial_vehicles, congestion_hotspot=hotspot if hotspot else None)
        self._status = SimulationStatus.RUNNING
        logger.info("Simulation started: scenario=%s  hotspot=%s", scenario_id, hotspot)

    def pause(self) -> None:
        if self._status == SimulationStatus.RUNNING:
            self._status = SimulationStatus.PAUSED
            logger.info("Simulation paused at t=%.1f", self._current_time)

    def resume(self) -> None:
        if self._status == SimulationStatus.PAUSED:
            self._status = SimulationStatus.RUNNING
            logger.info("Simulation resumed at t=%.1f", self._current_time)

    def reset(self) -> None:
        """Full reset of simulation state."""
        self._current_time = 0.0
        self._tick_count = 0
        self._status = SimulationStatus.IDLE
        self._ev_agent = None
        self._ev_model = None
        self._traffic.reset()
        self._bus.reset()
        self._metrics.reset()

        cfg = self._network.sim_config
        green = float(cfg.get("normal_green_seconds", 30))
        intersection_ids = list(self._network.intersections.keys())
        for idx, iid in enumerate(intersection_ids):
            cycle_offset = idx * (green / len(intersection_ids))
            self._tsa_agents[self._network.intersections[iid].signal_agent_id].reset(cycle_offset)

        # Re-register handlers (reset cleared the bus handler registry)
        for agent_id, tsa in self._tsa_agents.items():
            self._bus.register_handler(agent_id, tsa._handle_message)

        logger.info("Simulation reset")

    # ------------------------------------------------------------------
    # Emergency vehicle dispatch
    # ------------------------------------------------------------------

    def dispatch_emergency(
        self,
        emergency_id: str,
        start_node: str,
        destination: str,
        vehicle_type: str = "ambulance",
    ) -> Optional[EmergencyVehicleModel]:
        """
        Create and dispatch an Emergency Vehicle Agent.

        Returns the model if dispatch succeeded, None if A* finds no route.
        """
        vtype_map = {
            "ambulance": VehicleType.AMBULANCE,
            "fire_truck": VehicleType.FIRE_TRUCK,
            "police": VehicleType.POLICE,
        }
        vtype = vtype_map.get(vehicle_type, VehicleType.AMBULANCE)

        ev_model = EmergencyVehicleModel(
            id=emergency_id,
            type=vtype,
            current_node=start_node,
            destination=destination,
            dispatch_time=self._current_time,
            speed=float(self._network.sim_config.get("emergency_speed_kmh", 60)),
        )

        ev_agent = EmergencyVehicleAgent(
            model=ev_model,
            network=self._network,
            message_bus=self._bus,
            traffic_manager=self._traffic,
            replan_threshold=float(self._network.sim_config.get("replan_threshold", 0.20)),
        )

        # Plan the route using A*
        if not ev_agent.plan_route(self._current_time):
            logger.error(
                "Emergency dispatch failed: no route from %s to %s",
                start_node,
                destination,
            )
            return None

        self._ev_model = ev_model
        self._ev_agent = ev_agent

        logger.info(
            "Emergency vehicle %s dispatched: %s -> %s  route=%s",
            emergency_id,
            start_node,
            destination,
            " -> ".join(ev_model.route),
        )
        return ev_model

    # ------------------------------------------------------------------
    # Single tick advancement
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance simulation by one tick."""
        if self._status not in (SimulationStatus.RUNNING,):
            return

        dt = self._tick_seconds
        t = self._current_time

        # 1. Traffic movement + edge state update
        signals_snapshot = {
            iid: ctrl.get_signal_state()
            for iid, ctrl in self._signals.items()
        }
        # Build a minimal object that vehicles can query
        from backend.communication.schemas import SignalStateModel
        signal_models = {
            iid: SignalStateModel(state=state)
            for iid, state in signals_snapshot.items()
        }
        self._traffic.tick(t, signal_models)

        # 2. Tick each TSA (state machine transitions)
        for tsa in self._tsa_agents.values():
            tsa.tick(t, dt)

        # 3. Flush bus (deliver TSA-originated messages)
        self._bus.flush(t)

        # 4. Tick emergency vehicle agent
        if self._ev_agent and self._ev_model and self._ev_model.active:
            self._ev_agent.tick(t)

        # 5. Flush bus again (deliver EV-originated messages)
        self._bus.flush(t)

        # 6. Update metrics
        self._metrics.update_vehicle_metrics(
            total_waiting=self._traffic.get_total_waiting(),
            completed_count=self._traffic.get_completed_count(),
            current_time=t,
        )
        if self._ev_model and self._ev_model.arrival_time is not None:
            self._metrics.update_emergency_metrics(self._ev_model)

        self._current_time += dt
        self._tick_count += 1

    def run(self, duration: Optional[float] = None) -> None:
        """Run the simulation for the given duration (synchronous)."""
        if duration is None:
            duration = self._default_duration
        end_time = self._current_time + duration
        while self._current_time < end_time and self._status == SimulationStatus.RUNNING:
            self.tick()
        self._status = SimulationStatus.COMPLETED
        logger.info("Simulation completed at t=%.1f", self._current_time)

    # ------------------------------------------------------------------
    # State snapshot (for API)
    # ------------------------------------------------------------------

    def get_state(self) -> SimulationStateModel:
        """Build and return current simulation state snapshot."""
        from backend.communication.schemas import SignalStateModel

        signals = {
            iid: self._tsa_agents[
                self._network.intersections[iid].signal_agent_id
            ].get_signal_state_model()
            for iid in self._network.intersections
        }

        ev_list = []
        if self._ev_model:
            ev_list.append(self._ev_model)

        return SimulationStateModel(
            status=self._status,
            current_time=round(self._current_time, 2),
            tick=self._tick_count,
            intersections=self._network.intersections,
            edges=self._network.edges,
            signals=signals,
            vehicles=self._traffic.get_all_vehicles(),
            emergency_vehicles=ev_list,
            metrics=self._metrics.get_metrics(),
            events=self._bus.get_event_log()[-50:],
        )

    # ------------------------------------------------------------------
    # Accessors for tests
    # ------------------------------------------------------------------

    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def status(self) -> SimulationStatus:
        return self._status

    @property
    def network(self) -> RoadNetwork:
        return self._network

    @property
    def tsa_agents(self) -> Dict[str, TrafficSignalAgent]:
        return self._tsa_agents

    @property
    def ev_agent(self) -> Optional[EmergencyVehicleAgent]:
        return self._ev_agent

    @property
    def ev_model(self) -> Optional[EmergencyVehicleModel]:
        return self._ev_model

    @property
    def metrics(self) -> MetricsEvaluator:
        return self._metrics

    @property
    def bus(self) -> MessageBus:
        return self._bus

    @property
    def traffic(self) -> TrafficManager:
        return self._traffic

    @property
    def signals(self) -> Dict[str, SignalController]:
        return self._signals
