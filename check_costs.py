import sys
sys.path.insert(0, '.')
from backend.simulation.network import RoadNetwork
net = RoadNetwork()

routes = [
    ['I1','I2','I3','I5'],
    ['I1','I4','I5'],
    ['I1','I2','I4','I5'],
]

print('Free-flow costs (zero traffic):')
for r in routes:
    valid = all(net.get_edge(r[i], r[i+1]) for i in range(len(r)-1))
    if not valid:
        continue
    cost = net.route_cost(r)
    ff   = sum(net.free_flow_time(r[i], r[i+1]) for i in range(len(r)-1))
    route_str = ' -> '.join(r)
    print(f'  {route_str}: cost={cost:.4f}  free_flow={ff:.1f}s')
    for i in range(len(r)-1):
        e = net.get_edge(r[i], r[i+1])
        ff_seg = net.free_flow_time(r[i], r[i+1])
        edge_str = r[i] + '->' + r[i+1]
        print(f'    {edge_str}: len={e.length}m  spd={e.speed_limit}  ff={ff_seg:.1f}s')
