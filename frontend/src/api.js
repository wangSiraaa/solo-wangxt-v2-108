const BASE = '/api';

async function req(path, options) {
  const r = await fetch(BASE + path, options);
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch (_) { /* ignore */ }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return r.json();
}

export const api = {
  listBatches: () => req('/batches'),
  batchDetail: (id, { rorWindow, maxGap } = {}) => {
    const q = new URLSearchParams();
    if (rorWindow) q.set('ror_window_s', rorWindow);
    if (maxGap != null) q.set('max_interp_gap_s', maxGap);
    const qs = q.toString();
    return req(`/batches/${id}${qs ? `?${qs}` : ''}`);
  },
  compare: (a, b, { rorWindow, maxGap } = {}) => {
    const q = new URLSearchParams({ a, b });
    if (rorWindow) q.set('ror_window_s', rorWindow);
    if (maxGap != null) q.set('max_interp_gap_s', maxGap);
    return req(`/compare?${q.toString()}`);
  },
  addEvent: (batchId, body) =>
    req(`/batches/${batchId}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  acceptSuggestion: (eventId, operator) =>
    req(`/events/${eventId}/accept-suggestion?operator=${encodeURIComponent(operator)}`,
      { method: 'POST' }),
  revertEvent: (eventId, operator) =>
    req(`/events/${eventId}/revert?operator=${encodeURIComponent(operator)}`,
      { method: 'POST' }),
};

export function downloadUrl(batchId, kind) {
  return `${BASE}/batches/${batchId}/export/${kind}`;
}
