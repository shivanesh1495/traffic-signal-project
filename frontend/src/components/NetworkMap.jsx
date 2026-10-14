import React, { useMemo } from 'react';

/* ── Signal colour + short label ── */
const SIG_COLOR = {
  NORMAL_GREEN:      '#22c55e',
  NORMAL_YELLOW:     '#eab308',
  NORMAL_RED:        '#ef4444',
  EMERGENCY_PREPARE: '#f97316',
  EMERGENCY_GREEN:   '#06b6d4',
  EMERGENCY_CLEAR:   '#a855f7',
};
const SIG_SHORT = {
  NORMAL_GREEN:      'G',
  NORMAL_YELLOW:     'Y',
  NORMAL_RED:        'R',
  EMERGENCY_PREPARE: 'EP',
  EMERGENCY_GREEN:   'EG',
  EMERGENCY_CLEAR:   'EC',
};

/* ── Coordinate transform ──────────────────────────────────────
   Network coords: x 100–500, y 150–300
   SVG viewport  : 620 × 360
   Generous padding keeps every node label inside the frame.
──────────────────────────────────────────────────────────────── */
const VW  = 620;
const VH  = 360;
const PX  = 80;   // horizontal padding
const PY  = 56;   // vertical padding

function nx(x) { return PX + ((x - 100) / 400) * (VW - PX * 2); }
function ny(y) { return VH - PY - ((y - 140) / 170) * (VH - PY * 2); }

/* ── Legend items (bottom-right corner) ── */
const LEGEND = [
  { color: '#22c55e', label: 'Normal Green'   },
  { color: '#eab308', label: 'Yellow'          },
  { color: '#ef4444', label: 'Red'             },
  { color: '#f97316', label: 'Emerg. Prepare'  },
  { color: '#06b6d4', label: 'Emerg. Green'    },
  { color: '#a855f7', label: 'Recovery'        },
  { color: '#4a9eff', label: 'Emerg. Route'    },
  { color: '#ef4444', label: 'Emerg. Vehicle'  },
];

const LEG_W  = 128;
const LEG_RH = 15;   // row height
const LEG_H  = LEGEND.length * LEG_RH + 10;

/* ── Node circle sizes ── */
const R_OUTER = 20;   // outer ring
const R_FILL  = 12;   // signal colour fill
const R_PULSE = 28;   // emergency pulse ring

