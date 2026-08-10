export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/prototype_app.html').then(r => r.text());
  container.innerHTML = html;

  async function loadDashboard() {
    const target = document.getElementById('prototype-dashboard-content');
    try {
      const data = await api('/prototype/dashboard');
      if (!data.configured) {
        target.innerHTML = `<div class="empty-state card">${escHtml(data.message || '未配置运行时平台')}</div>`;
        return;
      }
      const summary = data.summary || {};
      const byStatus = data.by_status || {};
      const byModel = data.by_model || {};
      target.innerHTML = `
        <div class="dashboard-grid">
          <div class="stat-card"><div class="label">样机总数</div><div class="value">${summary.prototype_total ?? 0}</div></div>
          <div class="stat-card"><div class="label">使用中</div><div class="value">${(data.in_use || []).length}</div></div>
          <div class="stat-card"><div class="label">活跃预约</div><div class="value">${summary.reservation_active ?? 0}</div></div>
          <div class="stat-card"><div class="label">逾期预约</div><div class="value">${summary.reservation_overdue ?? 0}</div></div>
        </div>
        <div class="card">
          <div class="stats">
            ${Object.entries(byStatus).map(([k, v]) => `<span class="stat"><strong>${escHtml(k)}</strong>: ${v}</span>`).join('')}
          </div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="stats">
            ${Object.entries(byModel).map(([k, v]) => `<span class="stat"><strong>${escHtml(k)}</strong>: ${v}</span>`).join('')}
          </div>
        </div>`;
    } catch (e) {
      target.innerHTML = `<div class="empty-state card">${escHtml(e.message)}</div>`;
    }
  }

  async function seedPrototype() {
    try {
      const result = await api('/prototype/seed', { method: 'POST' });
      toast(result.message || '演示数据已写入');
      loadDashboard();
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  loadDashboard();

  Object.assign(window, { loadDashboard, seedPrototype });
  return () => { delete window.loadDashboard; delete window.seedPrototype; };
}
