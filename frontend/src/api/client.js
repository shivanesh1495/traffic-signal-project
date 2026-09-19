/**
 * API client for the FastAPI backend.
 * All functions interact with the actual simulation state.
 */

const BASE_URL = 'http://localhost:8000/api';

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE_URL}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Simulation control
  start: (scenarioId = 'S1') => request('POST', '/simulation/start', { scenario_id: scenarioId }),
  pause: () => request('POST', '/simulation/pause'),
  reset: () => request('POST', '/simulation/reset'),
  getState: () => request('GET', '/simulation/state'),
  tick: () => request('POST', '/simulation/tick'),

  // Emergency
  dispatch: (params) => request('POST', '/emergency/dispatch', params),

  // Network
  getNetwork: () => request('GET', '/network'),

  // Metrics
  getMetrics: () => request('GET', '/metrics'),

  // Events
  getEvents: () => request('GET', '/events'),
};
