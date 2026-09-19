"""
End-to-end verification of the complete emergency scenario.
Checks every acceptance criterion from Section 30 of the specification.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.simulation.engine import SimulationEngine
from backend.simulation.network import RoadNetwork
from backend.communication.schemas import SignalState

PASS = "[PASS]"
FAIL = "[FAIL]"

def check(condition, label):
    icon = PASS if condition else FAIL
    print(f"{icon} {label}")
    return condition

results = []

print("=" * 60)
print("COMPLETE EMERGENCY SCENARIO END-TO-END VERIFICATION")
print("=" * 60)

net = RoadNetwork()
engine = SimulationEngine(net)

# --- Start normal traffic ---
engine.start("S1")
results.append(check(engine.status.value == "running", "Simulation starts in running state"))

# Run 5 ticks for initial traffic
for _ in range(5):
    engine.tick()
vehicles = engine.traffic.get_all_vehicles()
results.append(check(len(vehicles) > 0, f"Normal vehicles present: {len(vehicles)}"))

# --- TSA-to-TSA traffic exchange ---
events = engine.bus.get_event_log()
traffic_updates = [e for e in events if e["type"] == "TRAFFIC_UPDATE"]
results.append(check(len(traffic_updates) > 0, f"TSA traffic exchanges: {len(traffic_updates)} TRAFFIC_UPDATE msgs"))

# --- Dispatch emergency vehicle ---
ev = engine.dispatch_emergency("EV01", "I1", "I5", "ambulance")
results.append(check(ev is not None, "Emergency vehicle dispatched"))

if ev:
    # A* route
    results.append(check(len(ev.route) >= 2, f"A* route found: {' -> '.join(ev.route)}"))
    results.append(check(ev.route[0] == "I1", "Route starts at emergency vehicle current node (I1)"))
    results.append(check(ev.route[-1] == "I5", "Route ends at destination (I5)"))
    results.append(check(ev.route_cost > 0, f"Route cost computed: {ev.route_cost:.4f}"))

    # Validate route edges exist
    all_edges_valid = all(
        net.get_edge(ev.route[i], ev.route[i+1]) is not None
        for i in range(len(ev.route)-1)
    )
    results.append(check(all_edges_valid, "Route edges all valid in network"))

    # ETA map
    results.append(check(len(ev.eta_map) > 0, f"ETA map computed for {len(ev.eta_map)} intersections"))
    for iid, eta in ev.eta_map.items():
        if iid != ev.route[0]:
            results.append(check(eta > engine.current_time, f"ETA for {iid}: {eta:.1f}s (future)"))

# Flush first priority messages
for _ in range(8):
    engine.tick()

# Check emergency messages reached route TSAs
prio_events = [e for e in engine.bus.get_event_log() if e["type"] == "EMERGENCY_PRIORITY"]
results.append(check(len(prio_events) > 0, f"EMERGENCY_PRIORITY messages sent: {len(prio_events)}"))

forward_events = [e for e in engine.bus.get_event_log() if e["type"] == "ROUTE_FORWARD"]
results.append(check(len(forward_events) > 0, f"ROUTE_FORWARD chain: {len(forward_events)} msgs"))

# Check at least one route TSA in emergency state
if ev:
    emergency_states = {SignalState.EMERGENCY_PREPARE, SignalState.EMERGENCY_GREEN}
    on_route_states = []
    for iid in ev.route:
        aid = net.intersections[iid].signal_agent_id
        s = engine.tsa_agents[aid].get_signal_state_model().state
        on_route_states.append((iid, s))
    has_emergency = any(s in emergency_states for _, s in on_route_states)
    results.append(check(has_emergency, f"At least one route TSA in emergency state: {[(i,s.value) for i,s in on_route_states]}"))

    # Check off-route TSAs are normal
    off_route = [iid for iid in net.intersections if iid not in ev.route]
    normal_states = {SignalState.NORMAL_GREEN, SignalState.NORMAL_YELLOW, SignalState.NORMAL_RED}
    off_route_normal = all(
        engine.tsa_agents[net.intersections[iid].signal_agent_id].get_signal_state_model().state
        in normal_states
        for iid in off_route
    )
    results.append(check(off_route_normal, f"Off-route TSAs ({off_route}) stay in normal operation"))

    # Check green corridor NOT simultaneous
    eg_count = sum(1 for _, s in on_route_states if s == SignalState.EMERGENCY_GREEN)
    results.append(check(eg_count < len(ev.route), f"Green corridor is sequential (not all {len(ev.route)} signals green simultaneously, only {eg_count})"))

# --- Run until EV arrives ---
for _ in range(300):
    engine.tick()
    if ev and ev.arrival_time is not None:
        break

if ev:
    results.append(check(ev.arrival_time is not None, f"Emergency vehicle reached I5 at t={ev.arrival_time:.1f}s" if ev.arrival_time else "EV DID NOT ARRIVE"))
    if ev.arrival_time:
        travel_time = ev.arrival_time - ev.dispatch_time
        results.append(check(travel_time > 0, f"Travel time: {travel_time:.1f}s"))

# --- Run more ticks for recovery ---
for _ in range(30):
    engine.tick()

# Check recovery
if ev:
    recovered = []
    for iid in ev.route:
        aid = net.intersections[iid].signal_agent_id
        s = engine.tsa_agents[aid].get_signal_state_model().state
        in_normal = s in normal_states
        recovered.append(in_normal)
        print(f"       Recovery: {iid} ({aid}) -> {s.value}  {'OK' if in_normal else 'FAIL'}")
    results.append(check(all(recovered), "All route signals recovered to normal operation"))

# --- Duplicate/stale message handling ---
from backend.communication.message_bus import MessageBus
test_bus = MessageBus(stale_timeout=10.0)
received = []
test_bus.register_handler("TSA-X", received.append)
from backend.communication.schemas import AgentMessage, MessageType, EmergencyPriorityPayload, EmergencyPriority, VehicleType
msg = AgentMessage(
    type=MessageType.EMERGENCY_PRIORITY,
    sender_id="EV99",
    receiver_id="TSA-X",
    timestamp=0.0,
    payload=EmergencyPriorityPayload(
        emergency_id="EV99", route=["I1"], priority=EmergencyPriority.HIGH,
        eta_to_intersection={}, vehicle_type=VehicleType.AMBULANCE,
    ).model_dump(),
)
test_bus.post(msg)
test_bus.post(msg)  # duplicate
test_bus.flush(0.0)
results.append(check(len(received) == 1, "Duplicate messages do not cause duplicate actions"))

test_bus2 = MessageBus(stale_timeout=10.0)
received2 = []
test_bus2.register_handler("TSA-Y", received2.append)
stale_msg = AgentMessage(
    type=MessageType.EMERGENCY_PRIORITY,
    sender_id="EV88",
    receiver_id="TSA-Y",
    timestamp=0.0,
    payload=EmergencyPriorityPayload(
        emergency_id="EV88", route=["I1"], priority=EmergencyPriority.HIGH,
        eta_to_intersection={}, vehicle_type=VehicleType.AMBULANCE,
    ).model_dump(),
)
test_bus2.post(stale_msg)
test_bus2.flush(current_time=100.0)  # stale
results.append(check(len(received2) == 0, "Stale emergency messages are dropped"))

# --- Metrics ---
metrics = engine.metrics.get_metrics()
if ev and ev.arrival_time:
    results.append(check(metrics.emergency_travel_time > 0, f"Emergency travel time metric: {metrics.emergency_travel_time:.1f}s"))
results.append(check(metrics.average_waiting_time >= 0, f"Average waiting time: {metrics.average_waiting_time:.2f}s"))
results.append(check(metrics.throughput >= 0, f"Throughput: {metrics.throughput:.4f} v/s"))
if ev:
    results.append(check(metrics.route_cost > 0, f"Route cost metric: {metrics.route_cost:.4f}"))

# --- TSA decentralisation ---
tsa1 = engine.tsa_agents["TSA-1"]
tsa2 = engine.tsa_agents["TSA-2"]
results.append(check(tsa1._signal is not tsa2._signal, "TSA-1 and TSA-2 control separate signal objects"))

# --- A* unreachable test ---
from backend.algorithms.astar import AStarRouter
router = AStarRouter(net)
bad_route, bad_cost = router.find_route("I1", "IX_BAD")
results.append(check(bad_route is None and bad_cost == float("inf"), "A* returns None for unreachable destination"))

print()
print("=" * 60)
passed = sum(results)
total = len(results)
print(f"RESULTS: {passed}/{total} checks passed")
if passed == total:
    print("ALL ACCEPTANCE CRITERIA MET")
else:
    print(f"✗ {total - passed} checks failed")
print("=" * 60)
