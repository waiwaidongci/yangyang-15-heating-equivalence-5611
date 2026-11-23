import { download, get, importFile, post } from '../api/client.js';
import { table } from '../components/common/data.js';
import { intro } from '../components/common/frame.js';
import { fieldControl, formError } from '../components/common/forms.js';
import { Role } from '../constants/enums.js';
import { bindDownloads, bindForm, notify } from '../hooks/actions.js';
import { formValues } from '../types/form.js';
import { esc } from '../utils/html.js';

export async function observationPage(spec, user, route) {
  const offset = Math.max(0, Number.parseInt(route.id, 10) || 0);
  const {total, items} = await get(`/observations?offset=${offset}&limit=20`);
  const writable = user.role !== Role.VIEWER;
  return `${intro('数据台账', spec.source, `<span class="count">${total} <small>条${esc(spec.record_name)}</small></span>`)}
    ${writable ? `<div class="tools"><details><summary>登记一条${esc(spec.record_name)}</summary><form id="record-form"><div class="form-grid">${spec.fields.map(field => fieldControl(field)).join('')}</div>${formError}<button class="primary">保存记录</button></form></details>
    <details><summary>按模板导入 CSV</summary><form id="import-form"><p>使用 UTF-8 CSV，每次最多 500 条。重复行自动跳过。</p><button type="button" data-download="/observations/template">下载模板</button><label class="field"><span>CSV 文件</span><input type="file" name="file" accept=".csv,text/csv" required></label>${formError}<button class="primary">导入文件</button></form></details></div>` : ''}
    <section class="panel"><div class="panel-heading"><h2>${esc(spec.record_name)}明细</h2>${writable ? '<a class="text-link" href="#analysis">发起分析 →</a>' : ''}</div>
    ${table([{key:'id',label:'记录号'},...spec.fields], items.map(item => ({id:item.id,...item.data})), '暂无观测。分析员可先导入 CSV 或登记样本。')}
    ${total ? `<div class="pagination"><span>第 ${offset + 1}–${Math.min(total,offset + 20)} 条</span>${offset > 0 ? `<a href="#observations/${Math.max(0, offset-20)}">上一页</a>` : ''}${offset+20 < total ? `<a href="#observations/${offset+20}">下一页</a>` : ''}</div>` : ''}</section>`;
}

export function wireObservations(root, spec, refresh) {
  bindDownloads(root, download);
  bindForm(root.querySelector('#record-form'), async form => {
    await post('/observations', formValues(form, spec.fields));
    notify('记录已保存');
    if (location.hash === '#observations' || !location.hash) refresh();
    else location.hash = '#observations';
  });
  bindForm(root.querySelector('#import-form'), async form => {
    const report = await importFile(form.elements.file.files[0]);
    notify(`已导入 ${report.added} 条 · 跳过 ${report.skipped} 条重复记录`);
    refresh();
  });
}
