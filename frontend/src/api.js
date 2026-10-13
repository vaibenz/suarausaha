async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => request('/health'),
  entries: () => request('/entries'),
  summary: () => request('/summary'),
  recordText: (text) =>
    request('/entries/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  recordVoice: (blob) => {
    const form = new FormData();
    form.append('audio', blob, 'rekaman.webm');
    return request('/entries/voice', { method: 'POST', body: form });
  },
  undo: () => request('/entries/last', { method: 'DELETE' }),
};

export function rupiah(amount) {
  return 'Rp' + Math.round(amount).toLocaleString('id-ID');
}
