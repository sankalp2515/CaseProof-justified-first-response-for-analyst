// Indian-locale money and IST time helpers.
export function inr(n, { decimals = false, sign = false } = {}) {
  const neg = n < 0;
  const abs = Math.abs(n);
  const [int, dec] = abs.toFixed(2).split('.');
  let out;
  if (int.length <= 3) out = int;
  else {
    const last3 = int.slice(-3);
    const rest = int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
    out = `${rest},${last3}`;
  }
  const s = `₹${out}${decimals ? '.' + dec : ''}`;
  if (neg) return `−${s}`;
  return sign ? `+${s}` : s;
}

export function lakh(n) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  return inr(n);
}

const IST_OFFSET = 5.5 * 3600 * 1000;
const ist = (ms) => new Date(ms + IST_OFFSET);
const p2 = (n) => String(n).padStart(2, '0');

export function hms(ms) {
  const d = ist(ms);
  return `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`;
}
export function hm(ms) {
  const d = ist(ms);
  return `${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
}
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function dayLabel(ms) {
  const d = ist(ms);
  return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}
export function dateLong(ms) {
  const d = ist(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function countdown(ms) {
  if (ms <= 0) return '00:00';
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${p2(m)}:${p2(sec)}` : `${p2(m)}:${p2(sec)}`;
}

export function ago(ms) {
  const m = Math.round(ms / 60000);
  if (m < 1) return 'now';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

// Build an IST timestamp on the demo day (12 Mar 2026).
export const T = (h, m = 0, s = 0) => Date.UTC(2026, 2, 12, h, m, s) - IST_OFFSET;

export const cx = (...a) => a.filter(Boolean).join(' ');
