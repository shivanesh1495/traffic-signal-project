import React from 'react';
import './MetricsPanel.css';

function Row({ label, value, unit, highlight, color }) {
  const display = typeof value === 'number'
    ? (Number.isInteger(value) ? value : value.toFixed(2))
    : (value || '—');
  return (
    <div className={`mp-row${highlight ? ' mp-row-hl' : ''}`}>
      <span className="mp-label">{label}</span>
      <span className="mp-value" style={color ? { color } : undefined}>
        {display}
        {unit && <span className="mp-unit"> {unit}</span>}
      </span>
    </div>
  );
}

export default function MetricsPanel({ simState }) {
  const m   = simState?.metrics   || {};
  const st  = simState?.status    || 'idle';
  const t   = simState?.current_time || 0;
  const veh = simState?.vehicles?.length || 0;

  return (
    <div className="mp panel">
      <div className="panel-header">
        <span className="panel-header-icon">📊</span>
        <span className="panel-header-title">Metrics</span>
      </div>

      <div className="panel-body">

        <div className="mp-section">
          <div className="mp-section-label">Emergency</div>
          <Row label="Travel time"        value={m.emergency_travel_time} unit="s"   highlight color="#4a9eff" />
          <Row label="Delay vs free-flow" value={m.emergency_delay}       unit="s"   color="#f97316" />
          <Row label="Route cost"         value={m.route_cost}                        highlight color="#4a9eff" />
        </div>

        <div className="mp-section">
          <div className="mp-section-label">Traffic</div>
          <Row label="Avg waiting"   value={m.average_waiting_time}     unit="s" />
          <Row label="Throughput"    value={m.throughput}               unit="v/s" />
          <Row label="Vehicles done" value={m.total_vehicles_completed} />
          <Row label="Active now"    value={veh} />
        </div>

        <div className="mp-section">
          <div className="mp-section-label">Simulation</div>
          <Row label="Sim time" value={parseFloat(t.toFixed(1))} unit="s" />
          <Row label="Status"   value={st} />
        </div>

      </div>
    </div>
  );
}
