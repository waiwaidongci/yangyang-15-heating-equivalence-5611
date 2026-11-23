export function notify(message, error = false) {
  const notice = document.getElementById('notice');
  notice.textContent = message;
  notice.classList.toggle('notice-error', error);
  notice.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { notice.hidden = true; }, 4200);
}

export function bindForm(node, action) {
  if (!node) return;
  node.addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.submitter;
    const error = node.querySelector('[role="alert"]');
    if (error) { error.hidden = true; error.textContent = ''; }
    if (button) button.disabled = true;
    try { await action(node); }
    catch (err) {
      if (error) { error.textContent = err.message; error.hidden = false; }
      else notify(err.message, true);
    } finally { if (button) button.disabled = false; }
  });
}

export function bindDownloads(parent, download) {
  for (const button of parent.querySelectorAll('[data-download]')) {
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await download(button.dataset.download, 'yangyang-export.csv'); }
      catch (err) { notify(err.message, true); }
      finally { button.disabled = false; }
    });
  }
}
