import { download, get, importFile, post } from '../api/client.js';
import { empty, table } from '../components/common/data.js';
import { intro } from '../components/common/frame.js';
import { fieldControl, formError } from '../components/common/forms.js';
import { Role, ticketStateName } from '../constants/enums.js';
import { bindDownloads, bindForm, notify } from '../hooks/actions.js';
import { formValues } from '../types/form.js';
import { esc, timeLabel } from '../utils/html.js';

export async function batchTablePage(spec, user) {
  const batches = await get('/batches');
  const writable = user.role !== Role.VIEWER;
  const form = writable ? `<details class="batch-create"><summary>登记新批次</summary><form id="batch-form"><div class="form-grid"><label class="field"><span>批次名称</span><input name="name" required maxlength="120" placeholder="例如 SJ-2611-并行巡检"></label><label class="field"><span>备注</span><input name="note" maxlength="300"></label></div>${formError}<button class="primary">创建批次</button></form></details>` : '';
  return `${intro('批次台账', spec.source, `<span class="count">${batches.length} <small>个新旧计时批次</small></span>`)}
    ${form}
    <section class="panel"><div class="panel-heading"><h2>计时批次</h2></div>
    ${table([
      {label:'批次',html:row => `<a href="#batches/${row.id}">${esc(row.name)}</a>`},
      {label:'区段',html:row => `${row.segment_count} 段`},
      {label:'完整配对',html:row => `${row.paired_count} 段`},
      {label:'缺单',html:row => row.missing_count ? `<b class="flag">${row.missing_count} 段</b>` : '—'},
      {label:'最新分析',html:row => row.latest_run ? `<a href="#result/${row.latest_run.id}">v${row.latest_run.version} · ${esc(row.latest_run.status)}</a>` : '未提交'},
      {label:'提交时间',html:row => timeLabel(row.created_at)},
    ], batches, '还没有计时批次。分析员可先登记批次，再分别导入新旧规程计时。')}</section>`;
}

export function wireBatches(root, refresh) {
  bindForm(root.querySelector('#batch-form'), async form => {
    const values = Object.fromEntries(new FormData(form));
    const batch = await post('/batches', {name:values.name, note:values.note});
    notify('批次已创建');
    location.hash = `#batches/${batch.id}`;
  });
}

function ticketColumns(spec) {
  return [
    {key:'code', label:'工单编号'},
    {key:'segment', label:'区段'},
    {key:'procedure_label', label:'规程'},
    {key:'kind_label', label:'类别'},
    {label:'计时（分钟）', html:row => row.minutes === null ? '—' : esc(row.minutes)},
    {key:'inspected_on', label:'计时日期'},
    {label:'关联工单', html:row => row.target_code ? esc(row.target_code) : '—'},
    {label:'状态', html:row => `<span class="status status-${esc(row.state)}">${esc(row.state_label || ticketStateName[row.state] || row.state)}</span>`},
  ];
}

