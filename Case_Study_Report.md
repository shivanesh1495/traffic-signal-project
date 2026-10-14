# Case Study Report

# Multi-Agent Urban Traffic Signal Synchronization System with Emergency Vehicle Priority ("GreenCorridor")

*Submitted By*

Arlagadda Jagruthi, CB.SC.U4CSE23709
Preethi Kannan, CB.SC.U4CSE23738
Shivanesh M C, CB.SC.U4CSE23743

*in partial fulfilment of the requirements for the course of*

**23CSE401 - Fundamentals of Artificial Intelligence**

**Academic Year 2026-27 Odd Semester**

**DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING**  
**AMRITA SCHOOL OF COMPUTING**  
**AMRITA VISHWA VIDYAPEETHAM**  
**COIMBATORE - 641 112**

---

## Contents

1. Introduction
2. PEAS Description
3. Agent and Environment Analysis
4. Design
5. Implementation
6. Testing and Results

---

## 1. Introduction

Urban traffic congestion is one of the most persistent challenges in modern cities. When an emergency vehicle — an ambulance, fire truck, or police car — is dispatched through a city grid, it routinely encounters red signals at each intersection, adding precious seconds to its response time. Coordinating all traffic signals through a centralized controller is both slow and brittle; a single point of failure can disrupt the entire network.

This project, **GreenCorridor**, addresses this problem through a **decentralized multi-agent system (MAS)** that creates an intelligent green corridor for emergency vehicles. The system consists of five autonomous **Traffic Signal Agents (TSAs)**, one per intersection, each managing only its own traffic signal. An **Emergency Vehicle Agent (EVA)** uses the **A\* informed search algorithm** to plan the optimal low-congestion route through the network, then coordinates with the relevant TSAs to prepare a sequential green corridor ahead of the vehicle. Once the emergency vehicle clears each intersection, the signal immediately recovers to normal operation — minimizing disruption to cross-traffic.

The project is a **100% software simulation** — there is no physical hardware. All sensors (GPS, vehicle density, queue length, speed) are virtual functions derived from simulated vehicle positions and physics. The road network models five intersections (I1–I5) connected by twelve directed edges, with ordinary vehicles being spawned and routed concurrently to create realistic dynamic traffic conditions.

The system is implemented as a **Python backend** (FastAPI + Pydantic) coupled with a **React/Vite frontend** that provides a live SVG visualization of the road network, signal states, vehicle positions, agent message logs, and evaluation metrics. Six distinct test scenarios cover normal traffic, low/high congestion emergencies, alternative routing, and dynamic replanning — enabling systematic evaluation of the multi-agent design.

**AI Concepts demonstrated:**

| AI Concept | Where it appears |
|---|---|
| Multi-Agent Systems | 5 TSAs + Vehicle Agents + Emergency Vehicle Agent |
| PEAS Framework | Formal agent definitions for all three agent types |
| A\* Informed Search | Emergency route planning with dynamic edge costs |
| Heuristic Search | f(n) = g(n) + h(n) with admissible Euclidean heuristic |
| Rule-Based Reasoning | Emergency priority rules R1–R5 in each TSA |
| Decentralized Decision-Making | Local signal control; chain message forwarding |
| Partially Observable Environment | Each TSA perceives only its own intersection |
| Dynamic Environment | Traffic and signal states change every simulation tick |

---

## 2. PEAS Description

The system contains three distinct agent types. The PEAS (Performance, Environment, Actuators, Sensors) framework is described for each below.

---

### 2.1 Traffic Signal Agent (TSA) — 5 Instances (TSA-1 through TSA-5)

#### Performance Measure
- **Primary:** Minimize emergency vehicle travel time and delay (time to clear green corridor intersections on route).
- **Secondary:** Maximize vehicle throughput (vehicles completing journeys per second).
- **Safety:** Minimize average vehicle waiting time; ensure safe signal transitions (yellow → all-red gap before any green).
- **Constraint:** Never grant EMERGENCY_GREEN while another conflicting signal phase is active on the same intersection.

#### Environment
- The local intersection it controls (one of I1–I5).
- Adjacent road edges with dynamic traffic state (vehicle count, queue length, average speed, congestion ratio).
- Incoming agent messages from the Emergency Vehicle Agent and neighboring TSAs.
- Current signal phase state and elapsed phase time.

#### Actuators

| Actuator | Triggered By | Effect |
|---|---|---|
| `SignalController.tick(dt)` | Every simulation tick | Advances normal GREEN → YELLOW → RED cycle |
| `SignalController.prepare_emergency(id, eta, t)` | EMERGENCY_PRIORITY received | Transitions signal to EMERGENCY_PREPARE |
| `SignalController.activate_emergency_green(id)` | ETA becomes imminent (< 10 s) | Transitions signal to EMERGENCY_GREEN (green corridor) |
| `SignalController.emergency_passed(id)` | EMERGENCY_PASSED received | Transitions signal to EMERGENCY_CLEAR → recovery |
| `MessageBus.post(ROUTE_FORWARD)` | After handling EMERGENCY_PRIORITY | Forwards route info to next TSA on the corridor |
| `MessageBus.post(TRAFFIC_UPDATE)` | Every 5 simulation ticks | Broadcasts local traffic state to neighbor TSAs |
| `MessageBus.post(ACK)` | On receipt of any message | Acknowledges receipt to sender |

