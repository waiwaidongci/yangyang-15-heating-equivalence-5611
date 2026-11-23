import { download, get, post } from '../api/client.js';
import { bars, status, table } from '../components/common/data.js';
import { intro } from '../components/common/frame.js';
import { formError } from '../components/common/forms.js';
import { Decision, Role, RunStatus } from '../constants/enums.js';
import { bindDownloads, bindForm, notify } from '../hooks/actions.js';
import { esc, formatMetric, timeLabel } from '../utils/html.js';
import { runTable } from './analysis.js';

export async function resultPage(spec, user, route) {
  if (!route.id) {
    const runs = await get('/runs');
    return `${intro('结果与复核', spec.decision_prompt)}<section class="panel"><div class="panel-heading"><h2>选择分析结果</h2></div>${runTable(runs, '暂无结果。分析员可先在「分析任务」提交计算。')}</section>`;
  }
  const id = Number(route.id);
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error('分析编号无效');
  const run = await get(`/runs/${id}`);
  const head = intro(run.title, `${run.sample_size} 条观测 · 快照末号 ${run.snapshot_id} · ${timeLabel(run.created_at)}`, status(run));
  if (run.status === RunStatus.QUEUED) return `${head}<div class="empty" data-pending="${id}">分析任务已入队，正在等待计算。此页会自动刷新。</div>`;
  if (run.status === RunStatus.FAILED) return `${head}<div class="empty" role="alert">${esc(run.error)} <a href="#analysis">调整条件并重新计算</a></div>`;
  const data = run.result;
  let review = '<p>等待复核负责人签核。签核后也可由只读角色查看。</p>';
  if (run.review) review = `<p><b>${run.review.decision === Decision.APPROVED ? '签核通过' : '退回补充'}</b> ${esc(run.review.note)}</p><small>${esc(run.review.reviewer)} · ${timeLabel(run.review.at)}</small>`;
  if (!run.review && user.role === Role.SUPERVISOR) review = `<form id="review-form" data-id="${id}"><label class="field"><span>复核结论</span><select name="decision"><option value="approved">签核通过</option><option value="returned">退回补充</option></select></label><label class="field"><span>复核依据</span><textarea name="note" required minlength="2" maxlength="1000" placeholder="${esc(spec.decision_prompt)}"></textarea></label>${formError}<button class="primary">保存复核</button></form>`;
  const parameters = spec.parameters.map(field => `<li><span>${esc(field.label)}</span><b>${esc(run.parameters[field.key])}</b></li>`).join('');
  return `${head}<div class="split result-summary"><section class="conclusion"><h2>${esc(data.headline)}</h2><p>${esc(data.summary)}</p>${data.metrics.length ? `<dl class="metrics">${data.metrics.map(metric => `<div><dt>${esc(metric.label)}</dt><dd>${esc(formatMetric(metric.value))}${metric.unit ? `<small> ${esc(metric.unit)}</small>` : ''}</dd></div>`).join('')}</dl>` : ''}</section><aside class="method"><h2>本次条件</h2><ul class="parameters">${parameters}</ul>${bars(data.chart)}</aside></div>
    <section class="panel"><div class="panel-heading"><h2>计算明细</h2><button data-download="/runs/${id}/export">下载 CSV</button></div>${table(data.columns,data.rows,'当前参数下无明细，计算结论保留。')}</section>
    <section class="panel"><div class="panel-heading"><h2>业务签核</h2>${run.review?.decision === Decision.APPROVED ? '<a href="#reports">查看分发 →</a>' : ''}</div><div class="panel-body">${review}</div></section>`;
}

export function wireResult(root, refresh) {
  bindDownloads(root, download);
  bindForm(root.querySelector('#review-form'), async form => {
    await post(`/runs/${form.dataset.id}/review`,Object.fromEntries(new FormData(form)));
    notify('复核记录已保存');
    refresh();
  });
  const pending = root.querySelector('[data-pending]');
  if (pending) setTimeout(() => {
    if (pending.isConnected && location.hash === `#result/${pending.dataset.pending}`) refresh();
  }, 800);
}
