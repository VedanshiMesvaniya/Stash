export async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const error = new Error((payload && payload.detail) || (payload && payload.error) || response.statusText);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

export const money = (value, currency = 'INR') =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));

export const shortDate = (value) =>
  new Intl.DateTimeFormat('en-IN', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value));

export const dayLabel = (value) => {
  const d = new Date(value);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const normalized = new Date(d);
  normalized.setHours(0, 0, 0, 0);
  if (normalized.getTime() === today.getTime()) return 'Today';
  if (normalized.getTime() === yesterday.getTime()) return 'Yesterday';
  return new Intl.DateTimeFormat('en-IN', { month: 'long', day: 'numeric' }).format(d);
};

export const toDateInput = (value) => {
  if (!value) return '';
  const d = new Date(value);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const fromDateInput = (value) => value || new Date().toISOString().slice(0, 10);

export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