#### Sensors

| Sensor | Virtual Implementation | Provides |
|---|---|---|
| Vehicle density sensor | `TrafficManager.get_vehicle_count(intersection_id)` | Number of vehicles at the intersection |
| Queue sensor | `TrafficManager.get_queue_length(intersection_id)` | Number of stopped/queued vehicles |
| Congestion sensor | `TrafficManager.get_congestion_ratio(intersection_id)` | Congestion as a 0–1 ratio |
| Speed sensor | `TrafficManager.get_average_speed(intersection_id)` | Mean vehicle speed at intersection (km/h) |
| Signal state sensor | `SignalController.get_signal_state()` | Current signal phase (one of 6 states) |
| Message receiver | `MessageBus` (registered handler) | `AgentMessage` objects from EVA and neighbor TSAs |

#### Input–Sensor Mapping

| Input | Sensor |
|---|---|
| Local traffic density | `get_vehicle_count(intersection_id)` |
| Waiting vehicles | `get_queue_length(intersection_id)` |
| Traffic congestion level | `get_congestion_ratio(intersection_id)` |
| Current intersection speed | `get_average_speed(intersection_id)` |
| Own signal phase | `get_signal_state()` |
| Emergency vehicle approaching | Incoming `EMERGENCY_PRIORITY` / `ROUTE_FORWARD` message |
| Emergency vehicle passed | Incoming `EMERGENCY_PASSED` message |
| Neighbor traffic state | Incoming `TRAFFIC_UPDATE` message |

#### Output–Actuator Mapping

| Output Decision | Actuator |
|---|---|
| Normal phase advance | `SignalController.tick(dt)` |
| Prepare green corridor | `SignalController.prepare_emergency()` |
| Activate green corridor | `SignalController.activate_emergency_green()` |
| Begin signal recovery | `SignalController.emergency_passed()` |
| Propagate corridor to next intersection | `MessageBus.post(ROUTE_FORWARD)` |
| Share traffic state with neighbors | `MessageBus.post(TRAFFIC_UPDATE)` |

---

### 2.2 Emergency Vehicle Agent (EVA) — 1 Instance

#### Performance Measure
- Minimize total travel time from dispatch location to destination.
- Minimize delay compared to free-flow (uncongested) traversal time.
- Select the route with the lowest combined dynamic cost (travel time, congestion, waiting time).
- Successfully coordinate a sequential green corridor through all on-route intersections.

#### Environment
- The complete static road network topology (5 intersections, 12 directed edges).
- Dynamic edge traffic states (congestion ratios, vehicle counts, waiting times) — read via virtual sensors.
- Current vehicle position (node, edge, fraction along edge).
- The set of TSAs along the planned route.

#### Actuators

| Actuator | Effect |
|---|---|
| `AStarRouter.find_route(start, goal)` | Plans minimum-cost route through network |
| `_calculate_eta(current_time)` | Computes per-intersection ETA |
| `MessageBus.post(EMERGENCY_PRIORITY)` | Notifies first TSA on route; initiates green corridor |
| `MessageBus.post(EMERGENCY_PASSED)` | Notifies each TSA after EV clears their intersection |
| `_move(dt, current_time)` | Advances vehicle position along route at emergency speed |
| `_check_replan(current_time)` | Re-runs A\* if remaining route cost changed > 15% |

#### Sensors

| Sensor | Virtual Implementation | Provides |
|---|---|---|
| GPS (position sensor) | `current_node` / `current_edge` from `EmergencyVehicleModel` | Current location in network |
| Speed sensor | `EmergencyVehicleModel.speed` (constant 60 km/h) | Current travel speed |
| ETA sensor | `get_eta(intersection_id)` — from computed `eta_map` | Estimated time to reach each intersection |
| Congestion sensor | `RoadNetwork.edge_cost(from, to)` — dynamic | Live edge costs for replanning |

#### Input–Sensor Mapping

| Input | Sensor |
|---|---|
| Current position | Virtual GPS (`current_node`, `current_edge`, `position`) |
| Travel speed | `EmergencyVehicleModel.speed` |
| Route progress | `route_index` into route list |
| Dynamic route costs | `RoadNetwork.edge_cost()` |

#### Output–Actuator Mapping

| Output Decision | Actuator |
|---|---|
| Planned route | `AStarRouter.find_route()` |
| Priority corridor request | `MessageBus.post(EMERGENCY_PRIORITY)` |
| Intersection cleared notification | `MessageBus.post(EMERGENCY_PASSED)` |
| Position update | `_move(dt, current_time)` |
| Route revision | `_check_replan()` + re-dispatch EMERGENCY_PRIORITY |

