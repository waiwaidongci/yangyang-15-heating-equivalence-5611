import { post } from '../api/client.js';
import { esc } from '../utils/html.js';
import { formError } from '../components/common/forms.js';
import { bindForm } from '../hooks/actions.js';
import { store } from '../stores/session.js';

const demos = {analyst: 'Analyst-2026!', supervisor: 'Supervisor-2026!', viewer:'Viewer-2026!'};
export function loginPage(spec) {
  return `<main class="login"><section class="login-identity"><p class="login-org">${esc(spec.organization)}</p><h1>${esc(spec.title.split('·').at(-1))}</h1><p class="tagline">${esc(spec.tagline)}</p><dl><dt>观测来源</dt><dd>${esc(spec.source)}</dd><dt>分析方法</dt><dd>${esc(spec.algorithm)}</dd></dl></section>
  <section class="login-entry"><form id="login-form"><h2>进入工作台</h2><label class="field"><span>邮箱</span><input name="email" type="email" autocomplete="username" required></label><label class="field"><span>密码</span><input name="password" type="password" autocomplete="current-password" required></label>${formError}<button class="primary" type="submit">登录</button><div class="demo-roles" aria-label="填入演示账号"><button type="button" data-demo="analyst">分析员</button><button type="button" data-demo="supervisor">负责人</button><button type="button" data-demo="viewer">只读</button></div></form></section></main>`;
}

export function wireLogin(root, refresh) {
  const form = root.querySelector('#login-form');
  root.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => {
    const role = button.dataset.demo;
    form.elements.email.value = `${role}@demo.local`;
    form.elements.password.value = demos[role];
  }));
  bindForm(form, async node => {
    const payload = Object.fromEntries(new FormData(node));
    store.setUser(await post('/auth/login', payload));
    refresh();
  });
}
