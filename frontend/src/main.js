import { get } from './api/client.js';
import { frame } from './components/common/frame.js';
import { analysisPage, wireAnalysis } from './pages/analysis.js';
import { loginPage, wireLogin } from './pages/login.js';
import { observationPage, wireObservations } from './pages/observations.js';
import { reportPage, wireReports } from './pages/reports.js';
import { resultPage, wireResult } from './pages/result.js';
import { route } from './router/hash.js';
import { store } from './stores/session.js';
import { esc } from './utils/html.js';

const root = document.getElementById('app');
const pages = {observations:observationPage,analysis:analysisPage,result:resultPage,reports:reportPage};
let navigationTick = 0;

async function render() {
  const tick = ++navigationTick;
  try {
    store.spec ||= await get('/spec');
    const spec = store.spec;
    document.title = spec.title;
    document.body.className = `theme-${spec.layout}`;
    if (!store.user) {
      root.innerHTML = loginPage(spec);
      wireLogin(root,render);
      return;
    }
    const current = route();
    const user = store.user;
    const content = await pages[current.page](spec, user, current);
    if (tick !== navigationTick) return;
    root.innerHTML = frame(spec,user,current,content);
    root.querySelector('#logout').addEventListener('click', () => {
      store.setUser(null);
      if (location.hash) location.hash = '';
      render();
    });
    if (current.page === 'observations') wireObservations(root, spec,render);
    if (current.page === 'analysis') wireAnalysis(root,spec);
    if (current.page === 'result') wireResult(root,render);
    if (current.page === 'reports') wireReports(root,render);
  } catch (err) {
    if (tick !== navigationTick) return;
    const standalone = `<section class="panel recovery"><h1>页面加载失败</h1><p role="alert">${esc(err.message)}</p><button class="primary" id="retry">重试</button></section>`;
    root.innerHTML = store.user && store.spec ? frame(store.spec,store.user,route(),standalone) : `<main>${standalone}</main>`;
    root.querySelector('#retry').addEventListener('click',render);
    root.querySelector('#logout')?.addEventListener('click', () => { store.setUser(null); render(); });
  }
}

window.addEventListener('hashchange',render);
window.addEventListener('desk:expired',render);
render();
