import React, { useRef, useEffect } from 'react';
import './EventLog.css';

const TYPE_META = {
  EMERGENCY_PRIORITY: { color: '#ef4444', short: 'PRIO'  },
  ROUTE_FORWARD:      { color: '#f97316', short: 'FWD'   },
  EMERGENCY_PASSED:   { color: '#a855f7', short: 'PASS'  },
  TRAFFIC_UPDATE:     { color: '#4a9eff', short: 'TRAF'  },
  SIGNAL_STATUS:      { color: '#22c55e', short: 'SIG'   },
  ACK:                { color: '#4a5278', short: 'ACK'   },
  STALE_MESSAGE:      { color: '#6b7280', short: 'STALE' },
};

function summarise(type, payload) {
  const p = payload || {};
  switch (type) {
    case 'EMERGENCY_PRIORITY': return `route: ${(p.route||[]).join('→')}`;
    case 'ROUTE_FORWARD':      return `next: ${p.next_intersection}  eta: ${p.eta?.toFixed(1)}s`;
    case 'TRAFFIC_UPDATE':     return `v=${p.vehicle_count} q=${p.queue_length} c=${p.congestion_ratio?.toFixed(2)}`;
    case 'EMERGENCY_PASSED':   return `cleared ${p.intersection_id}`;
    case 'ACK':                return 'ok';
    case 'STALE_MESSAGE':      return `age ${p.age?.toFixed(0)}s`;
    default:                   return '';
  }
}

export default function EventLog({ simState }) {
  const events = (simState?.events || []).slice(-80).reverse();
  const listRef = useRef(null);

  return (
    <div className="el panel">
      <div className="panel-header">
        <span className="panel-header-icon">📡</span>
        <span className="panel-header-title">Agent Event Log</span>
        <span className="el-count">{events.length}</span>
      </div>

      <div className="el-list" ref={listRef}>
        {events.length === 0 ? (
          <div className="el-empty">No events yet — start the simulation.</div>
        ) : (
          events.map((ev, i) => {
            const meta = TYPE_META[ev.type] || { color: '#7a85a8', short: ev.type };
            const t    = typeof ev.timestamp === 'number' ? ev.timestamp.toFixed(1) : '?';
            const sum  = summarise(ev.type, ev.payload);
            return (
              <div key={i} className="el-row">
                <span className="el-time">{t}s</span>
                <span className="el-tag" style={{ color: meta.color, borderColor: meta.color + '44', background: meta.color + '14' }}>
                  {meta.short}
                </span>
                <span className="el-agents">{ev.sender} › {ev.receiver}</span>
                {sum && <span className="el-detail">{sum}</span>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
