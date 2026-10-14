import React from 'react';
import { useSimulation } from './hooks/useSimulation.js';
import NetworkMap     from './components/NetworkMap.jsx';
import ControlPanel   from './components/ControlPanel.jsx';
import EventLog       from './components/EventLog.jsx';
import SignalGrid     from './components/SignalGrid.jsx';
import './App.css';

export default function App() {
  const {
    simState, network, loading,
    startSimulation, pauseSimulation,
    resetSimulation, advanceTick, dispatchEmergency,
  } = useSimulation();

  return (
    <div className="app">

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

      </main>

      {/* ── Footer ── */}
      <footer className="app-footer">
        <SignalGrid simState={simState} network={network} />
        <EventLog   simState={simState} />
      </footer>

    </div>
  );
}
