import React, { useState, useRef, useCallback } from 'react';
import './ControlPanel.css';

const TRAFFIC_PRESETS = [
  { id: 'S1', label: 'Low',     desc: '~18 vehicles' },
  { id: 'S2', label: 'High',    desc: '~55 vehicles' },
  { id: 'S4', label: 'Dynamic', desc: 'Congestion builds' },
];

const INTERSECTIONS = ['I1', 'I2', 'I3', 'I4', 'I5'];
const EV_TYPES      = ['ambulance', 'fire_truck', 'police'];

const STATUS_META = {
  idle:      { label: 'IDLE',    color: '#4a5278', bg: 'rgba(74,82,120,0.2)'   },
  running:   { label: 'RUNNING', color: '#22c55e', bg: 'rgba(34,197,94,0.15)'  },
  paused:    { label: 'PAUSED',  color: '#eab308', bg: 'rgba(234,179,8,0.15)'  },
  completed: { label: 'DONE',    color: '#a855f7', bg: 'rgba(168,85,247,0.15)' },
};

function useLongPress(callback, { initialDelay = 400, repeatInterval = 120 } = {}) {
  const holdRef    = useRef(null);
  const initialRef = useRef(null);
  const activeRef  = useRef(false);

  const start = useCallback((e) => {
    if (e.type === 'touchstart') e.preventDefault();
    if (activeRef.current) return;
    activeRef.current = true;
    callback();
    initialRef.current = setTimeout(() => {
      holdRef.current = setInterval(() => {
        if (activeRef.current) callback();
      }, repeatInterval);
    }, initialDelay);
  }, [callback, initialDelay, repeatInterval]);

  const stop = useCallback(() => {
    activeRef.current = false;
    clearTimeout(initialRef.current);
    clearInterval(holdRef.current);
  }, []);

  return {
    onMouseDown:   start,
    onMouseUp:     stop,
    onMouseLeave:  stop,
    onTouchStart:  start,
    onTouchEnd:    stop,
    onTouchCancel: stop,
    onClick:       (e) => e.preventDefault(),
  };
}

export default function ControlPanel({ simState, loading, onStart, onPause, onReset, onTick, onDispatch }) {
  const [intensity,   setIntensity]   = useState('S2');
  const [evId,        setEvId]        = useState('EV01');
  const [evType,      setEvType]      = useState('ambulance');
  const [evStart,     setEvStart]     = useState('I1');
  const [evDest,      setEvDest]      = useState('I5');
  const [dispatchMsg, setDispatchMsg] = useState(null);

  const status    = simState?.status || 'idle';
  const isRunning = status === 'running';
  const isPaused  = status === 'paused';
  const isIdle    = status === 'idle';
  const hasEV     = (simState?.emergency_vehicles || []).length > 0;
  const simTime   = simState?.current_time?.toFixed(1) ?? '0.0';
  const tickCount = simState?.tick ?? 0;
  const meta      = STATUS_META[status] || STATUS_META.idle;

  const tickDisabled       = loading || isIdle;
  const tickLongPressProps = useLongPress(onTick, { initialDelay: 350, repeatInterval: 100 });

  async function handleDispatch() {
    setDispatchMsg(null);
    try {
      const r = await onDispatch({
        emergency_id: evId,
        start_node:   evStart,
        destination:  evDest,
        vehicle_type: evType,
      });
      const route = (r.route || []).join(' -> ');
      setDispatchMsg({ ok: true, text: `Route: ${route}  |  Cost: ${r.route_cost?.toFixed(3)}` });
    } catch (e) {
      setDispatchMsg({ ok: false, text: e.message });
    }
  }

  return (
    <div className="cp">

      {/* Status strip */}
      <div className="cp-status" style={{ background: meta.bg, borderLeft: `3px solid ${meta.color}` }}>
        <span className="cp-status-badge" style={{ color: meta.color }}>{meta.label}</span>
        <span className="cp-status-time">T: {simTime}s</span>
        <span className="cp-status-tick">#{tickCount}</span>
      </div>

      {/* Traffic intensity */}
      <div className="cp-section">
        <div className="cp-section-label">Traffic Intensity</div>
        <div className="cp-intensity-row">
          {TRAFFIC_PRESETS.map(p => (
            <button
              key={p.id}
              className={`cp-intensity-btn ${intensity === p.id ? 'active' : ''}`}
              onClick={() => setIntensity(p.id)}
              disabled={isRunning || isPaused}
              title={p.desc}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="cp-intensity-hint">
          {TRAFFIC_PRESETS.find(p => p.id === intensity)?.desc}
          &nbsp;· dynamic seed each run
        </div>
      </div>

      {/* Simulation controls */}
      <div className="cp-section">
        <div className="cp-section-label">Simulation</div>
        <div className="cp-btn-grid">
          <button className="cp-btn cp-btn-start" onClick={() => onStart(intensity)} disabled={loading || isRunning || isPaused}>
            ▶ Start
          </button>
          <button className="cp-btn cp-btn-pause" onClick={onPause} disabled={loading || isIdle}>
            {isPaused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button className="cp-btn cp-btn-reset" onClick={onReset} disabled={loading}>
            ↺ Reset
          </button>
          <button
            className="cp-btn cp-btn-tick"
            disabled={tickDisabled}
            title="Click: one tick  |  Hold: continuous advance"
            {...(!tickDisabled ? tickLongPressProps : {})}
          >
            ⏭ Tick
          </button>
        </div>
      </div>

      {/* Emergency dispatch */}
      <div className="cp-section">
        <div className="cp-section-label">Emergency Dispatch</div>
        <div className="cp-form">
          <div className="cp-field-row">
            <div className="cp-field">
              <label className="cp-field-label">ID</label>
              <input type="text" value={evId} onChange={e => setEvId(e.target.value)} />
            </div>
            <div className="cp-field">
              <label className="cp-field-label">Type</label>
              <select value={evType} onChange={e => setEvType(e.target.value)}>
                {EV_TYPES.map(t => (
                  <option key={t} value={t}>
                    {t === 'fire_truck' ? 'Fire truck' : t.charAt(0).toUpperCase() + t.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="cp-field-row">
            <div className="cp-field">
              <label className="cp-field-label">From</label>
              <select value={evStart} onChange={e => setEvStart(e.target.value)}>
                {INTERSECTIONS.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
            <div className="cp-field">
              <label className="cp-field-label">To</label>
              <select value={evDest} onChange={e => setEvDest(e.target.value)}>
                {INTERSECTIONS.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
          </div>
        </div>

        <button
          className="cp-btn cp-btn-dispatch"
          onClick={handleDispatch}
          disabled={loading || isIdle || hasEV}
        >
          🚑 Dispatch Emergency
        </button>

        {dispatchMsg && (
          <div className={`cp-msg ${dispatchMsg.ok ? 'cp-msg-ok' : 'cp-msg-err'}`}>
            {dispatchMsg.ok ? '✓' : '✗'} {dispatchMsg.text}
          </div>
        )}
      </div>

    </div>
  );
}
