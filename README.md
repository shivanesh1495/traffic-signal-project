# Multi-Agent Urban Traffic Signal Synchronization System
## Emergency Vehicle Priority – AI Case Study

A complete, runnable prototype of a **decentralised multi-agent system** for emergency vehicle green-corridor creation. Five independent Traffic Signal Agents coordinate via an in-process message bus. An Emergency Vehicle Agent uses A\* to plan routes and sequentially coordinates green phases as it moves through the network.

---

## Architecture Overview

```
Virtual Traffic Generator
        ↓
Virtual Vehicles + Emergency Vehicle + Traffic Signals
        ↓
     Simulation Engine  (1-second discrete ticks)
        ↓
  Virtual Sensor Functions  (get_vehicle_count, get_queue_length, …)
        ↓
 Traffic Signal Agents (TSA-1…TSA-5) + Emergency Vehicle Agent
        ↓
 A* Route Planning + Agent Communication + Rule-Based Signal Control
        ↓
            Green Corridor
        ↓
      Metrics + React/Vite Visualization
```

### Agent Architecture

| Agent | Count | Responsibility |
|---|---|---|
| Traffic Signal Agent (TSA) | 5 | Controls only its own signal; exchanges traffic info with neighbours; responds to emergency priority |
| Vehicle Agent | 10–40 | Ordinary vehicles; perceive signal state; stop/go decisions |
| Emergency Vehicle Agent | 1 | A\* route planning; sends EMERGENCY_PRIORITY; moves through green corridor |

**Key architectural constraints (non-negotiable):**
- No central controller. Each TSA makes local decisions only.
- Each TSA controls exactly one intersection.
- A\* is used only by the Emergency Vehicle Agent for route planning.
- A\* does NOT directly control any traffic signal.
- Green corridor is sequential/time-coordinated, not all-green simultaneously.

---

## Virtual-Only Architecture

This is a **100% software simulation**. No hardware, cameras, GPS, IoT, or physical sensors.

| Sensor concept | Virtual implementation |
|---|---|
| GPS | `current_node` / `current_edge` from simulation state |
| Vehicle density | `get_vehicle_count(intersection_id)` |
| Queue sensor | `get_queue_length(intersection_id)` |
| Speed sensor | `get_average_speed(intersection_id)` |
| Congestion ratio | `get_congestion_ratio(intersection_id)` |
| Signal state | `get_signal_state(intersection_id)` |
| Traffic state | `get_traffic_state(road_id)` |
| ETA | `get_eta(emergency_id, intersection_id)` |

---

## Network Topology (Fixed)

```
I1 ──── I2 ──── I3
│  \   /│ \     │
│   \ / │  \    │
I4 ───── I2  I5─┘
│               │
└───────────────┘
```

| Intersection | Neighbours | Agent |
|---|---|---|
| I1 | I2, I4 | TSA-1 |
| I2 | I1, I3, I4 | TSA-2 |
| I3 | I2, I5 | TSA-3 |
| I4 | I1, I2, I5 | TSA-4 |
| I5 | I3, I4 | TSA-5 |

---

## A\* Route Planning

Used exclusively by the Emergency Vehicle Agent.

```
f(n) = g(n) + h(n)
g(n) = accumulated dynamic edge cost from start to n
h(n) = straight-line distance / max_emergency_speed × scale_factor
```

**Edge cost formula** (weights configurable in `network.json`):
```
edge_cost = 0.50 × normalised_travel_time
          + 0.30 × congestion_ratio
          + 0.20 × normalised_waiting_time
```

Normalisation:
- `normalised_travel_time = travel_time / free_flow_travel_time` (clamped 0–1)
- `normalised_waiting_time = waiting_time / MAX_WAITING_TIME` (clamped 0–1)

---

## Communication Protocol

In-process async message bus. All messages have unique `message_id` and `timestamp`.

| Message type | Sender → Receiver | Key fields |
|---|---|---|
| TRAFFIC_UPDATE | TSA-i → Neighbour TSA | vehicle_count, queue_length, signal_state, congestion_ratio |
| EMERGENCY_PRIORITY | EV Agent → First TSA on route | emergency_id, route, priority, eta_to_intersection |
| ROUTE_FORWARD | TSA-i → Next TSA on route | emergency_id, route, next_intersection, eta |
| SIGNAL_STATUS | TSA-i → Neighbour TSA | signal_state, phase_remaining |
| EMERGENCY_PASSED | EV Agent → TSA at passed intersection | emergency_id, intersection_id |
| ACK | Receiver → Sender | message_id, status |

**Message rules:**
- Stale EMERGENCY_PRIORITY / ROUTE_FORWARD messages older than `stale_timeout` are dropped.
- Duplicate `message_id` is ignored.
- Each TSA only acts on messages relevant to its own intersection or configured neighbours.

---

## Traffic Signal State Machine

