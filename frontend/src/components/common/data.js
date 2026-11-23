import { esc, displayValue, formatMetric } from '../../utils/html.js';
import { statusName } from '../../constants/enums.js';

export const empty = content => `<div class="empty">${esc(content)}</div>`;

export function table(columns, rows, content = '当前没有记录') {
  if (!rows.length) return empty(content);
  return `<div class="table-wrap" tabindex="0" role="region" aria-label="可滚动明细表"><table><thead><tr>${columns.map(col => `<th scope="col">${esc(col.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(col => `<td>${col.html ? col.html(row) : esc(displayValue(row[col.key]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

export function status(run) {
  const key = run.review?.decision || run.status;
  return `<span class="status status-${esc(key)}">${esc(statusName[key] || key)}</span>`;
}

export function bars(chart) {
  if (!chart?.points?.length) return '';
  const points = chart.points.filter(point => typeof point.value === 'number' && Number.isFinite(point.value)).slice(0, 14);
  if (!points.length) return '';
  const signed = points.some(point => point.value < 0);
  const highest = Math.max(...points.map(point => Math.abs(point.value))) || 1;
  return `<figure class="bars"><figcaption>${esc(chart.label)}${chart.unit ? ` <span>${esc(chart.unit)}</span>` : ''}</figcaption>${points.map(point => {
    const width = Math.abs(point.value) / highest * (signed ? 50 : 100);
    const left = point.value < 0 ? 50 - width : signed ? 50 : 0;
    return `<div class="bar-row"><span>${esc(point.label)}</span><i class="bar-track${signed ? ' bar-signed' : ''}" aria-hidden="true"><i class="bar-fill${point.value < 0 ? ' bar-negative' : ''}" style="--left:${left}%;--width:${width}%"></i></i><b>${esc(formatMetric(point.value))}</b></div>`;
  }).join('')}</figure>`;
}
