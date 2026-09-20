"""
FastAPI route handlers for the simulation API.

All endpoints interact with the actual SimulationEngine instance.
No fake data is returned.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.simulation.engine import SimulationEngine
from backend.simulation.network import RoadNetwork

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level engine instance (shared across requests)
# ---------------------------------------------------------------------------

_network: Optional[RoadNetwork] = None
_engine: Optional[SimulationEngine] = None


def get_engine() -> SimulationEngine:
    global _engine, _network
    if _engine is None:
        _network = RoadNetwork()
        _engine = SimulationEngine(_network)
    return _engine


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    scenario_id: str = "S1"


class DispatchRequest(BaseModel):
    emergency_id: str = "EV01"
    start_node: str = "I1"
    destination: str = "I5"
    vehicle_type: str = "ambulance"


# ---------------------------------------------------------------------------
# Simulation control endpoints
# ---------------------------------------------------------------------------

@router.post("/simulation/start")
def simulation_start(req: StartRequest) -> Dict[str, Any]:
    """Start a simulation scenario."""
    engine = get_engine()
    engine.start(req.scenario_id)
    return {
        "status": "started",
        "scenario_id": req.scenario_id,
        "simulation_time": engine.current_time,
    }


@router.post("/simulation/pause")
def simulation_pause() -> Dict[str, Any]:
    """Pause a running simulation."""
    engine = get_engine()
    if engine.status.value == "running":
        engine.pause()
        return {"status": "paused", "simulation_time": engine.current_time}
    elif engine.status.value == "paused":
        engine.resume()
        return {"status": "resumed", "simulation_time": engine.current_time}
    return {"status": engine.status.value, "simulation_time": engine.current_time}


@router.post("/simulation/reset")
def simulation_reset() -> Dict[str, Any]:
    """Reset simulation state and metrics."""
    engine = get_engine()
    engine.reset()
    return {"status": "reset", "simulation_time": engine.current_time}


@router.get("/simulation/state")
def simulation_state() -> Dict[str, Any]:
    """Return current complete simulation state."""
    engine = get_engine()
    state = engine.get_state()
    return state.model_dump()


@router.post("/simulation/tick")
def simulation_tick() -> Dict[str, Any]:
    """Advance simulation by exactly one tick (for deterministic testing)."""
    engine = get_engine()
    if engine.status.value not in ("running", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Simulation must be started before ticking. POST /api/simulation/start first.",
        )
    # Allow ticking even when paused (for step-by-step testing)
    prev_status = engine.status
    from backend.communication.schemas import SimulationStatus
    engine._status = SimulationStatus.RUNNING
    engine.tick()
    engine._status = prev_status
    return {
        "tick": engine._tick_count,
        "simulation_time": engine.current_time,
        "status": engine.status.value,
    }


# ---------------------------------------------------------------------------
# Emergency vehicle
# ---------------------------------------------------------------------------

@router.post("/emergency/dispatch")
def emergency_dispatch(req: DispatchRequest) -> Dict[str, Any]:
    """Create and dispatch an emergency vehicle scenario."""
    engine = get_engine()
    if engine.status.value not in ("running", "paused"):
        raise HTTPException(
            status_code=400,
            detail="Start simulation before dispatching emergency vehicle.",
        )
    ev = engine.dispatch_emergency(
        emergency_id=req.emergency_id,
        start_node=req.start_node,
        destination=req.destination,
        vehicle_type=req.vehicle_type,
    )
    if ev is None:
        raise HTTPException(
            status_code=422,
            detail=f"No route found from {req.start_node} to {req.destination}",
        )
    return {
        "status": "dispatched",
        "emergency_id": ev.id,
        "route": ev.route,
        "eta_map": ev.eta_map,
        "route_cost": ev.route_cost,
    }


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

@router.get("/network")
def get_network() -> Dict[str, Any]:
    """Return static road-network configuration."""
    engine = get_engine()
    return {
        "intersections": {
            iid: intr.model_dump()
            for iid, intr in engine.network.intersections.items()
        },
        "edges": {
            eid: edge.model_dump()
            for eid, edge in engine.network.edges.items()
        },
        "sim_config": engine.network.sim_config,
        "cost_weights": engine.network.cost_weights,
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics")
def get_metrics() -> Dict[str, Any]:
    """Return current and final evaluation metrics."""
    engine = get_engine()
    return engine.metrics.get_metrics().model_dump()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@router.get("/events")
def get_events() -> Dict[str, Any]:
    """Return agent/message event log."""
    engine = get_engine()
    return {"events": engine.bus.get_event_log()}