---

### 2.3 Vehicle Agent (Ordinary Traffic) — Many Instances

#### Performance Measure
- Reach assigned destination.
- Minimize accumulated waiting time at red signals.

#### Environment
- Current road edge and position along it.
- Signal state at the next intersection on the route.
- Assigned destination and remaining route.

#### Actuators
- `decide(perception)` — returns one of `"go"`, `"slow"`, or `"stop"`.
- Position update handled by `TrafficManager` based on the decision.

#### Sensors
- `perceive(signals)` — reads: `current_node`, `current_edge`, `position` (0–1 along edge), `speed`, signal state at next intersection, `destination`, `route_index`, `waiting` flag.

---

## 3. Agent and Environment Analysis

### 3.1 Agent Category

#### Traffic Signal Agent (TSA)

Each TSA is a **goal-based, utility-maximizing, rule-based reactive agent** with the following properties:

- **Reactive:** Responds immediately to incoming messages (EMERGENCY_PRIORITY, EMERGENCY_PASSED) and to the current signal phase state.
- **Goal-based:** Has explicit goals — maintain safe signal cycling under normal conditions; clear the green corridor ahead of an emergency vehicle under emergency conditions.
- **Rule-based:** Five explicitly coded rules (R1–R5) govern all emergency-related decisions. There is no learning; logic is fixed and deterministic given the same inputs.
- **Cooperative:** Actively assists the EVA by entering EMERGENCY_PREPARE, activating EMERGENCY_GREEN, and forwarding the corridor to the next TSA in the chain.
- **Decentralized:** Each TSA holds a reference only to its own `SignalController`. It structurally cannot access or modify any other intersection's signal — this is enforced at the architecture level, not just by convention.

**Agent type:** Reflex agent with state (the signal phase history, active emergency contexts, processed message IDs, and tick count constitute the agent's internal state).

#### Emergency Vehicle Agent (EVA)

The EVA is a **goal-based utility agent** that uses **informed search** for decision-making:

- **Goal-based:** Has a fixed goal — reach the destination as fast as possible.
- **Planning:** Performs A\* search to find the minimum-cost route before acting.
- **Utility-driven:** Route selection is driven by a multi-component edge cost function balancing travel time, congestion, and waiting time.
- **Adaptive:** Re-evaluates the route every 5 seconds and replans if conditions change significantly (replan threshold: 15% cost change).
- **Communicative:** Sends structured priority messages to TSAs to coordinate the corridor ahead of its movement.

**Agent type:** Goal-based model-based agent (it maintains an internal model of the route and ETAs, updates it periodically via sensors, and acts based on that model).

#### Vehicle Agent (Ordinary Traffic)

Each ordinary vehicle is a **simple reflex agent**:

- **Reflex:** Observes the signal state at its next intersection and decides to go, slow, or stop based on a direct condition-action rule.
- **No learning:** Behavior is fully determined by the current perception.

**Agent type:** Simple reflex agent.

---

### 3.2 Environment Classification

| Property | Value | Justification |
|---|---|---|
| **Fully vs. Partially Observable** | **Partially Observable** | Each TSA only perceives its own intersection's local state and messages from configured neighbors. The EVA perceives only its own position and edge costs — not the full positions of all vehicles. No agent has a global view. |
| **Deterministic vs. Stochastic** | **Stochastic** | Vehicle spawning is random by default (`random_seed = -1`). Traffic distributions vary between runs. Congestion on edges depends on random vehicle arrival patterns. A fixed `random_seed` is available for reproducible (deterministic) testing. |
| **Episodic vs. Sequential** | **Sequential** | Each agent's decision affects future state. A TSA's signal phase transition influences queue buildup on adjacent edges, which in turn affects A\* route costs in subsequent ticks. The EVA's replanning decisions at tick T affect corridor coordination at tick T+N. |
| **Static vs. Dynamic** | **Dynamic** | The environment changes continuously while agents deliberate. New vehicles spawn each tick, edge congestion shifts, signal phases advance, and ETA calculations become outdated within seconds. The environment is actively changing between each agent's decision and its execution. |
| **Discrete vs. Continuous** | **Hybrid** | Time is discrete (1-second ticks). Signal states are discrete (6 enumerated values). Vehicle positions are continuous (0.0–1.0 fraction along an edge). Edge costs are real-valued continuous. |
| **Single-Agent vs. Multi-Agent** | **Multi-Agent (Cooperative)** | 5 TSAs + 1 EVA + multiple ordinary Vehicle Agents operate simultaneously. TSAs cooperate by chain-forwarding the green corridor without a central director. The EVA and TSAs cooperate toward the shared goal of minimizing emergency travel time. Ordinary vehicles are passive and do not communicate. |

---

## 4. Design

### 4.1 System Architecture

The system follows a **two-tier client-server architecture**:

- **Backend:** Python (FastAPI) — all simulation logic, agent behavior, A\* algorithm, message passing, and metrics computation.
- **Frontend:** React/Vite (JavaScript) — live visualization of the simulation state via REST polling.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React/Vite)                        │
│  NetworkMap  │  ControlPanel  │  SignalGrid  │  EventLog  │  Panels  │
└────────────────────────────┬─────────────────────────────────────────┘
                             │  HTTP REST (every 500 ms)
                             │  /api/simulation/state
                             │  /api/emergency/dispatch  etc.