export default function NetworkMap({ simState, network }) {
  if (!network && !simState) {
    return (
      <div style={{
        display:'flex', alignItems:'center', justifyContent:'center',
        width:'100%', height:'100%', color:'#4a5278', fontSize:12,
      }}>
        Connecting to backend…
      </div>
    );
  }

  const liveIntersections = (simState?.intersections && Object.keys(simState.intersections).length > 0)
    ? simState.intersections
    : (network?.intersections || {});
  const liveEdges = (simState?.edges && Object.keys(simState.edges).length > 0)
    ? simState.edges
    : (network?.edges || {});

  const intersections = liveIntersections;
  const edges = liveEdges;
  const { signals = {}, vehicles = [], emergency_vehicles = [] } = simState || {};
  const ev = emergency_vehicles[0] || null;

  /* Emergency route directed edge set */
  const evRoute = useMemo(() => {
    const s = new Set();
    const r = ev?.route || [];
    for (let i = 0; i < r.length - 1; i++) s.add(`${r[i]}|${r[i+1]}`);
    return s;
  }, [ev]);

  /* Ordinary vehicle dot positions */
  const vehDots = useMemo(() =>
    vehicles.flatMap(v => {
      if (!v.current_edge) return [];
      const e = edges[v.current_edge];
      if (!e) return [];
      const a = intersections[e.from_node], b = intersections[e.to_node];
      if (!a || !b) return [];
      const t = v.position;
      return [{ id: v.id, waiting: v.waiting,
        x: nx(a.x) + (nx(b.x) - nx(a.x)) * t,
        y: ny(a.y) + (ny(b.y) - ny(a.y)) * t }];
    }),
  [vehicles, edges, intersections]);

  /* Emergency vehicle position */
  const evPos = useMemo(() => {
    if (!ev) return null;
    if (ev.current_edge) {
      const e = edges[ev.current_edge];
      if (e) {
        const a = intersections[e.from_node], b = intersections[e.to_node];
        if (a && b) {
          const t = ev.position;
          return { x: nx(a.x)+(nx(b.x)-nx(a.x))*t, y: ny(a.y)+(ny(b.y)-ny(a.y))*t };
        }
      }
    }
    if (ev.current_node && intersections[ev.current_node]) {
      const n = intersections[ev.current_node];
      return { x: nx(n.x), y: ny(n.y) };
    }
    return null;
  }, [ev, edges, intersections]);

  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width:'100%', height:'100%', display:'block', background:'#ffffff' }}
    >
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.5" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="glow-sm" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="1.8" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <radialGradient id="nm-bg" cx="50%" cy="50%" r="70%">
          <stop offset="0%"   stopColor="#ffffff"/>
          <stop offset="100%" stopColor="#f4f4f4"/>
        </radialGradient>
        <marker id="arr" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <path d="M0,0 L0,5 L5,2.5 z" fill="#b00020"/>
        </marker>
        <marker id="arr-em" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <path d="M0,0 L0,5 L5,2.5 z" fill="#b00020aa"/>
        </marker>
      </defs>

      {/* Background */}
      <rect width={VW} height={VH} fill="url(#nm-bg)"/>

      {/* Subtle dot grid */}
      {Array.from({length:9},(_,i) => Array.from({length:6},(_,j) => (
        <circle key={`d${i}-${j}`} cx={50+i*66} cy={30+j*60} r={0.8} fill="#dddddd"/>
      )))}

      {/* ── Road edges ── */}
      {Object.values(edges).map(edge => {
        const a = intersections[edge.from_node];
        const b = intersections[edge.to_node];
        if (!a || !b) return null;
        const isEmg  = evRoute.has(`${edge.from_node}|${edge.to_node}`);
        const cong   = Math.min(1, edge.congestion_ratio || 0);
        const roadCol = isEmg
          ? '#4a9eff'
          : `rgb(${28+Math.round(cong*36)},${32+Math.round(cong*8)},56)`;
        const ax = nx(a.x), ay = ny(a.y), bx = nx(b.x), by = ny(b.y);

        return (
          <g key={edge.id}>
            {/* Glow halo on emergency route */}
            {isEmg && (
              <line x1={ax} y1={ay} x2={bx} y2={by}
                stroke="rgba(74,158,255,0.18)" strokeWidth={12} strokeLinecap="round"/>
            )}
            {/* Road shadow */}
            <line x1={ax} y1={ay} x2={bx} y2={by}
              stroke="rgba(0,0,0,0.45)" strokeWidth={isEmg ? 7 : 6} strokeLinecap="round"/>
            {/* Road surface */}
            <line x1={ax} y1={ay} x2={bx} y2={by}
              stroke={roadCol} strokeWidth={isEmg ? 3 : 2}
              strokeLinecap="round"
              filter={isEmg ? 'url(#glow-sm)' : undefined}
              markerEnd={isEmg ? 'url(#arr-em)' : 'url(#arr)'}
            />
          </g>
        );
      })}

      {/* ── Ordinary vehicle dots ── */}
      {vehDots.map(v => (
        <circle key={v.id} cx={v.x} cy={v.y} r={3.5}
          fill={v.waiting ? 'rgba(234,179,8,0.6)' : 'rgba(74,158,255,0.55)'}
          stroke={v.waiting ? '#eab308' : '#4a9eff'} strokeWidth={0.8}/>
      ))}

      {/* ── Intersection nodes ── */}
      {Object.values(intersections).map(node => {
        const sig     = signals[node.id];
        const state   = sig?.state || 'NORMAL_RED';
        const color   = SIG_COLOR[state] || '#4a5278';
        const letter  = SIG_SHORT[state]  || '?';
        const isEmg   = state.startsWith('EMERGENCY');
        const onRoute = (ev?.route || []).includes(node.id);
        const x = nx(node.x), y = ny(node.y);
        const phaseRem = sig?.phase_remaining != null ? `${sig.phase_remaining.toFixed(0)}s` : '';

        // Queue from approaching edges
        const queueSum = Object.values(edges || {})
          .filter(e => e.to_node === node.id)
          .reduce((s, e) => s + (e.queue_length || 0), 0);

        return (
          <g key={node.id}>
            {/* Pulse ring — only in emergency states or on route */}
            {(isEmg || onRoute) && (
              <circle cx={x} cy={y} r={R_PULSE}
                fill="none" stroke={color} strokeWidth={1.2}
                opacity={0.22} filter="url(#glow)"/>
            )}

            {/* Outer ring (dark background) */}
            <circle cx={x} cy={y} r={R_OUTER}
              fill="#ffffff" stroke={color} strokeWidth={2}
              filter={isEmg ? 'url(#glow-sm)' : undefined}/>

            {/* Signal colour fill */}
            <circle cx={x} cy={y} r={R_FILL} fill={color} opacity={0.92}/>

            {/* State letter — centred inside fill circle */}
            <text x={x} y={y + 4}
              textAnchor="middle" dominantBaseline="auto"
              fill="#060810" fontSize="9" fontWeight="900"
              fontFamily="var(--font-mono,monospace)">
              {letter}
            </text>

            {/* ── Labels — all placed at fixed offsets, no overlap ── */}

            {/* Intersection ID — directly above outer ring */}
            <text x={x} y={y - R_OUTER - 8}
              textAnchor="middle"
              fill="#111111" fontSize="11" fontWeight="700"
              fontFamily="var(--font-sans,-apple-system,sans-serif)">
              {node.id}
            </text>

            {/* Agent ID — one line further above */}
            <text x={x} y={y - R_OUTER - 20}
              textAnchor="middle"
              fill="#555555" fontSize="8"
              fontFamily="var(--font-sans,-apple-system,sans-serif)">
              {node.signal_agent_id}
            </text>

            {/* Phase remaining — directly below outer ring */}
            {phaseRem && (
              <text x={x} y={y + R_OUTER + 12}
                textAnchor="middle"
                fill="#555555" fontSize="8"
                fontFamily="var(--font-mono,monospace)">
                {phaseRem}
              </text>
            )}

            {/* Queue count — to the right of the ring, only when > 0 */}
            {queueSum > 0 && (
              <g transform={`translate(${x + R_OUTER + 4}, ${y - 5})`}>
                <rect x={0} y={0} width={26} height={12} rx={3}
                  fill="rgba(234,179,8,0.18)" stroke="#eab30855" strokeWidth={0.8}/>
                <text x={13} y={9}
                  textAnchor="middle"
                  fill="#eab308" fontSize="8" fontWeight="700"
                  fontFamily="var(--font-mono,monospace)">
                  Q:{queueSum}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* ── Emergency Vehicle marker ── */}
      {evPos && ev && (
        <g>
          <circle cx={evPos.x} cy={evPos.y} r={16}
            fill="rgba(239,68,68,0.14)" filter="url(#glow)"/>
          <circle cx={evPos.x} cy={evPos.y} r={9}
            fill="#ef4444" stroke="#fca5a5" strokeWidth={1.5}
            filter="url(#glow-sm)"/>
          <text x={evPos.x} y={evPos.y + 3.5}
            textAnchor="middle"
            fill="white" fontSize="7" fontWeight="900"
            fontFamily="var(--font-mono,monospace)">
            EV
          </text>
          {/* ID label below marker */}
          <text x={evPos.x} y={evPos.y + 24}
            textAnchor="middle"
            fill="#fca5a5" fontSize="8" fontWeight="700"
            fontFamily="var(--font-sans,-apple-system,sans-serif)">
            {ev.id}
          </text>
        </g>
      )}

      {/* ── Legend — bottom-right corner, no network overlap ── */}
      <g transform={`translate(${VW - LEG_W - 8}, ${VH - LEG_H - 8})`}>
        <rect width={LEG_W} height={LEG_H} rx="5"
          fill="rgba(255,255,255,0.95)" stroke="#b00020" strokeWidth={1}/>
        {LEGEND.map((item, i) => (
          <g key={item.label} transform={`translate(7, ${6 + i * LEG_RH})`}>
            <circle cx={4.5} cy={4.5} r={3.8} fill={item.color}/>
            <text x={13} y={8.5}
              fill="#5a6380" fontSize="8.5"
              fontFamily="var(--font-sans,-apple-system,sans-serif)">
              {item.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
