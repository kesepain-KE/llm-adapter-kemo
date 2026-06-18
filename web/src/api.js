const BASE = '/api';

export async function apiRequest(path, options = {}) {
  const response = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  }

  return response.json();
}