┌────────────────────────────▼─────────────────────────────────────────┐
│                         BACKEND (FastAPI)                             │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    Simulation Engine                          │    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │ TrafficManager│  │  MessageBus  │  │ MetricsEvaluator │  │    │
│  │  │  (vehicles,  │  │  (queued msg │  │ (travel time,    │  │    │
│  │  │   sensors)   │  │   delivery)  │  │  throughput…)    │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │    │
│  │                                                              │    │
│  │  ┌───────────────────────────────────────────────────────┐  │    │
│  │  │            5 × TrafficSignalAgent (TSA-1…TSA-5)       │  │    │
│  │  │    each owns one SignalController (6-state machine)   │  │    │
│  │  └───────────────────────────────────────────────────────┘  │    │
│  │                                                              │    │
│  │  ┌────────────────────────────────────────────────────────┐ │    │
│  │  │           EmergencyVehicleAgent (EVA)                  │ │    │
│  │  │    uses AStarRouter → plans route → sends messages     │ │    │
│  │  └────────────────────────────────────────────────────────┘ │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────────────────┐   ┌──────────────────────────────────┐  │
│  │  RoadNetwork (graph)    │   │  network.json (topology +config) │  │
│  └─────────────────────────┘   └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Road Network Topology

The network consists of **5 intersections** and **12 directed edges** (bidirectional roads modeled as two directed edges):

```
I1 (100,300) ──── I2 (300,300) ──── I3 (500,300)
│                 │                        │
│                 │                        │
I4 (200,150) ─────┘               I5 (400,150)
│                                          │
└──────────────────────────────────────────┘
```

| Intersection | Coordinates | Neighbors | Agent ID |
|---|---|---|---|
| I1 | (100, 300) | I2, I4 | TSA-1 |
| I2 | (300, 300) | I1, I3, I4 | TSA-2 |
| I3 | (500, 300) | I2, I5 | TSA-3 |
| I4 | (200, 150) | I1, I2, I5 | TSA-4 |
| I5 | (400, 150) | I3, I4 | TSA-5 |

Edge lengths range from 170–200 metres; speed limits are either 50 km/h (bottom row I1–I2–I3) or 60 km/h (diagonal/vertical edges).

### 4.3 Algorithm: A\* Informed Search

A\* is used exclusively by the Emergency Vehicle Agent for route planning.

**Cost function:**

```
f(n) = g(n) + h(n)

g(n) = accumulated dynamic edge cost from start to node n
h(n) = HEURISTIC_SCALE × (euclidean_distance(n, goal) / max_speed_ms) / REPRESENTATIVE_FF_TIME
```

Where `HEURISTIC_SCALE = 0.50` and `REPRESENTATIVE_FF_TIME = 10.0 s`.

**Dynamic edge cost formula** (weights configurable in `network.json`):

```
edge_cost(u, v) = 0.50 × norm_travel_time
               + 0.30 × congestion_ratio
               + 0.20 × norm_waiting_time
```

- `norm_travel_time = min(1.0, base_cost × max(1.0, travel_time / free_flow_time))`
- `congestion_ratio = min(1.0, vehicle_count / EDGE_CAPACITY)` where `EDGE_CAPACITY = 8`
- `norm_waiting_time = min(1.0, waiting_time / 120.0)`

The heuristic is admissible for the travel-time component (it never overestimates the minimum travel cost). The algorithm uses a **min-heap** (`heapq`) with the `_Node` dataclass for efficient priority queue management.

**Ordinary vehicle routing** uses **Breadth-First Search (BFS)** — a simpler shortest-hop algorithm. A\* is reserved for the EVA per the project specification.

### 4.4 Traffic Signal State Machine

Each `SignalController` implements a 6-state finite state machine:

```
NORMAL_GREEN ──► NORMAL_YELLOW ──► NORMAL_RED
     ▲                                   │
     └───────────────────────────────────┘
                                         │
                               EMERGENCY_PREPARE ◄── (on route priority)
                                         │
                               EMERGENCY_GREEN   (held until PASSED)
                                         │
                               EMERGENCY_CLEAR   (2s all-red)
                                         │
                               NORMAL_GREEN
```

Default phase durations: GREEN = 30 s, YELLOW = 5 s, ALL-RED gap = 2 s.  
Cycles are staggered at startup by `cycle_offset = index × (green_duration / num_intersections)` to prevent all lights turning green simultaneously.

### 4.5 Communication Protocol

All inter-agent communication uses an **in-process asynchronous message bus** (`MessageBus`):

