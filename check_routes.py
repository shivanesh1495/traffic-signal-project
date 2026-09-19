import sys
sys.path.insert(0, '.')
from backend.simulation.engine import SimulationEngine
from backend.simulation.network import RoadNetwork

print('=== Route variation across 6 independent runs (S2 high congestion) ===')
routes = []
for i in range(6):
    net = RoadNetwork()
    engine = SimulationEngine(net)
    engine.start('S2')
    for _ in range(12):
        engine.tick()
    ev = engine.dispatch_emergency('EV01', 'I1', 'I5', 'ambulance')
    if ev:
        r = ' -> '.join(ev.route)
        routes.append(r)
        # Show edge costs on both candidate paths
        c_direct = net.route_cost(['I1','I4','I5'])
        c_via_i2 = net.route_cost(['I1','I2','I3','I5'])
        c_via_i2b = net.route_cost(['I1','I2','I4','I5'])
        print(f'Run {i+1}: {r}  cost={ev.route_cost:.4f}')
        print(f'         I1->I4->I5: {c_direct:.4f}  |  I1->I2->I3->I5: {c_via_i2:.4f}  |  I1->I2->I4->I5: {c_via_i2b:.4f}')
    del engine, net

print()
unique = set(routes)
print(f'Unique routes: {len(unique)} of {len(routes)} runs')
for r in unique:
    print(f'  {r}  (x{routes.count(r)})')

print()
print('=== S3 (hotspot I4) – I1 to I3 ===')
routes3 = []
for i in range(6):
    net = RoadNetwork()
    engine = SimulationEngine(net)
    engine.start('S3')
    for _ in range(12):
        engine.tick()
    ev = engine.dispatch_emergency('EV01', 'I1', 'I3', 'police')
    if ev:
        r = ' -> '.join(ev.route)
        routes3.append(r)
        c1 = net.route_cost(['I1','I2','I3'])
        c2 = net.route_cost(['I1','I4','I2','I3'])
        print(f'Run {i+1}: {r}  cost={ev.route_cost:.4f}  | direct:{c1:.4f} via_I4:{c2:.4f}')
    del engine, net
unique3 = set(routes3)
print(f'Unique routes S3: {len(unique3)} of {len(routes3)} runs')
for r in unique3:
    print(f'  {r}  (x{routes3.count(r)})')
