import { download, get, post } from '../api/client.js';
import { intro } from '../components/common/frame.js';
import { empty, table } from '../components/common/data.js';
import { formError } from '../components/common/forms.js';
import { Decision, Role } from '../constants/enums.js';
import { bindDownloads, bindForm, notify } from '../hooks/actions.js';
import { esc, timeLabel } from '../utils/html.js';

export async function reportPage(spec, user) {
  const supervisor = user.role === Role.SUPERVISOR;
  const reads = supervisor ? ['/reports/inbox','/reports/schedules','/reports/audit','/runs'] : ['/reports/inbox'];
  const [inbox,schedules,audit,runs] = await Promise.all(reads.map(get));
  const approved = runs?.filter(run => run.review?.decision === Decision.APPROVED) || [];
  return `${intro('报表分发','已签核结果按计划投递到本地收件箱，供交班和归档。','<button id="refresh-inbox">刷新收件箱</button>')}
    ${supervisor ? `<section class="panel"><div class="panel-heading"><h2>分发计划</h2></div>
    ${approved.length ? `<form class="panel-body" id="schedule-form"><div class="form-grid"><label class="field"><span>签核报告</span><select name="run_id" required>${approved.map(run => `<option value="${run.id}">${esc(run.title)}</option>`).join('')}</select></label><label class="field"><span>收件组</span><input name="recipient" required minlength="2" maxlength="100" value="${esc(spec.recipient)}"></label><label class="field"><span>分发间隔（分钟）</span><input name="interval_minutes" type="number" required min="1" max="10080" value="1440"></label><label class="field"><span>首次分发时间（北京时间）</span><input name="start_at" type="datetime-local"><small>留空时立即投递一次。</small></label></div>${formError}<button class="primary">创建分发计划</button></form>` : empty('暂无可分发的报告。请先签核一份成功的分析。')}
    ${schedules.length ? table([{key:'recipient',label:'收件组'},{key:'interval_minutes',label:'间隔（分钟）'},{label:'下次分发',html:row => row.active ? timeLabel(row.next_at) : '已停止'},{label:'操作',html:row => row.active ? `<button data-stop="${row.id}">停止计划</button>` : '—'}],schedules) : ''}</section>` : ''}
    <section class="panel"><div class="panel-heading"><h2>本地收件箱</h2></div>${table([{key:'recipient',label:'收件组'},{label:'来源分析',html:row => `<a href="#result/${row.run_id}">查看分析 #${row.run_id}</a>`},{label:'送达时间',html:row => timeLabel(row.at)},{label:'文件',html:row => `<button data-download="/reports/inbox/${row.id}/file">下载报表</button>`}], inbox, '暂无报表。计划到期后，后台任务会把报表投到这里。')}</section>
    ${supervisor && audit.length ? `<section class="panel"><div class="panel-heading"><h2>操作记录</h2></div>${table([{label:'时间',html:row => timeLabel(row.at)},{key:'actor',label:'操作人'},{key:'detail',label:'说明'}],audit)}</section>` : ''}`;
}

export function wireReports(root, refresh) {
  bindDownloads(root, download);
  root.querySelector('#refresh-inbox')?.addEventListener('click', refresh);
  bindForm(root.querySelector('#schedule-form'), async form => {
    const values = Object.fromEntries(new FormData(form));
    const start = values.start_at ? `${values.start_at}:00+08:00` : null;
    await post('/reports/schedules',{run_id:Number(values.run_id),recipient:values.recipient,interval_minutes:Number(values.interval_minutes),start_at:start});
    notify('分发计划已保存');
    refresh();
  });
  root.querySelectorAll('[data-stop]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try { await post(`/reports/schedules/${button.dataset.stop}/stop`,{}); notify('分发计划已停止'); refresh(); }
    catch (err) { notify(err.message,true); button.disabled = false; }
  }));
}