| Message Type | Sender → Receiver | Purpose |
|---|---|---|
| `EMERGENCY_PRIORITY` | EVA → First TSA on route | Initiates green corridor; carries route, ETAs, priority |
| `ROUTE_FORWARD` | TSA-i → Next TSA on route | Chain-propagates corridor to the next intersection ahead |
| `EMERGENCY_PASSED` | EVA → TSA at each intersection | Triggers signal recovery after EV clears intersection |
| `TRAFFIC_UPDATE` | TSA-i → Neighbor TSAs | Shares local vehicle count, queue, congestion, signal state |
| `SIGNAL_STATUS` | TSA-i → Neighbor TSAs | Shares current phase and remaining time |
| `ACK` | Any receiver → Sender | Acknowledges message receipt |

**Bus protections:**
- **Duplicate detection:** Every message carries a UUID `message_id`; re-posting the same ID is silently dropped.
- **Stale message drop:** `EMERGENCY_PRIORITY` and `ROUTE_FORWARD` messages older than 60 s are discarded during delivery.
- **Event log:** All delivered messages are recorded (capped at 2000 entries) and exposed via `/api/events`.

### 4.6 Simulation Tick Order

Each 1-second tick in `SimulationEngine.tick()` proceeds in this order:

1. `TrafficManager.tick()` — spawn new vehicles, move all vehicles, update edge traffic states.
2. `TrafficSignalAgent.tick()` × 5 — advance each signal state machine; check ETA activation.
3. `MessageBus.flush()` — deliver TSA-originated messages (TRAFFIC_UPDATE, ROUTE_FORWARD, ACK).
4. `EmergencyVehicleAgent.tick()` — move EV; send EMERGENCY_PRIORITY (first tick only); send EMERGENCY_PASSED.
5. `MessageBus.flush()` — deliver EV-originated messages.
6. `MetricsEvaluator.update_vehicle_metrics()` and `update_emergency_metrics()`.

### 4.7 Hardware and Software Requirements

#### Hardware Requirements
- Any modern PC or laptop (development and testing environment)
- No embedded hardware, physical sensors, cameras, or IoT devices — the system is 100% software simulated

#### Software Requirements

| Component | Technology | Version |
|---|---|---|
| Programming Language | Python | 3.11+ |
| Backend Framework | FastAPI | 0.110+ |
| Data Validation | Pydantic | 2.x |
| ASGI Server | Uvicorn | 0.29+ |
| Frontend Framework | React | 18 |
| Frontend Build Tool | Vite | 5.x |
| Testing Framework | pytest | 8.x |

#### Python Packages (from `requirements.txt`)
- `fastapi`, `uvicorn[standard]` — REST API server
- `pydantic` — data model validation
- `pytest`, `httpx` — testing

#### Frontend Packages (from `package.json`)
- `react`, `react-dom` — UI framework
- `vite`, `@vitejs/plugin-react` — build tooling
- `eslint` — linting

---

## 5. Implementation

### 5.1 Input Representation

The entire network configuration is loaded from a single JSON file (`backend/config/network.json`) which encodes:

- **Intersections:** `id`, `x`/`y` coordinates (pixels), `neighbors` list, `signal_agent_id`
- **Edges:** `id`, `from_node`, `to_node`, `length` (metres), `speed_limit` (km/h), `base_cost` (free-flow normalised cost)
- **Simulation parameters:** tick duration, vehicle speeds, green/yellow/all-red durations, spawn rate, random seed, stale timeout, replan threshold
- **Cost weights:** `travel_time_weight`, `congestion_weight`, `waiting_time_weight`
- **Scenarios (S0–S5):** name, emergency flag, start/destination nodes, vehicle type, initial vehicle count, congestion hotspot intersections, duration

There is no external dataset — all traffic data is generated synthetically by `TrafficManager`.

### 5.2 Modules and Sub-Modules

#### Backend Modules

**`backend/simulation/engine.py` — SimulationEngine**
- Central orchestrator; owns all agents, the message bus, and metrics evaluator.
- Lifecycle: `start(scenario_id)`, `pause()`, `resume()`, `reset()`, `tick()`.
- `dispatch_emergency()` creates an EVA and calls `plan_route()`.
- `get_state()` returns a complete `SimulationStateModel` snapshot.

**`backend/simulation/network.py` — RoadNetwork**
- Loads and parses `network.json`.
- Provides graph primitives: `neighbors(node)`, `get_edge(from, to)`, `edge_cost(from, to)`, `euclidean_distance(a, b)`, `free_flow_time(from, to)`.
- Dynamic edge state (`vehicle_count`, `congestion_ratio`, etc.) is updated by `TrafficManager` and read by A\*.

**`backend/simulation/signals.py` — SignalController**
- 6-state finite state machine per intersection.
- `tick(dt)` advances normal cycling.
- `prepare_emergency()`, `activate_emergency_green()`, `emergency_passed()` handle emergency transitions.
- Safety fallback: EMERGENCY_GREEN self-recovers after 120 s if EMERGENCY_PASSED is never received.

