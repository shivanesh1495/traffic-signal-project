import React from 'react';
import './SignalGrid.css';

const SIG_COLOR = {
  NORMAL_GREEN:      { text: '#22c55e', bg: 'rgba(34,197,94,0.15)'  },
  NORMAL_YELLOW:     { text: '#eab308', bg: 'rgba(234,179,8,0.15)'  },
  NORMAL_RED:        { text: '#ef4444', bg: 'rgba(239,68,68,0.15)'  },
  EMERGENCY_PREPARE: { text: '#f97316', bg: 'rgba(249,115,22,0.15)' },
  EMERGENCY_GREEN:   { text: '#06b6d4', bg: 'rgba(6,182,212,0.15)'  },
  EMERGENCY_CLEAR:   { text: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
};

const SIG_LABEL = {
  NORMAL_GREEN:      'Normal Green',
  NORMAL_YELLOW:     'Yellow',
  NORMAL_RED:        'Red',
  EMERGENCY_PREPARE: 'Emerg. Prepare',
  EMERGENCY_GREEN:   'Emerg. Green',
  EMERGENCY_CLEAR:   'Recovery',
};

export default function SignalGrid({ simState, network }) {
  if (!network && !simState) return null;

  const liveIntersections = (simState?.intersections && Object.keys(simState.intersections).length > 0)
    ? simState.intersections
    : (network?.intersections || {});
  const liveEdges = (simState?.edges && Object.keys(simState.edges).length > 0)
    ? simState.edges
    : (network?.edges || {});

  const intersections = liveIntersections;
  const edges = liveEdges;
  const signals = simState?.signals || {};

  const rows = Object.values(intersections || {}).map(node => {
    const sig   = signals[node.id] || {};
    const state = sig.state || 'NORMAL_RED';
    const meta  = SIG_COLOR[state] || { text: '#7a85a8', bg: 'transparent' };

    const approach = Object.values(edges || {}).filter(e => e.to_node === node.id);
    const vehicles = approach.reduce((s, e) => s + (e.vehicle_count || 0), 0);
    const queued   = approach.reduce((s, e) => s + (e.queue_length  || 0), 0);
    const cong     = approach.length > 0
      ? approach.reduce((s, e) => s + (e.congestion_ratio || 0), 0) / approach.length
      : 0;

    return { node, sig, state, meta, vehicles, queued, cong };
  });

  return (
    <div className="sg panel">
      <div className="panel-header">
        <span className="panel-header-icon">🚦</span>
        <span className="panel-header-title">Signal States</span>
      </div>

      <div className="sg-table-wrap">
        <table className="sg-table">
          <thead>
            <tr>
              <th>Node</th>
              <th>Agent</th>
              <th>State</th>
              <th>Rem.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ node, sig, state, meta }) => (
              <tr key={node.id} className={state.startsWith('EMERGENCY') ? 'sg-emg-row' : ''}>
                <td className="sg-node">{node.id}</td>
                <td className="sg-agent">{node.signal_agent_id}</td>
                <td>
                  <span
                    className="sg-badge"
                    style={{ color: meta.text, background: meta.bg, borderColor: meta.text + '55' }}
                  >
                    {SIG_LABEL[state] || state}
                  </span>
                </td>
                <td className="sg-mono">{sig.phase_remaining?.toFixed(0) ?? '—'}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
