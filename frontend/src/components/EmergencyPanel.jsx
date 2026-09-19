import React from 'react';
import './EmergencyPanel.css';

export default function EmergencyPanel({ simState }) {
  const evs = simState?.emergency_vehicles || [];
  const ev  = evs[0] || null;

  return (
    <div className="ep panel">
      <div className="panel-header">
        <span className="panel-header-icon">🚑</span>
        <span className="panel-header-title">Emergency Vehicle</span>
        {ev && (
          <span className={`ep-badge ${ev.active ? 'ep-active' : 'ep-arrived'}`}>
            {ev.active ? 'ACTIVE' : 'ARRIVED'}
          </span>
        )}
      </div>

      {!ev ? (
        <div className="ep-empty">
          <span className="ep-empty-icon">🚑</span>
          <span>No emergency vehicle dispatched</span>
        </div>
      ) : (
        <div className="panel-body">

          {/* ID + type row */}
          <div className="ep-id-row">
            <span className="ep-id">{ev.id}</span>
            <span className="ep-type">{ev.type.replace('_', ' ')}</span>
          </div>

          {/* Details grid */}
          <div className="ep-section-label">Details</div>
          <div className="ep-kv">
            <KV label="From"     value={ev.route?.[0] || '—'} />
            <KV label="To"       value={ev.destination}        accent />
            <KV label="Location" value={ev.current_node || (ev.current_edge ? `${ev.current_edge} (${(ev.position*100).toFixed(0)}%)` : '—')} />
            <KV label="Speed"    value={`${ev.speed?.toFixed(0)} km/h`} />
            <KV label="Cost"     value={ev.route_cost?.toFixed(4)} />
            {ev.arrival_time != null && (
              <KV label="Travel" value={`${(ev.arrival_time - ev.dispatch_time).toFixed(1)}s`} accent />
            )}
          </div>

          {/* Route */}
          <div className="ep-section-label">A* Route</div>
          <div className="ep-route">
            {(ev.route || []).map((node, i) => (
              <React.Fragment key={node}>
                <span className={[
                  'ep-node',
                  ev.current_node === node ? 'ep-node-current' : '',
                  node === ev.destination   ? 'ep-node-dest'    : '',
                ].join(' ')}>
                  {node}
                </span>
                {i < ev.route.length - 1 && <span className="ep-arrow">›</span>}
              </React.Fragment>
            ))}
          </div>

          {/* ETA table */}
          {Object.keys(ev.eta_map || {}).length > 0 && (
            <>
              <div className="ep-section-label">ETA per Intersection</div>
              <table className="ep-table">
                <thead>
                  <tr>
                    <th>Node</th>
                    <th>ETA (s)</th>
                    <th>In (s)</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(ev.eta_map).sort((a,b) => a[1]-b[1]).map(([iid, eta]) => (
                    <tr key={iid} className={iid === ev.current_node ? 'ep-table-current' : ''}>
                      <td>{iid}</td>
                      <td>{eta.toFixed(1)}</td>
                      <td>{(eta - (simState?.current_time || 0)).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

        </div>
      )}
    </div>
  );
}

function KV({ label, value, accent }) {
  return (
    <div className="kv-row">
      <span className="kv-label">{label}</span>
      <span className={`kv-value${accent ? ' accent' : ''}`}>{value || '—'}</span>
    </div>
  );
}
