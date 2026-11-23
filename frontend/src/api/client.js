import { store } from '../stores/session.js';

async function request(path, options = {}) {
  const headers = new Headers(options.headers);
  if (store.user) headers.set('Authorization', `Bearer ${store.user.token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const result = await fetch(`/api${path}`, {...options, headers});
  if (!result.ok) {
    if (result.status === 401 && path !== '/auth/login') {
      store.setUser(null);
      window.dispatchEvent(new Event('desk:expired'));
    }
    const detail = await result.json().catch(() => ({}));
    throw new Error(detail.detail || `服务请求失败（${result.status}）`);
  }
  return result;
}

export async function get(path) { return (await request(path)).json(); }
export async function post(path, payload) {
  return (await request(path, {method:'POST', body: JSON.stringify(payload)})).json();
}
export async function importFile(file) {
  return (await request('/observations/import', {method:'POST', body:file, headers:{'Content-Type':'text/csv'}})).json();
}
export async function download(path, fallback) {
  const response = await request(path);
  const name = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1] || fallback;
  const href = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = href;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1500);
}