```
NORMAL_GREEN  →  NORMAL_YELLOW  →  NORMAL_RED
     ↑                                  ↓
     └──────────────────────────────────┘
                                        ↓
                               EMERGENCY_PREPARE
                                        ↓
                               EMERGENCY_GREEN  (held until PASSED received)
                                        ↓
                               EMERGENCY_CLEAR  (2s all-red)
                                        ↓
                               NORMAL_GREEN / NORMAL_RED
```

Baseline timings (configurable in `network.json`):
- Normal green: 30 s
- Yellow: 5 s
- All-red: 2 s
- Emergency priority: temporary green override, sequential per intersection

---

## Green Corridor Mechanism

1. EV Agent runs A\* → obtains route `R = [I1, I2, ..., Ik]`
2. EV calculates ETA per upcoming intersection
3. EV sends `EMERGENCY_PRIORITY` to TSA at `I1`
4. Each on-route TSA enters `EMERGENCY_PREPARE` and forwards to next TSA via `ROUTE_FORWARD`
5. When ETA is imminent (< 10 s), TSA activates `EMERGENCY_GREEN`
6. EV moves through the green signal
7. EV sends `EMERGENCY_PASSED` → TSA enters `EMERGENCY_CLEAR` → recovery → `NORMAL`
8. Off-route TSAs continue normal operation (R4 rule)

---

## Project Structure

```
traffic-signal-project/
├── backend/
│   ├── main.py                          # FastAPI app entry point
│   ├── api/
│   │   └── routes.py                    # All API endpoints
│   ├── agents/
│   │   ├── traffic_signal_agent.py      # TSA-1…TSA-5 logic
│   │   ├── vehicle_agent.py             # Ordinary vehicle agent
│   │   └── emergency_vehicle_agent.py   # EV agent + A* dispatch
│   ├── algorithms/
│   │   └── astar.py                     # Custom A* implementation
│   ├── simulation/
│   │   ├── engine.py                    # Simulation orchestrator
│   │   ├── network.py                   # Road network graph
│   │   ├── traffic.py                   # Vehicle management + sensors
│   │   └── signals.py                   # Signal state machine
│   ├── communication/
│   │   ├── message_bus.py               # In-process async message bus
│   │   └── schemas.py                   # Pydantic data models
│   ├── config/
│   │   └── network.json                 # Network topology + parameters
│   └── metrics/
│       └── evaluator.py                 # Metrics calculator
├── frontend/
│   ├── src/
│   │   ├── App.jsx / App.css            # Root layout
│   │   ├── api/client.js                # Backend API client
│   │   ├── hooks/useSimulation.js       # Simulation state hook
│   │   └── components/
│   │       ├── NetworkMap.jsx           # SVG road network visualisation
│   │       ├── ControlPanel.jsx         # Start/Pause/Reset/Dispatch
│   │       ├── EmergencyPanel.jsx       # EV details and ETA
│   │       ├── MetricsPanel.jsx         # Evaluation metrics
│   │       ├── SignalGrid.jsx           # Per-intersection state table
│   │       └── EventLog.jsx             # Live agent message log
│   └── package.json
├── tests/
│   ├── test_astar.py                    # A* algorithm tests
│   ├── test_signals.py                  # Signal state machine tests
│   ├── test_communication.py            # Message bus tests
│   ├── test_emergency_system.py         # Integration + green corridor tests
│   ├── test_network.py                  # Network graph tests
│   └── test_api.py                      # FastAPI endpoint tests
├── requirements.txt
└── README.md
```

---

## Installation

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### Backend Setup

```bash
cd traffic-signal-project

# Install Python dependencies
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd traffic-signal-project/frontend

# Install Node dependencies (if not already done)
npm install
```

---

## Running the Project

### 1. Start the Backend (FastAPI)

Open a terminal in `traffic-signal-project/`:

```bash
uvicorn backend.main:app --reload --port 8000
```

The API is available at: `http://localhost:8000`  
Swagger docs: `http://localhost:8000/docs`

### 2. Start the Frontend (React/Vite)

Open a second terminal in `traffic-signal-project/frontend/`:

```bash
npm run dev
```

The UI is available at: `http://localhost:5173`

---

## Running Tests

```bash
cd traffic-signal-project

# Run all tests with verbose output
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_astar.py -v
python -m pytest tests/test_signals.py -v
python -m pytest tests/test_communication.py -v
python -m pytest tests/test_emergency_system.py -v
python -m pytest tests/test_api.py -v
python -m pytest tests/test_network.py -v
```

Expected: **98 tests, 0 failures**

---

## Running a Simulation Scenario (Command Line)

