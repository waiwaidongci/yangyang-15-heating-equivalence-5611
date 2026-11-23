export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, text => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[text]);
}

const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false,
});
export const timeLabel = value => value ? timeFormat.format(new Date(value)) : '—';
export const displayValue = value => value === null || value === undefined || value === '' ? '—' : value;

const metricFormat = new Intl.NumberFormat('zh-CN', {maximumSignificantDigits: 7});
export function formatMetric(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return value;
  if (value !== 0 && Math.abs(value) < 0.0001) return value.toExponential(3);
  return metricFormat.format(value);
}