export async function registryPage(spec, user, route) {
  const id = route.id;
  if (!id) throw new Error('请选择批次');
  const registry = await get(`/batches/${id}/registry`);
  const batch = registry.batch;
  const writable = user.role !== Role.VIEWER;
  const ticketFields = spec.ticket_fields;
  const entryFields = ticketFields.map(field => {
    if (field.key === 'minutes') return fieldControl({...field, required:false});
    if (field.key === 'kind') return fieldControl(field, true);
    return fieldControl(field);
  });
  const missing = registry.missing || [];
  const issues = registry.issues || [];
  const ambiguous = registry.ambiguous || [];
  const pairs = Object.entries(registry.pairs || {});

  const missingRow = missing.length ? `<section class="panel"><div class="panel-heading"><h2>缺单区段</h2><span class="aside-note">缺一侧有效计时，不参与检验</span></div><div class="table-wrap"><table><thead><tr><th scope="col">区段</th><th scope="col">缺哪一侧</th><th scope="col">原因</th></tr></thead><tbody>${missing.map(item => `<tr><td>${esc(item.segment)}</td><td>${esc(item.sides.map(side => side.label).join('、'))}</td><td>${esc(item.sides.map(side => side.text).join('；'))}</td></tr>`).join('')}</tbody></table></div></section>` : '';
  const issueRow = issues.length ? `<section class="panel"><div class="panel-heading"><h2>待核对的引用</h2><span class="aside-note">更正或撤回尚未生效</span></div><div class="table-wrap"><table><thead><tr><th scope="col">工单</th><th scope="col">引用</th><th scope="col">说明</th></tr></thead><tbody>${issues.map(item => `<tr><td>${esc(item.code)}</td><td>${esc(item.target_code || '—')}</td><td>${esc(item.text)}</td></tr>`).join('')}</tbody></table></div></section>` : '';
  const ambiguousRow = ambiguous.length ? `<section class="panel"><div class="panel-heading"><h2>多配法区段</h2><span class="aside-note">同一区段有多个有效计时</span></div><div class="table-wrap"><table><thead><tr><th scope="col">区段</th><th scope="col">旧规程候选</th><th scope="col">新规程候选</th></tr></thead><tbody>${ambiguous.map(item => `<tr><td>${esc(item.segment)}</td><td>${esc(item.old.map(row => `${row.code} ${row.minutes}`).join('，'))}</td><td>${esc(item.new.map(row => `${row.code} ${row.minutes}`).join('，'))}</td></tr>`).join('')}</tbody></table></div></section>` : '';

  const pairRows = pairs.map(([segment, sides]) => ({segment, old: sides.old.join('，'), new: sides.new.join('，')}));

  const tools = writable ? `<div class="tools">
    <details><summary>登记一张计时工单</summary><form id="ticket-form">
      <div class="form-grid">
        <label class="field"><span>规程</span><select name="procedure" required><option value="old">旧规程</option><option value="new">新规程</option></select></label>
        ${entryFields.join('')}
      </div>${formError}<button class="primary">保存工单</button></form></details>
    <details><summary>分别导入新旧规程计时 CSV</summary><form id="import-form">
      <p>两份 CSV 分开提交，可乱序导入。时间与更正撤回均在表内。</p>
      <label class="field"><span>规程</span><select name="procedure" required><option value="old">旧规程</option><option value="new">新规程</option></select></label>
      <label class="field"><span>CSV 文件</span><input type="file" name="file" accept=".csv,text/csv" required></label>${formError}<button class="primary">导入文件</button></form></details>
    <div class="download-strip"><button data-download="/batches/${id}/tickets/template?procedure=old">下载旧规程模板</button><button data-download="/batches/${id}/tickets/template?procedure=new">下载新规程模板</button></div>
  </div>` : '';

  const run = batch.latest_run;
  const runLine = run ? `<p>最新分析 <a href="#result/${run.id}">v${run.version} · ${esc(run.status)}</a>${batch.needs_recompute ? '（批次有新的计时工单，待重算）' : ''}</p>` : '<p>还没有提交分析。</p>';
  const runButton = writable ? `<div class="panel-body"><a class="button-link" href="#analysis/${id}">到分析任务提交复核</a></div>` : '';

  return `${intro(batch.name, `批次 #${batch.id} · ${batch.ticket_count} 张工单 · 完整配对 ${pairs.length} 段`, `<a class="text-link" href="#batches">← 批次台账</a>`)}
    <div class="split"><section class="panel"><div class="panel-heading"><h2>批次概览</h2></div><div class="panel-body"><p>${esc(batch.note || '无备注')}</p>${runLine}</div>${runButton}</section>
    <aside class="method"><h2>规程计时口径</h2><p>${esc(spec.formula)}</p><p class="aside-note">新旧两份计时分开提交；缺一侧的区段只列为缺单，不进入比较。</p></aside></div>
    ${tools}
    ${missingRow}${issueRow}${ambiguousRow}
    <section class="panel"><div class="panel-heading"><h2>有效配对</h2><span class="aside-note">每个区段旧、新各取一张有效工单</span></div>
    ${table([{key:'segment',label:'区段'},{key:'old',label:'旧规程有效工单'},{key:'new',label:'新规程有效工单'}], pairRows, '暂无完整配对。请补齐缺单区段。')}</section>
    <section class="panel"><div class="panel-heading"><h2>全部计时工单</h2></div>
    ${table(ticketColumns(spec), registry.tickets || [], '本批次还没有工单。')}</section>`;
}

export function wireRegistry(root, spec, refresh) {
  bindDownloads(root, download);
  bindForm(root.querySelector('#ticket-form'), async form => {
    const values = formValues(form, spec.ticket_fields);
    await post(`/batches/${location.hash.split('/')[1]}/tickets`, {tickets: [values]});
    notify('工单已保存');
    refresh();
  });
  bindForm(root.querySelector('#import-form'), async form => {
    const procedure = form.elements.procedure.value;
    const file = form.elements.file.files[0];
    const report = await importFile(`/batches/${location.hash.split('/')[1]}/tickets/import?procedure=${procedure}`, file);
    notify(`已导入 ${report.added} 张 · 跳过 ${report.skipped} 张重复工单`);
    refresh();
  });
}
