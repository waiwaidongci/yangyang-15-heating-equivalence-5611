let session = null;
try { session = JSON.parse(sessionStorage.getItem('desk.session')); } catch { /* expired or malformed cache */ }
export const store = {
  spec: null,
  get user() { return session; },
  setUser(next) {
    session = next;
    if (next) sessionStorage.setItem('desk.session', JSON.stringify(next));
    else sessionStorage.removeItem('desk.session');
  },
};
