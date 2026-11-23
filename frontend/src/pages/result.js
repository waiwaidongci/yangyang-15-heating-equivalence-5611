import { download, get, post } from '../api/client.js';
import { bars, status, table } from '../components/common/data.js';
import { intro } from '../components/common/frame.js';
import { formError } from '../components/common/forms.js';
import { Decision, Role, RunStatus } from '../constants/enums.js';
import { bindDownloads, bindForm, notify } from '../hooks/actions.js';
import { esc, formatMetric, timeLabel } from '../utils/html.js';
import { runTable } from './analysis.js';

function configurationPanel(result) {
  const config = result.configurations;
  if (!config) return '';
  const verdicts = config.verdicts.map(item => `<li><span>${esc(item.label)}</span><b>${item.count} 种</b></li>`).join('');
  const blockingRows = (config.blocking || []).map(item => ({
    verdict: item.verdict_label,
    tickets: Object.entries(item.tickets).map(([segment, side]) => `${segment} 旧 ${side.old} / 新 ${side.new}`).join('；'),
    average: item.average,
    interval: `[${item.interval[0]}, ${item.interval[1]}]`,
  }));
  return `<section class="panel"><div class="panel-heading"><h2>配法一致性</h2><span class="aside-note">共 ${config.total} 种配法，${config.consistent ? '裁决全部一致' : '裁决不一致，暂不给结论'}</span></div>
    <div class="panel-body"><ul class="parameters">${verdicts}</ul></div>
    ${blockingRows.length ? table([{key:'verdict',label:'不同裁决'},{key:'tickets',label:'配法（区段 旧工单 / 新工单）'},{key:'average',label:'均差'},{key:'interval',label:'置信区间'}], blockingRows) : ''}</section>`;
}

const missingTable = result => (result.missing || []).length ? table([
  {key:'segment',label:'缺单区段'}, {label:'缺哪一侧',html:row => row.sides.map(side => side.label).join('、')},
  {label:'原因',html:row => row.sides.map(side => side.text).join('；')},
], result.missing) : '';

const ticketPanel = result => (result.tickets || []).length ? `<section class="panel"><div class="panel-heading"><h2>本版所用工单</h2><span class="aside-note">${result.tickets.length} 张，按此快照复现</span></div>${table([
  {key:'code',label:'工单编号'}, {key:'segment',label:'区段'}, {key:'procedure_label',label:'规程'},
  {key:'kind_label',label:'类别'}, {label:'计时（分钟）',html:row => row.minutes === null ? '—' : esc(row.minutes)},
  {label:'状态',html:row => esc(row.state_label || row.state)},
], result.tickets)}</section>` : '';

