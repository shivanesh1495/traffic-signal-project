"""
Communication schemas and data models for the Multi-Agent Traffic System.
All data structures use Pydantic for validation.
"""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SignalState(str, Enum):
    NORMAL_GREEN = "NORMAL_GREEN"
    NORMAL_YELLOW = "NORMAL_YELLOW"
    NORMAL_RED = "NORMAL_RED"
    EMERGENCY_PREPARE = "EMERGENCY_PREPARE"
    EMERGENCY_GREEN = "EMERGENCY_GREEN"
    EMERGENCY_CLEAR = "EMERGENCY_CLEAR"


class MessageType(str, Enum):
    TRAFFIC_UPDATE = "TRAFFIC_UPDATE"
    EMERGENCY_PRIORITY = "EMERGENCY_PRIORITY"
    ROUTE_FORWARD = "ROUTE_FORWARD"
    SIGNAL_STATUS = "SIGNAL_STATUS"
    EMERGENCY_PASSED = "EMERGENCY_PASSED"
    ACK = "ACK"


class VehicleType(str, Enum):
    NORMAL = "normal"
    AMBULANCE = "ambulance"
    FIRE_TRUCK = "fire_truck"
    POLICE = "police"


class EmergencyPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SimulationStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Road network data models
# ---------------------------------------------------------------------------

class IntersectionModel(BaseModel):
    id: str
    x: float
    y: float
    neighbors: List[str]
    signal_agent_id: str


class RoadEdgeModel(BaseModel):
    id: str
    from_node: str
    to_node: str
    length: float          # metres
    speed_limit: float     # km/h
    base_cost: float = 0.5  # free-flow normalised travel-time component (0-1)
    vehicle_count: int = 0
    queue_length: int = 0
    average_speed: float = 0.0
    travel_time: float = 0.0      # seconds
    waiting_time: float = 0.0     # seconds
    congestion_ratio: float = 0.0  # 0–1


class SignalStateModel(BaseModel):
    state: SignalState = SignalState.NORMAL_RED
    phase_elapsed: float = 0.0    # seconds in current phase
    phase_remaining: float = 0.0  # seconds until next transition


# ---------------------------------------------------------------------------
# Vehicle data models
# ---------------------------------------------------------------------------

class VehicleModel(BaseModel):
    id: str
    type: VehicleType = VehicleType.NORMAL
    current_edge: Optional[str] = None
    current_node: Optional[str] = None
    position: float = 0.0          # 0–1 fraction along current edge
    speed: float = 0.0             # km/h
    destination: str = ""
    route: List[str] = Field(default_factory=list)  # list of intersection IDs
    route_index: int = 0           # index into route of current/next intersection
    waiting: bool = False
    waiting_time_accumulated: float = 0.0
    reached_destination: bool = False
    dispatch_time: float = 0.0


class EmergencyVehicleModel(BaseModel):
    id: str
    type: VehicleType = VehicleType.AMBULANCE
    current_node: Optional[str] = None
    current_edge: Optional[str] = None
    position: float = 0.0          # 0–1 fraction along current edge
    speed: float = 60.0            # km/h – emergency speed
    destination: str = ""
    route: List[str] = Field(default_factory=list)
    route_index: int = 0
    priority: EmergencyPriority = EmergencyPriority.HIGH
    eta_map: Dict[str, float] = Field(default_factory=dict)  # intersection_id -> ETA seconds
    dispatch_time: float = 0.0
    arrival_time: Optional[float] = None
    active: bool = True
    route_cost: float = 0.0


# ---------------------------------------------------------------------------
# Agent message models
# ---------------------------------------------------------------------------

def _new_message_id() -> str:
    return str(uuid.uuid4())


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=_new_message_id)
    type: MessageType
    sender_id: str
    receiver_id: str
    timestamp: float  # simulation time (seconds)
    payload: Dict[str, Any] = Field(default_factory=dict)
    acknowledged: bool = False


class TrafficUpdatePayload(BaseModel):
    vehicle_count: int
    queue_length: int
    signal_state: SignalState
    congestion_ratio: float
    average_speed: float = 0.0


class EmergencyPriorityPayload(BaseModel):
    emergency_id: str
    route: List[str]
    priority: EmergencyPriority
    eta_to_intersection: Dict[str, float]
    vehicle_type: VehicleType = VehicleType.AMBULANCE


class RouteForwardPayload(BaseModel):
    emergency_id: str
    route: List[str]
    next_intersection: str
    eta: float
    full_eta_map: Dict[str, float] = Field(default_factory=dict)


class SignalStatusPayload(BaseModel):
    signal_state: SignalState
    phase_remaining: float


class EmergencyPassedPayload(BaseModel):
    emergency_id: str
    intersection_id: str


class AckPayload(BaseModel):
    message_id: str
    receiver_id: str
    status: str = "OK"


# ---------------------------------------------------------------------------
# Metrics model
# ---------------------------------------------------------------------------

class MetricsModel(BaseModel):
    emergency_travel_time: float = 0.0    # seconds
    emergency_delay: float = 0.0          # actual - free-flow
    average_waiting_time: float = 0.0     # seconds per vehicle
    throughput: float = 0.0               # vehicles/evaluation_period
    route_cost: float = 0.0               # sum of edge costs
    total_vehicles_completed: int = 0
    total_waiting_accumulated: float = 0.0
    evaluation_period: float = 0.0        # seconds


# ---------------------------------------------------------------------------
# Simulation state snapshot (returned by /api/simulation/state)
# ---------------------------------------------------------------------------

class SimulationStateModel(BaseModel):
    status: SimulationStatus = SimulationStatus.IDLE
    current_time: float = 0.0
    tick: int = 0
    intersections: Dict[str, IntersectionModel] = Field(default_factory=dict)
    edges: Dict[str, RoadEdgeModel] = Field(default_factory=dict)
    signals: Dict[str, SignalStateModel] = Field(default_factory=dict)  # key = intersection_id
    vehicles: List[VehicleModel] = Field(default_factory=list)
    emergency_vehicles: List[EmergencyVehicleModel] = Field(default_factory=list)
    metrics: MetricsModel = Field(default_factory=MetricsModel)
    events: List[Dict[str, Any]] = Field(default_factory=list)