**`backend/simulation/traffic.py` — TrafficManager**
- Spawns initial vehicles with random origins/destinations; supports `congestion_hotspot` to bias placement.
- Continuously spawns new vehicles at `spawn_rate_per_second = 0.20` vehicles/s.
- Routes ordinary vehicles via BFS; moves them along edges at random speeds (8–42 km/h).
- Updates per-edge metrics each tick: vehicle count, queue length, congestion ratio, average speed, travel time, waiting time.
- Exposes virtual sensor functions: `get_vehicle_count()`, `get_queue_length()`, `get_congestion_ratio()`, `get_average_speed()`.

**`backend/agents/traffic_signal_agent.py` — TrafficSignalAgent**
- One instance per intersection (TSA-1 through TSA-5).
- Registers message handler with the `MessageBus` on construction.
- Implements rules R1–R5 for emergency handling.
- Broadcasts `TRAFFIC_UPDATE` to all configured neighbors every 5 ticks.
- Chain-forwards `ROUTE_FORWARD` to the next TSA on the emergency route.

**`backend/agents/emergency_vehicle_agent.py` — EmergencyVehicleAgent**
- Created dynamically when `dispatch_emergency()` is called.
- Calls `AStarRouter.find_route()` to plan the route.
- Calculates per-intersection ETAs accounting for edge length, speed, and congestion delay.
- Moves along route edges at 60 km/h; sends `EMERGENCY_PASSED` at each intersection.
- Replans route every 5 seconds if cost change exceeds the threshold.

**`backend/algorithms/astar.py` — AStarRouter**
- `find_route(start, goal)` — standard A\* with min-heap and closed set.
- `_heuristic(node, goal)` — Euclidean distance scaled by emergency speed and heuristic constant.
- `_reconstruct(came_from, goal)` — backtracks the `came_from` dict to produce the path.

**`backend/communication/message_bus.py` — MessageBus**
- `register_handler(agent_id, fn)` — binds an agent's callback.
- `post(message)` — enqueues message (UUID-deduplicated).
- `flush(current_time)` — delivers all queued messages; drops stale emergency messages; records event log.

**`backend/communication/schemas.py` — Data Models**
- Pydantic models for all data structures: `IntersectionModel`, `RoadEdgeModel`, `VehicleModel`, `EmergencyVehicleModel`, `AgentMessage`, `SignalStateModel`, `MetricsModel`, `SimulationStateModel`.
- Enumerations: `SignalState` (6), `MessageType` (6), `VehicleType` (4), `EmergencyPriority` (3), `SimulationStatus` (4).

**`backend/metrics/evaluator.py` — MetricsEvaluator**
- `update_vehicle_metrics(total_waiting, completed_count, current_time)` — updates throughput and average waiting.
- `update_emergency_metrics(ev_model)` — computes emergency travel time, delay vs free-flow, and route cost.

**`backend/api/routes.py` — REST API**
- Hosts a module-level `SimulationEngine` singleton.
- 9 endpoints covering simulation lifecycle, emergency dispatch, network topology, metrics, and events.

#### Frontend Modules

**`src/hooks/useSimulation.js`**
- Custom React hook; polls `/api/simulation/state` every 500 ms while simulation is running.
- Exposes `simState`, `network`, `loading`, `error`, and control functions to all components.

**`src/components/NetworkMap.jsx`**
- SVG visualization (620 × 360 px) with coordinate transform from network space to display space.
- Draws road edges (congestion-color-reactive), intersection nodes (signal-state-colored), vehicle dots (blue/yellow), and the emergency vehicle marker (red "EV").
- Emergency route edges highlighted in blue with a glow halo.
- Pulse animation on intersections in emergency state.

**`src/components/ControlPanel.jsx`**
- Scenario preset buttons (Low/High/Dynamic congestion).
- Start, Pause/Resume, Reset, Tick controls; Tick supports long-press for continuous stepping.
- Emergency Dispatch form: EV ID, vehicle type, from/to intersection selectors; displays route and cost after dispatch.

**`src/components/SignalGrid.jsx`**
- Table listing all 5 intersections with their current signal state (color-coded badge) and phase remaining.

**`src/components/EventLog.jsx`**
- Real-time table of the last 80 agent messages in reverse chronological order: timestamp, message type, sender → receiver, payload summary.

**`src/components/MetricsPanel.jsx` and `EmergencyPanel.jsx`**
- Panels for live metric readouts (travel time, delay, waiting, throughput, route cost) and emergency vehicle ETA/status.

### 5.3 Evaluation Scenarios

Six scenarios are pre-configured in `network.json`:

| Scenario | Name | Emergency | Initial Vehicles | Congestion Hotspot | Purpose |
|---|---|---|---|---|---|
| S0 | Normal Traffic | No | 35 | None | Baseline throughput and waiting time |
| S1 | Emergency Low Congestion | Yes (Ambulance I1→I5) | 18 | None | Basic green corridor test |
| S2 | Emergency High Congestion | Yes (Fire Truck I1→I5) | 55 | I4, I5 | A\* routing under congestion |
| S3 | Alternative Routes | Yes (Police I1→I3) | 40 | I4 | A\* route avoidance |
| S4 | Dynamic Congestion | Yes (Ambulance I2→I5) | 45 | I2, I4 | Replanning under changing conditions |
| S5 | Recovery | Yes (Ambulance I1→I3) | 30 | I2 | Signal recovery behavior |