```python
from backend.simulation.engine import SimulationEngine
from backend.simulation.network import RoadNetwork

net = RoadNetwork()
engine = SimulationEngine(net)

# Start with scenario S1 (emergency, low congestion)
engine.start("S1")

# Dispatch an emergency vehicle I1 → I5
ev = engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
print("Route:", ev.route)
print("ETAs:", ev.eta_map)

# Run until EV arrives
for _ in range(300):
    engine.tick()
    if ev.arrival_time:
        break

metrics = engine.metrics.get_metrics()
print(f"Travel time: {metrics.emergency_travel_time:.1f}s")
print(f"Route cost: {metrics.route_cost:.4f}")
print(f"Avg wait: {metrics.average_waiting_time:.1f}s")
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/simulation/start` | Start scenario (`{"scenario_id": "S1"}`) |
| POST | `/api/simulation/pause` | Toggle pause/resume |
| POST | `/api/simulation/reset` | Reset all state and metrics |
| GET | `/api/simulation/state` | Full simulation state snapshot |
| POST | `/api/simulation/tick` | Advance one tick (deterministic testing) |
| POST | `/api/emergency/dispatch` | Dispatch emergency vehicle |
| GET | `/api/network` | Static road network |
| GET | `/api/metrics` | Current evaluation metrics |
| GET | `/api/events` | Agent message event log |

---

## Configuration

All parameters are in `backend/config/network.json`. No hard-coded values in agent code.

Key configurable parameters:

```json
"simulation": {
  "tick_seconds": 1,
  "default_duration_seconds": 300,
  "initial_normal_vehicles": 30,
  "signal_cycle_seconds": 60,
  "normal_green_seconds": 30,
  "yellow_seconds": 5,
  "all_red_seconds": 2,
  "emergency_speed_kmh": 60,
  "random_seed": 42,
  "stale_message_timeout": 60,
  "replan_threshold": 0.20
},
"cost_weights": {
  "travel_time_weight": 0.50,
  "congestion_weight": 0.30,
  "waiting_time_weight": 0.20
}
```

---

## Evaluation Scenarios

| Scenario | Description |
|---|---|
| S0 | Normal traffic only — establishes baseline waiting and throughput |
| S1 | Emergency (ambulance) I1→I5, low congestion (10 vehicles) |
| S2 | Emergency (fire truck) I1→I5, high congestion (40 vehicles) |
| S3 | Emergency (police) I1→I3 — verifies A* alternative routes |
| S4 | Emergency I2→I5 with dynamic congestion — tests replanning |
| S5 | Emergency I1→I3 — verifies signal recovery after passage |

---

## Metrics

| Metric | Definition |
|---|---|
| Emergency travel time | `arrival_time − dispatch_time` |
| Emergency delay | `actual travel time − estimated free-flow travel time` |
| Average waiting time | `total_waiting_seconds / number_of_vehicles` |
| Throughput | `vehicles_completed / evaluation_period` |
| Route cost | `sum of edge_cost values along selected A* route` |

---

## Demo Scenario (Quick Start)

1. Start backend: `uvicorn backend.main:app --reload --port 8000`
2. Start frontend: `npm run dev` (in `frontend/`)
3. Open `http://localhost:5173`
4. Click **⚡ Demo: Emergency I1→I5** — this starts the simulation and dispatches an ambulance automatically
5. Watch the network map: signals on the route turn orange (PREPARE) then cyan (EMERGENCY_GREEN) sequentially
6. The red ambulance marker moves through the green corridor
7. Each passed signal turns purple (EMERGENCY_CLEAR) then returns to normal
8. Metrics update in the bottom-left panel

---

## Troubleshooting

**Backend won't start:**
- Check Python 3.11+ is installed: `python --version`
- Install dependencies: `pip install -r requirements.txt`
- Verify port 8000 is free

**Frontend shows "Connecting to backend…":**
- Backend must be running on port 8000 before starting the frontend
- Check CORS: backend allows `http://localhost:5173`

**Tests fail with import errors:**
- Run from the `traffic-signal-project/` directory
- Ensure `sys.path` includes the project root (handled automatically in test files)

**Emergency vehicle doesn't move:**
- Simulation must be in `running` state before dispatch
- Click Start first, then Dispatch

---

## Limitations

- Single emergency vehicle baseline (multiple EV extension defined but not the baseline scenario)
- Route replanning may cause brief re-entry to PREPARE on some TSAs (handled by duplicate guard)
- A\* documented as informed search strategy; formal optimality depends on traffic state consistency
- Vehicle routing uses BFS (shortest hops), not A\* (reserved for emergency vehicles per spec)
- Frontend polling interval is 500 ms; very fast simulations may appear to skip states

---

## AI Concept Mapping

| AI Concept | Where it appears |
|---|---|
| PEAS | Formal agent definitions (Section 6 of spec) |
| Multi-Agent Systems | 5 TSAs + Vehicle Agents + Emergency Vehicle Agent |
| Decentralised decision-making | Neighbour communication, local signal rules |
| Partially observable environment | Each TSA sees only its intersection + neighbour messages |
| A\* search | Emergency route planning |
| Heuristic search | f(n) = g(n) + h(n) |
| Rule-based reasoning | Emergency priority rules R1–R5, recovery schedule |
| Dynamic environment | Traffic and signal states change every tick |
| Sequential decision-making | Signal decisions affect later queue/travel conditions |
