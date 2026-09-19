/**
 * useSimulation – central React hook for simulation state management.
 *
 * Polls the backend /api/simulation/state every POLL_INTERVAL ms while running.
 * Exposes control functions: start, pause, reset, tick, dispatchEmergency.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client.js';

const POLL_INTERVAL = 500; // ms

const INITIAL_STATE = {
  status: 'idle',
  current_time: 0,
  tick: 0,
  intersections: {},
  edges: {},
  signals: {},
  vehicles: [],
  emergency_vehicles: [],
  metrics: {
    emergency_travel_time: 0,
    emergency_delay: 0,
    average_waiting_time: 0,
    throughput: 0,
    route_cost: 0,
    total_vehicles_completed: 0,
  },
  events: [],
};

export function useSimulation() {
  const [simState, setSimState] = useState(INITIAL_STATE);
  const [network, setNetwork] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef(null);
  const isRunningRef = useRef(false);

  // Load network on mount
  useEffect(() => {
    api.getNetwork()
      .then(setNetwork)
      .catch(e => setError('Backend not reachable: ' + e.message));
  }, []);

  // Polling
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await api.getState();
        setSimState(state);
        setError(null);
        if (state.status === 'completed' || state.status === 'idle') {
          stopPolling();
        }
      } catch (e) {
        setError('State fetch error: ' + e.message);
      }
    }, POLL_INTERVAL);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  // Control actions
  const startSimulation = useCallback(async (scenarioId = 'S1') => {
    setLoading(true);
    setError(null);
    try {
      await api.start(scenarioId);
      const state = await api.getState();
      setSimState(state);
      startPolling();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [startPolling]);

  const pauseSimulation = useCallback(async () => {
    try {
      await api.pause();
      const state = await api.getState();
      setSimState(state);
      if (state.status === 'paused') stopPolling();
      else startPolling();
    } catch (e) {
      setError(e.message);
    }
  }, [startPolling, stopPolling]);

  const resetSimulation = useCallback(async () => {
    stopPolling();
    try {
      await api.reset();
      setSimState(INITIAL_STATE);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [stopPolling]);

  const advanceTick = useCallback(async () => {
    try {
      await api.tick();
      const state = await api.getState();
      setSimState(state);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const dispatchEmergency = useCallback(async (params) => {
    setError(null);
    try {
      const result = await api.dispatch(params);
      const state = await api.getState();
      setSimState(state);
      return result;
    } catch (e) {
      setError(e.message);
      throw e;
    }
  }, []);

  return {
    simState,
    network,
    error,
    loading,
    startSimulation,
    pauseSimulation,
    resetSimulation,
    advanceTick,
    dispatchEmergency,
  };
}