In hotspot scenarios, 60% of initial vehicles are spawned with origins or destinations at the hotspot intersections, creating measurable real congestion that A\* routes around.

### 5.4 User Interface

The frontend provides a live single-page dashboard:

- **Left panel — ControlPanel:** Simulation controls and emergency dispatch form. Scenario preset buttons are disabled once the simulation is running.
- **Center — NetworkMap:** Main SVG visualization showing the road network with real-time updates (signal colors, vehicle positions, EV marker, emergency route highlight). A color legend in the bottom-right explains all states.
- **Bottom-left — MetricsPanel:** Numeric readouts of all evaluation metrics, updated every poll cycle.
- **Bottom-center — SignalGrid:** 5-row table with per-intersection signal state and phase countdown.
- **Bottom-right — EventLog:** Scrolling log of agent messages with color-coded type badges.
- **Bottom — EmergencyPanel:** EV route, per-intersection ETAs, and arrival status.

---

## 6. Testing and Results

### 6.1 Testing Levels

Testing was organized across three levels:

1. **Unit Testing** — individual components in isolation (`test_network.py`, `test_astar.py`, `test_signals.py`, `test_communication.py`)
2. **Integration Testing** — multi-component scenarios (`test_emergency_system.py`)
3. **API/System Testing** — REST endpoints with a live engine (`test_api.py`)

All tests are located in the `tests/` directory and run with `pytest`. The expected result is **98 tests, 0 failures**.

---

### 6.2 Unit Test Cases

#### `test_network.py` — Road Network Graph

| Test | What is verified |
|---|---|
| 5 intersections with correct IDs | Network topology loaded correctly from JSON |
| Correct adjacency for each intersection | Neighbor lists match the configured topology |
| All adjacencies have directed edges | Every neighbor pair has a corresponding `RoadEdgeModel` |
| Edge cost at free-flow equals `w_t × base_cost` | Cost formula baseline (no congestion, no waiting) |
| Edge cost increases with added vehicles | Dynamic cost responds to congestion correctly |
| Missing edge returns infinity | Graph handles non-existent edges gracefully |
| Route cost = sum of individual edge costs | `route_cost()` accumulation is correct |
| Free-flow time formula: `length / speed_ms` | Verified per-edge travel time calculation |
| Euclidean distance calculation | Correct geometric distance between node coordinates |

#### `test_astar.py` — A\* Algorithm

| Test | What is verified |
|---|---|
| Valid route found: I1→I5, I2→I3 | Algorithm finds reachable routes |
| Trivial route: start == goal | Returns single-element route with cost 0 |
| Non-existent node returns None | Graceful failure for invalid inputs |
| All 5 intersections reachable from I1 | Network is fully connected |
| Route contains only valid network nodes | Path reconstruction is correct |
| All consecutive pairs in route share an edge | Spatial validity of the planned route |
| Higher congestion produces higher route cost | Dynamic cost influences path selection |
| Route cost > 0 for non-trivial routes | Sanity check on cost formula |

#### `test_signals.py` — Signal State Machine

| Test | What is verified |
|---|---|
| Initial state is NORMAL_GREEN | Constructor default |
| GREEN→YELLOW after 30 s | Normal phase transition |
| YELLOW→RED after 5 s | Normal phase transition |
| RED→GREEN after 2 s all-red | Normal cycle completion |
| Phase elapsed resets on each transition | State machine reset logic |
| Phase remaining decreases over time | Timer countdown behavior |
| Cycle offset staggers signal start | Staggering mechanism works |
| `prepare_emergency()` from GREEN or RED → PREPARE | Emergency entry works from both states |
| PREPARE → EMERGENCY_GREEN after yellow+all_red | Safety-timeout transition |
| `activate_emergency_green()` with correct ID | Explicit green activation |
| `activate_emergency_green()` with wrong ID returns False | ID guard works |
| EMERGENCY_GREEN held for 100 ticks (no PASSED) | Signal holds green during corridor |
| `emergency_passed()` → EMERGENCY_CLEAR | Recovery triggered by PASSED message |
| `emergency_passed()` with wrong ID fails | ID guard works for recovery |
| EMERGENCY_CLEAR → NORMAL_GREEN after all-red | Full recovery cycle |
| TSA-1 structurally cannot affect TSA-2's controller | Decentralization enforced architecturally |

#### `test_communication.py` — Message Bus

