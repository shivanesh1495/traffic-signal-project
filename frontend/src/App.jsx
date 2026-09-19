import React from 'react';
import { useSimulation } from './hooks/useSimulation.js';
import NetworkMap     from './components/NetworkMap.jsx';
import ControlPanel   from './components/ControlPanel.jsx';
import EmergencyPanel from './components/EmergencyPanel.jsx';
import MetricsPanel   from './components/MetricsPanel.jsx';
import EventLog       from './components/EventLog.jsx';
import SignalGrid      from './components/SignalGrid.jsx';
import './App.css';

export default function App() {
  const {
    simState, network, error, loading,
    startSimulation, pauseSimulation,
    resetSimulation, advanceTick, dispatchEmergency,
  } = useSimulation();

  return (
    <div className="app">

      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-brand">
          <span className="header-icon">🚦</span>
          <span className="header-title">Multi-Agent Traffic Signal System</span>
        </div>

        <div className="header-divider" />
        <span className="header-subtitle">Emergency Vehicle Priority – Decentralised Multi-Agent AI</span>

        {error && <div className="header-error">⚠ {error}</div>}

        <div className="header-tags">
          <span className="header-tag">5 TSAs</span>
          <span className="header-tag">A* Routing</span>
          <span className="header-tag">Green Corridor</span>
        </div>
      </header>

      {/* ── Body ── */}
      <main className="app-body">

        <aside className="body-left">
          <ControlPanel
            simState={simState}
            loading={loading}
            onStart={startSimulation}
            onPause={pauseSimulation}
            onReset={resetSimulation}
            onTick={advanceTick}
            onDispatch={dispatchEmergency}
          />
        </aside>

        <section className="body-center">
          <div className="map-wrapper">
            <NetworkMap simState={simState} network={network} />
          </div>
        </section>

        <aside className="body-right">
          <EmergencyPanel simState={simState} />
          <MetricsPanel   simState={simState} />
        </aside>

      </main>

      {/* ── Footer ── */}
      <footer className="app-footer">
        <SignalGrid simState={simState} network={network} />
        <EventLog   simState={simState} />
      </footer>

    </div>
  );
}
