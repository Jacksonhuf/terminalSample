export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/operations.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let activeTab = 'dashboard';

    function switchTab(name) {
      activeTab = name;
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + name).classList.add('active');
      if (name === 'dashboard') loadDashboard();
      if (name === 'audit') loadAuditLogs();
      if (name === 'approvals') loadApprovals();
      if (name === 'messages') loadMessageLogs();
      if (name === 'outreach') loadOutreachTasks();
    }

    function renderEmpty(targetId, message) {
      document.getElementById(targetId).innerHTML = `<div class="empty-state card">${escHtml(message)}</div>`;
    }

    function renderTable(targetId, columns, rows) {
      if (!rows.length) {
        renderEmpty(targetId, '暂无数据');
        return;
      }
      const head = columns.map(c => `<th>${escHtml(c.label)}</th>`).join('');
      const body = rows.map(row => {
        const cells = columns.map(c => `<td>${escHtml(String(row[c.key] ?? ''))}</td>`).join('');
        return `<tr>${cells}</tr>`;
      }).join('');
      document.getElementById(targetId).innerHTML = `
        <table class="data-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>`;
    }

    async function loadStatus() {
      try {
        const status = await api('/operations/status');
        const parts = [];
        parts.push(status.audit_configured ? '审计: 已配置' : '审计: 未配置');
        parts.push(status.approvals_configured ? '审批: 已配置' : '审批: 未配置');
        parts.push(status.integrations_configured ? '出站消息: 已配置' : '出站消息: 未配置');
        parts.push(status.runtime_configured ? '运行时: 已配置' : '运行时: 未配置');
        parts.push(status.prototype_configured ? '样机看板: 已配置' : '样机看板: 未配置');
        document.getElementById('status-info').textContent = parts.join(' | ');
        document.getElementById('run-outreach-btn').disabled = !status.integrations_configured;
        document.getElementById('seed-btn').disabled = !status.prototype_configured;
      } catch (e) {
        document.getElementById('status-info').textContent = e.message;
      }
    }

    function renderKeyValueTable(title, rows, columns) {
      if (!rows.length) return '';
      const head = columns.map(c => `<th>${escHtml(c.label)}</th>`).join('');
      const body = rows.map(row => {
        const cells = columns.map(c => `<td>${escHtml(String(row[c.key] ?? ''))}</td>`).join('');
        return `<tr>${cells}</tr>`;
      }).join('');
      return `
        <h3 class="section-title">${escHtml(title)}</h3>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>`;
    }

    async function loadDashboard() {
      const target = document.getElementById('dashboard-content');
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
          </div>
          ${renderKeyValueTable('使用中样机', data.in_use || [], [
            { key: 'prototype_id', label: '样机 ID' },
            { key: 'model', label: '型号' },
            { key: 'custodian_id', label: '保管人' },
          ])}
          ${renderKeyValueTable('逾期预约', data.overdue_reservations || [], [
            { key: 'reservation_id', label: '预约 ID' },
            { key: 'prototype_id', label: '样机' },
            { key: 'person_id', label: '预约人' },
            { key: 'end_date', label: '截止日' },
          ])}`;
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

    function onApprovalStatusChange() {
      const isPending = document.getElementById('approval-status').value === 'pending';
      document.getElementById('batch-actions').style.display = isPending ? 'flex' : 'none';
      document.getElementById('select-all-approvals').checked = false;
    }

    function toggleSelectAll() {
      const checked = document.getElementById('select-all-approvals').checked;
      document.querySelectorAll('.approval-checkbox').forEach(cb => { cb.checked = checked; });
    }

    function getSelectedApprovalIds() {
      return Array.from(document.querySelectorAll('.approval-checkbox:checked')).map(cb => cb.value);
    }

    async function batchResolve(approved) {
      const ids = getSelectedApprovalIds();
      if (!ids.length) {
        toast('请先选择审批项', 'error');
        return;
      }
      try {
        const result = await api('/approvals/batch-resolve', {
          method: 'POST',
          body: JSON.stringify({
            request_ids: ids,
            approved,
            resolver_id: 'admin-ui',
            resolver_roles: ['admin'],
          }),
        });
        const ok = result.succeeded.length;
        const fail = result.failed.length;
        toast(`已处理 ${ok} 条${fail ? `，失败 ${fail} 条` : ''}`);
        loadApprovals();
        loadAuditLogs();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function loadAuditLogs() {
      const action = document.getElementById('audit-action').value.trim();
      const user = document.getElementById('audit-user').value.trim();
      const params = new URLSearchParams();
      if (action) params.set('action_name', action);
      if (user) params.set('user_id', user);
      params.set('limit', '100');
      try {
        const data = await api('/audit-logs?' + params.toString());
        if (!data.configured) {
          renderEmpty('audit-table', data.message || '未配置审计日志');
          return;
        }
        renderTable('audit-table', [
          { key: 'timestamp', label: '时间' },
          { key: 'user_id', label: '用户' },
          { key: 'action_name', label: '动作' },
          { key: 'target_id', label: '目标' },
          { key: 'status', label: '状态' },
          { key: 'message', label: '消息' },
        ], data.logs);
      } catch (e) {
        renderEmpty('audit-table', e.message);
      }
    }

    async function loadApprovals() {
      const status = document.getElementById('approval-status').value;
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      params.set('limit', '100');
      try {
        const data = await api('/approvals?' + params.toString());
        if (!data.configured) {
          renderEmpty('approvals-table', data.message || '未配置审批存储');
          return;
        }
        if (!data.requests.length) {
          renderEmpty('approvals-table', '暂无审批请求');
          return;
        }
        const showBatch = status === 'pending';
        document.getElementById('batch-actions').style.display = showBatch ? 'flex' : 'none';
        const rows = data.requests.map(r => ({
          ...r,
          requester_roles: Array.isArray(r.requester_roles) ? r.requester_roles.join(', ') : r.requester_roles,
          actions: r.status === 'pending'
            ? `<button class="btn btn-primary btn-sm" onclick="resolveApproval('${r.id}', true)">批准</button>
               <button class="btn btn-secondary btn-sm" onclick="resolveApproval('${r.id}', false)">拒绝</button>`
            : '',
        }));
        const checkboxHeader = showBatch ? '<th></th>' : '';
        document.getElementById('approvals-table').innerHTML = `
          <table class="data-table">
            <thead><tr>
              ${checkboxHeader}
              <th>创建时间</th><th>动作</th><th>目标</th><th>发起人</th><th>状态</th><th>线程</th><th>操作</th>
            </tr></thead>
            <tbody>
              ${rows.map(r => `<tr>
                ${showBatch && r.status === 'pending'
                  ? `<td><input type="checkbox" class="approval-checkbox" value="${escHtml(r.id)}"></td>`
                  : (showBatch ? '<td></td>' : '')}
                <td>${escHtml(r.created_at)}</td>
                <td>${escHtml(r.action_name)}</td>
                <td>${escHtml(r.target_id)}</td>
                <td>${escHtml(r.requester_id)} (${escHtml(r.requester_roles)})</td>
                <td>${escHtml(r.status)}</td>
                <td>${escHtml(r.thread_id)}</td>
                <td>${r.actions}</td>
              </tr>`).join('')}
            </tbody>
          </table>`;
      } catch (e) {
        renderEmpty('approvals-table', e.message);
      }
    }

    async function resolveApproval(requestId, approved) {
      try {
        const result = await api(`/approvals/${requestId}/resolve`, {
          method: 'POST',
          body: JSON.stringify({
            approved,
            resolver_id: 'admin-ui',
            resolver_roles: ['admin'],
          }),
        });
        toast(result.response || `已${approved ? '批准' : '拒绝'}`);
        loadApprovals();
        loadAuditLogs();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function loadMessageLogs() {
      const objectType = document.getElementById('msg-object-type').value.trim();
      const objectId = document.getElementById('msg-object-id').value.trim();
      const params = new URLSearchParams();
      if (objectType) params.set('object_type', objectType);
      if (objectId) params.set('object_id', objectId);
      params.set('limit', '100');
      try {
        const data = await api('/message-logs?' + params.toString());
        if (!data.configured) {
          renderEmpty('messages-table', data.message || '未配置 integrations 数据库');
          return;
        }
        renderTable('messages-table', [
          { key: 'timestamp', label: '时间' },
          { key: 'channel', label: '通道' },
          { key: 'template_id', label: '模板' },
          { key: 'recipients', label: '收件人' },
          { key: 'status', label: '状态' },
          { key: 'object_id', label: '对象' },
          { key: 'error', label: '错误' },
        ], data.logs.map(l => ({
          ...l,
          recipients: Array.isArray(l.recipients) ? l.recipients.join(', ') : l.recipients,
        })));
      } catch (e) {
        renderEmpty('messages-table', e.message);
      }
    }

    async function loadOutreachTasks() {
      const status = document.getElementById('task-status').value;
      const objectType = document.getElementById('task-object-type').value.trim();
      const objectId = document.getElementById('task-object-id').value.trim();
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      if (objectType) params.set('object_type', objectType);
      if (objectId) params.set('object_id', objectId);
      params.set('limit', '100');
      try {
        const data = await api('/outreach-tasks?' + params.toString());
        if (!data.configured) {
          renderEmpty('outreach-table', data.message || '未配置 integrations 数据库');
          return;
        }
        renderTable('outreach-table', [
          { key: 'due_at', label: '到期时间' },
          { key: 'channel', label: '通道' },
          { key: 'template_id', label: '模板' },
          { key: 'status', label: '状态' },
          { key: 'object_id', label: '对象' },
          { key: 'person_id', label: '人员' },
          { key: 'attempt_count', label: '重试' },
          { key: 'last_error', label: '错误' },
        ], data.tasks);
      } catch (e) {
        renderEmpty('outreach-table', e.message);
      }
    }

    async function runOutreach() {
      try {
        const result = await api('/outreach/run', { method: 'POST' });
        toast(`已处理 ${result.processed} 条，成功 ${result.sent}，失败 ${result.failed}`);
        loadOutreachTasks();
        loadMessageLogs();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    loadStatus();
    onApprovalStatusChange();
    switchTab(params.tab || 'dashboard');

  Object.assign(window, { getSelectedApprovalIds, seedPrototype, loadAuditLogs, loadDashboard, renderTable, toggleSelectAll, onApprovalStatusChange, runOutreach, switchTab, loadOutreachTasks, loadMessageLogs, loadStatus, renderEmpty, loadApprovals, batchResolve, resolveApproval, renderKeyValueTable });
  return () => { delete window.batchResolve; delete window.getSelectedApprovalIds; delete window.loadApprovals; delete window.loadAuditLogs; delete window.loadDashboard; delete window.loadMessageLogs; delete window.loadOutreachTasks; delete window.loadStatus; delete window.onApprovalStatusChange; delete window.renderEmpty; delete window.renderKeyValueTable; delete window.renderTable; delete window.resolveApproval; delete window.runOutreach; delete window.seedPrototype; delete window.switchTab; delete window.toggleSelectAll; };
}