| Test | What is verified |
|---|---|
| Each message has unique UUID | `message_id` uniqueness |
| Pydantic payload validation | `TrafficUpdatePayload`, `EmergencyPriorityPayload` fields |
| Message delivered to registered handler | Basic delivery |
| Message not delivered without handler | Handler absence is handled gracefully |
| Multiple recipients receive correct messages | Per-recipient queuing |
| EMERGENCY_PRIORITY older than stale_timeout dropped | Stale detection works |
| Fresh EMERGENCY_PRIORITY delivered | Stale check does not affect valid messages |
| TRAFFIC_UPDATE not subject to stale check | Stale check applies only to emergency message types |
| Duplicate `message_id` delivered only once | Deduplication works |
| Different messages all delivered | Normal multi-message delivery |
| Event log populated after delivery | Event recording works |
| `bus.reset()` clears all state | Reset clears queues, handlers, and log |

---

### 6.3 Integration Test Cases — `test_emergency_system.py`

| Test | What is verified |
|---|---|
| Dispatch returns EVA model with correct ID | Successful emergency dispatch |
| Route starts at I1 and ends at I5 | A\* produces correct start/end |
| Invalid destination returns None | Graceful failure for unreachable goal |
| ETA map computed for all route nodes | ETA calculation covers full route |
| Route cost > 0 | Non-trivial route is costed |
| EMERGENCY_PRIORITY reaches TSAs on route after 5 ticks | Priority messaging and delivery confirmed |
| TSAs not on route stay in normal states | Rule R4 (off-route ignore) works |
| Green corridor is sequential: not all signals simultaneously EMERGENCY_GREEN | Time-coordinated corridor confirmed |
| Signals recover after EV passes (EMERGENCY_CLEAR then normal) | Rule R3 (recovery) works end-to-end |
| Travel time > 0 after EV arrives | Metrics populated |
| Route cost matches sum of edge costs at dispatch time | Metric accuracy |
| Virtual sensors return correct types | Sensor interface contract |
| End-to-end: EV reaches destination within 300 ticks | Full scenario completion |

---

### 6.4 API Test Cases — `test_api.py`

| Test | What is verified |
|---|---|
| `/api/network` returns 5 intersections | Network endpoint |
| Start → Pause → Resume → Reset lifecycle | All status transitions |
| `/api/simulation/state` returns 5 signals and vehicles | State snapshot structure |
| Each tick advances `simulation_time` by 1 second | Tick accuracy |
| Tick without start returns 400 | Pre-condition enforcement |
| Dispatch returns route and eta_map | Dispatch response structure |
| Dispatch with invalid destination returns 422 | Error handling |
| Dispatch without started simulation returns 400 | Pre-condition enforcement |
| `/api/metrics` has all required fields | Metrics schema completeness |
| `/api/events` returns list; populated after dispatch + ticks | Event log endpoint |

---

### 6.5 Key Results and Observations

**Scenario S1 — Emergency, Low Congestion (Ambulance I1→I5, 18 vehicles)**

- A\* selects route **I1 → I4 → I5** (via diagonal high-speed edges) in preference to the longer **I1 → I2 → ... → I5** path under low traffic conditions.
- Green corridor activates sequentially: TSA-1 (I1) enters EMERGENCY_PREPARE, then TSA-4 (I4), then TSA-5 (I5) — each approximately when the EV ETA falls within 10 seconds.
- Each signal recovers (EMERGENCY_CLEAR → NORMAL_GREEN) within 2–3 seconds after the EV clears the intersection.
- Emergency travel time: approximately 36–42 seconds for I1→I5 (under low congestion).

**Scenario S2 — Emergency, High Congestion (Fire Truck I1→I5, 55 vehicles, hotspot I4+I5)**

- With I4 and I5 heavily congested, A\* routes the vehicle via **I1 → I2 → I3 → I5** to avoid the congested diagonal path.
- This demonstrates the dynamic edge cost formula correctly penalizing congested routes.
- Emergency travel time increases relative to S1, but delay (vs free-flow) is constrained by the green corridor.

**Scenario S3 — Alternative Routes (Police I1→I3, 40 vehicles, hotspot I4)**

- With I4 congested, A\* routes via **I1 → I2 → I3** (bottom row) rather than through I4.
- TSA-1, TSA-2, TSA-3 all participate in the corridor; TSA-4 and TSA-5 stay in normal operation (Rule R4 confirmed).

**General Observations:**
- The decentralized chain-forwarding mechanism reliably propagates the corridor along all route TSAs with no central coordinator.
- The message bus correctly filters duplicate and stale messages, preventing phantom emergency states.
- Signal recovery is prompt and consistent — no intersection remains in emergency state after the EV departs.
- Ordinary vehicle throughput is measurably higher in S0 (no emergency) compared to S2 (high congestion), confirming that the metrics correctly capture system-level impact.

---

### 6.6 Test Execution

```
cd traffic-signal-project
python -m pytest tests/ -v
```

Expected output:
```
tests/test_network.py         .......... PASSED
tests/test_astar.py           .......... PASSED
tests/test_signals.py         ................. PASSED
tests/test_communication.py   ............ PASSED
tests/test_emergency_system.py ............... PASSED
tests/test_api.py             .......... PASSED

98 passed in X.XXs
```