export async function resultPage(spec, user, route) {
  if (!route.id) {
    const runs = await get('/runs');
    return `${intro('结果与复核', spec.decision_prompt)}<section class="panel"><div class="panel-heading"><h2>选择分析结果</h2></div>${runTable(runs, '暂无结果。分析员可先在「分析任务」提交计算。')}</section>`;
  }
  const id = Number(route.id);
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error('分析编号无效');
  const run = await get(`/runs/${id}`);
  const head = intro(run.title, `批次 #${run.batch_id} · v${run.version} · ${run.sample_size} 个配对区段 · ${timeLabel(run.created_at)}`, status(run));
  if (run.status === RunStatus.QUEUED) return `${head}<div class="empty" data-pending="${id}">分析任务已入队，正在重算。此页会自动刷新。</div>`;
  const notice = run.status === RunStatus.SUPERSEDED || run.stale
    ? `<div class="stale-note" role="status">这份结论已作废，不能继续签核。${run.superseded_by ? `批次已重算为 <a href="#result/${run.superseded_by}">新版本</a>。` : ''}以下为当时所用工单的计算，可按当时快照复现。</div>` : '';
  if (run.status === RunStatus.FAILED || run.status === RunStatus.BLOCKED) {
    return `${head}${notice}<div class="empty" role="alert">${esc(run.error)} ${user.role === Role.ANALYST ? `<button data-retry="${id}">重试计算</button>` : ''}</div>`;
  }
  const data = run.result;
  let review = '<p>等待复核负责人签核。签核后也可由只读角色查看。</p>';
  if (run.review) review = `<p><b>${run.review.decision === Decision.APPROVED ? '签核通过' : '退回补充'}</b> ${esc(run.review.note)}</p><small>${esc(run.review.reviewer)} · ${timeLabel(run.review.at)}</small>`;
  const signable = !run.review && !run.stale && run.status === RunStatus.SUCCEEDED && data.consistent;
  if (signable && user.role === Role.SUPERVISOR) review = `<form id="review-form" data-id="${id}"><label class="field"><span>复核结论</span><select name="decision"><option value="approved">签核通过</option><option value="returned">退回补充</option></select></label><label class="field"><span>复核依据</span><textarea name="note" required minlength="2" maxlength="1000" placeholder="${esc(spec.decision_prompt)}"></textarea></label>${formError}<button class="primary">保存复核</button></form>`;
  else if (!run.review && !data.consistent) review = '<p role="alert">多种配法裁决不一致，需先核对补测、更正与撤回工单，暂不能签核。</p>';
  const parameters = spec.parameters.map(field => `<li><span>${esc(field.label)}</span><b>${esc(run.parameters[field.key])}</b></li>`).join('');
  return `${head}${notice}<div class="split result-summary"><section class="conclusion"><h2>${esc(data.headline)}</h2><p>${esc(data.summary)}</p>${data.metrics.length ? `<dl class="metrics">${data.metrics.map(metric => `<div><dt>${esc(metric.label)}</dt><dd>${esc(formatMetric(metric.value))}${metric.unit ? `<small> ${esc(metric.unit)}</small>` : ''}</dd></div>`).join('')}</dl>` : ''}</section><aside class="method"><h2>本次条件</h2><ul class="parameters">${parameters}</ul>${bars(data.chart)}</aside></div>
    ${configurationPanel(data)}
    ${missingTable(data)}
    <section class="panel"><div class="panel-heading"><h2>计算明细</h2><button data-download="/runs/${id}/export">下载 CSV</button></div>${table(data.columns,data.rows,'当前参数下无明细，计算结论保留。')}</section>
    ${ticketPanel(data)}
    <section class="panel"><div class="panel-heading"><h2>业务签核</h2>${run.review?.decision === Decision.APPROVED ? '<a href="#reports">查看分发 →</a>' : ''}</div><div class="panel-body">${review}</div></section>
    <section class="panel"><div class="panel-heading"><h2>按当时工单复现</h2><button data-reproduce="${id}">复现核对</button></div><div class="panel-body" id="reproduce-out"><p class="aside-note">用本版本固化的工单快照重新计算，核对签核时的数值。</p></div></section>`;
}

export function wireResult(root, refresh) {
  bindDownloads(root, download);
  bindForm(root.querySelector('#review-form'), async form => {
    await post(`/runs/${form.dataset.id}/review`,Object.fromEntries(new FormData(form)));
    notify('复核记录已保存');
    refresh();
  });
  root.querySelector('[data-retry]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { await post(`/runs/${button.dataset.retry}/retry`); notify('已重新入队，不新增版本'); refresh(); }
    catch (err) { notify(err.message, true); button.disabled = false; }
  });
  root.querySelector('[data-reproduce]')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const out = root.querySelector('#reproduce-out');
    button.disabled = true;
    try {
      const report = await post(`/runs/${button.dataset.reproduce}/reproduce`);
      out.innerHTML = `<p role="status"><b>${report.matches ? '数值与签核时一致' : '数值与签核时不一致'}</b> · 结论 ${esc(report.verdict_label)} · 快照 ${report.snapshot_size} 张工单</p>${report.metrics ? `<dl class="metrics">${report.metrics.map(metric => `<div><dt>${esc(metric.label)}</dt><dd>${esc(formatMetric(metric.value))}</dd></div>`).join('')}</dl>` : ''}`;
    } catch (err) { notify(err.message, true); }
    finally { button.disabled = false; }
  });
  const pending = root.querySelector('[data-pending]');
  if (pending) setTimeout(() => {
    if (pending.isConnected && location.hash === `#result/${pending.dataset.pending}`) refresh();
  }, 800);
}
