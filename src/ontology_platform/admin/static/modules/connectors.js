export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/connectors.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let editingConnector = null;
    let editingCredential = null;

    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + name).classList.add('active');
      if (name === 'connectors') loadConnectors();
      if (name === 'credentials') loadCredentials();
    }

    async function loadStatus() {
      try {
        const status = await api('/operations/status');
        const parts = [
          status.credentials_configured ? '凭据库: 已配置' : '凭据库: 未配置（需 --store-path）',
          status.connectors_configured ? '连接器: 已配置' : '连接器: 未配置',
        ];
        document.getElementById('status-info').textContent = parts.join(' | ');
      } catch (e) {
        document.getElementById('status-info').textContent = e.message;
      }
    }

    async function loadCredentialOptions() {
      const select = document.getElementById('c-credential-ref');
      const current = select.value;
      select.innerHTML = '<option value="">（无）</option>';
      try {
        const data = await api('/credentials');
        if (!data.configured) return;
        data.credentials.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.id;
          opt.textContent = `${c.name} (${c.username})`;
          select.appendChild(opt);
        });
        select.value = current;
      } catch (_) {}
    }

    async function loadConnectors() {
      await loadCredentialOptions();
      try {
        const data = await api('/connectors');
        if (!data.connectors.length) {
          document.getElementById('connectors-table').innerHTML = '<div class="empty-state card">暂无连接器</div>';
          return;
        }
        document.getElementById('connectors-table').innerHTML = `
          <table class="data-table">
            <thead><tr>
              <th>名称</th><th>模式</th><th>目标 URL</th><th>凭据</th><th>操作</th>
            </tr></thead>
            <tbody>
              ${data.connectors.map(c => `<tr>
                <td>${escHtml(c.name)}</td>
                <td>${escHtml(c.mode)}</td>
                <td>${escHtml(c.source_url || c.source_file || '')}</td>
                <td>${escHtml(c.credential_ref || '-')}</td>
                <td>
                  <button class="btn btn-primary btn-sm" onclick="runCaptureByName('${escAttr(c.name)}', true)">采集</button>
                  <button class="btn btn-secondary btn-sm" onclick='editConnector(${JSON.stringify(c).replace(/'/g, "&#39;")})'>编辑</button>
                  <button class="btn btn-secondary btn-sm" onclick="deleteConnector('${escHtml(c.name)}')">删除</button>
                </td>
              </tr>`).join('')}
            </tbody>
          </table>`;
      } catch (e) {
        document.getElementById('connectors-table').innerHTML = `<div class="empty-state card">${escHtml(e.message)}</div>`;
      }
    }

    function showConnectorForm() {
      editingConnector = null;
      document.getElementById('connector-form-title').textContent = '新建连接器';
      document.getElementById('c-name').value = '';
      document.getElementById('c-mode').value = 'computer_use';
      document.getElementById('c-source-url').value = '';
      document.getElementById('c-credential-ref').value = '';
      document.getElementById('c-login-url').value = '';
      document.getElementById('c-description').value = '';
      document.getElementById('c-instructions').value = '';
      document.getElementById('c-schedule-enabled').checked = false;
      document.getElementById('c-schedule-interval').value = '3600';
      document.getElementById('c-schedule-auto-sync').checked = true;
      document.getElementById('task-output').style.display = 'none';
      document.getElementById('connector-form').style.display = 'block';
      document.getElementById('c-name').disabled = false;
    }

    function hideConnectorForm() {
      document.getElementById('connector-form').style.display = 'none';
    }

    function editConnector(c) {
      editingConnector = c.name;
      document.getElementById('connector-form-title').textContent = `编辑连接器: ${c.name}`;
      document.getElementById('c-name').value = c.name;
      document.getElementById('c-name').disabled = true;
      document.getElementById('c-mode').value = c.mode;
      document.getElementById('c-source-url').value = c.source_url || '';
      document.getElementById('c-credential-ref').value = c.credential_ref || '';
      document.getElementById('c-login-url').value = (c.login && c.login.login_url) || '';
      document.getElementById('c-description').value = c.description || '';
      document.getElementById('c-instructions').value = c.capture_instructions || '';
      const sched = c.schedule || {};
      document.getElementById('c-schedule-enabled').checked = !!sched.enabled;
      document.getElementById('c-schedule-interval').value = sched.interval_sec || 3600;
      document.getElementById('c-schedule-auto-sync').checked = sched.auto_sync !== false;
      document.getElementById('task-output').style.display = 'none';
      document.getElementById('connector-form').style.display = 'block';
    }

    async function saveConnector() {
      const name = document.getElementById('c-name').value.trim();
      if (!name) { toast('请填写连接器名称', 'error'); return; }
      const body = {
        name,
        description: document.getElementById('c-description').value.trim(),
        mode: document.getElementById('c-mode').value,
        source_url: document.getElementById('c-source-url').value.trim(),
        credential_ref: document.getElementById('c-credential-ref').value,
        login: {
          type: 'form',
          login_url: document.getElementById('c-login-url').value.trim(),
        },
        capture_instructions: document.getElementById('c-instructions').value,
        schedule: {
          enabled: document.getElementById('c-schedule-enabled').checked,
          interval_sec: parseInt(document.getElementById('c-schedule-interval').value, 10) || 3600,
          auto_sync: document.getElementById('c-schedule-auto-sync').checked,
        },
        record_mappings: editingConnector ? undefined : [],
      };
      try {
        if (editingConnector) {
          const existing = await api(`/connectors/${editingConnector}`);
          body.record_mappings = existing.record_mappings || [];
          await api(`/connectors/${editingConnector}`, { method: 'PUT', body: JSON.stringify(body) });
        } else {
          await api('/connectors', { method: 'POST', body: JSON.stringify(body) });
        }
        toast('连接器已保存');
        hideConnectorForm();
        loadConnectors();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function deleteConnector(name) {
      if (!confirm(`删除连接器 ${name}?`)) return;
      try {
        await api(`/connectors/${name}`, { method: 'DELETE' });
        toast('已删除');
        loadConnectors();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function generateTask() {
      const name = document.getElementById('c-name').value.trim();
      if (!name) { toast('请先保存连接器', 'error'); return; }
      try {
        const task = await api(`/connectors/${name}/task`, { method: 'POST' });
        const out = document.getElementById('task-output');
        out.style.display = 'block';
        out.textContent = JSON.stringify(task, null, 2);
        toast('采集任务已生成（密码通过 CU_PASSWORD 环境变量注入，不出现在 JSON 中）');
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function runCapture(mock) {
      const name = document.getElementById('c-name').value.trim();
      if (!name) { toast('请先保存连接器', 'error'); return; }
      await runCaptureByName(name, mock);
    }

    async function runCaptureByName(name, mock) {
      const label = mock ? '演示采集 (Mock)' : 'LLM 采集';
      if (!mock && !confirm(`确认对「${name}」执行${label}？需要已配置 LLM 与 playwright。`)) return;
      try {
        toast(`${label}进行中...`);
        const result = await api(`/connectors/${name}/run`, {
          method: 'POST',
          body: JSON.stringify({ mock, auto_sync: true }),
        });
        const out = document.getElementById('task-output');
        if (out) {
          out.style.display = 'block';
          out.textContent = JSON.stringify(result, null, 2);
        }
        toast(`采集完成：${result.records_captured || 0} 条，同步 ${result.records_synced || 0} 条`);
        loadConnectors();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function loadCredentials() {
      try {
        const data = await api('/credentials');
        if (!data.configured) {
          document.getElementById('credentials-table').innerHTML =
            `<div class="empty-state card">${escHtml(data.message || '未配置凭据存储，请使用 --store-path 启动')}</div>`;
          return;
        }
        if (!data.credentials.length) {
          document.getElementById('credentials-table').innerHTML = '<div class="empty-state card">暂无凭据</div>';
          return;
        }
        document.getElementById('credentials-table').innerHTML = `
          <table class="data-table">
            <thead><tr>
              <th>ID</th><th>名称</th><th>用户名</th><th>登录 URL</th><th>密码</th><th>操作</th>
            </tr></thead>
            <tbody>
              ${data.credentials.map(c => `<tr>
                <td>${escHtml(c.id)}</td>
                <td>${escHtml(c.name)}</td>
                <td>${escHtml(c.username)}</td>
                <td>${escHtml(c.login_url || '-')}</td>
                <td>${c.password_set ? '已设置' : '未设置'}</td>
                <td>
                  <button class="btn btn-secondary btn-sm" onclick='editCredential(${JSON.stringify(c).replace(/'/g, "&#39;")})'>编辑</button>
                  <button class="btn btn-secondary btn-sm" onclick="rotatePassword('${escHtml(c.id)}')">轮换密码</button>
                  <button class="btn btn-secondary btn-sm" onclick="deleteCredential('${escHtml(c.id)}')">删除</button>
                </td>
              </tr>`).join('')}
            </tbody>
          </table>`;
      } catch (e) {
        document.getElementById('credentials-table').innerHTML = `<div class="empty-state card">${escHtml(e.message)}</div>`;
      }
    }

    function showCredentialForm() {
      editingCredential = null;
      document.getElementById('credential-form-title').textContent = '新建凭据';
      document.getElementById('cred-id').value = '';
      document.getElementById('cred-id').disabled = false;
      document.getElementById('cred-name').value = '';
      document.getElementById('cred-username').value = '';
      document.getElementById('cred-password').value = '';
      document.getElementById('cred-login-url').value = '';
      document.getElementById('cred-notes').value = '';
      document.getElementById('credential-form').style.display = 'block';
    }

    function hideCredentialForm() {
      document.getElementById('credential-form').style.display = 'none';
    }

    function editCredential(c) {
      editingCredential = c.id;
      document.getElementById('credential-form-title').textContent = `编辑凭据: ${c.name}`;
      document.getElementById('cred-id').value = c.id;
      document.getElementById('cred-id').disabled = true;
      document.getElementById('cred-name').value = c.name;
      document.getElementById('cred-username').value = c.username;
      document.getElementById('cred-password').value = '';
      document.getElementById('cred-login-url').value = c.login_url || '';
      document.getElementById('cred-notes').value = c.notes || '';
      document.getElementById('credential-form').style.display = 'block';
    }

    async function saveCredential() {
      const id = document.getElementById('cred-id').value.trim();
      const name = document.getElementById('cred-name').value.trim();
      const username = document.getElementById('cred-username').value.trim();
      const password = document.getElementById('cred-password').value;
      if (!name || !username) { toast('请填写名称和用户名', 'error'); return; }
      try {
        if (editingCredential) {
          await api(`/credentials/${editingCredential}`, {
            method: 'PUT',
            body: JSON.stringify({
              name,
              username,
              login_url: document.getElementById('cred-login-url').value.trim(),
              notes: document.getElementById('cred-notes').value.trim(),
            }),
          });
          if (password) {
            await api(`/credentials/${editingCredential}/password`, {
              method: 'PUT',
              body: JSON.stringify({ password }),
            });
          }
        } else {
          if (!password) { toast('新建凭据需要填写密码', 'error'); return; }
          await api('/credentials', {
            method: 'POST',
            body: JSON.stringify({
              credential_id: id,
              name,
              username,
              password,
              login_url: document.getElementById('cred-login-url').value.trim(),
              notes: document.getElementById('cred-notes').value.trim(),
            }),
          });
        }
        toast('凭据已保存');
        hideCredentialForm();
        loadCredentials();
        loadCredentialOptions();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function rotatePassword(id) {
      const password = prompt('输入新密码:');
      if (!password) return;
      try {
        await api(`/credentials/${id}/password`, {
          method: 'PUT',
          body: JSON.stringify({ password }),
        });
        toast('密码已轮换');
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function deleteCredential(id) {
      if (!confirm(`删除凭据 ${id}?`)) return;
      try {
        await api(`/credentials/${id}`, { method: 'DELETE' });
        toast('已删除');
        loadCredentials();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    loadStatus();
    switchTab(params.tab || 'connectors');

  Object.assign(window, { rotatePassword, editConnector, deleteCredential, editCredential, switchTab, loadCredentialOptions, loadConnectors, saveConnector, hideConnectorForm, loadStatus, deleteConnector, loadCredentials, showConnectorForm, saveCredential, hideCredentialForm, showCredentialForm, generateTask, runCapture, runCaptureByName });
  return () => { delete window.deleteConnector; delete window.deleteCredential; delete window.editConnector; delete window.editCredential; delete window.generateTask; delete window.hideConnectorForm; delete window.hideCredentialForm; delete window.loadConnectors; delete window.loadCredentialOptions; delete window.loadCredentials; delete window.loadStatus; delete window.rotatePassword; delete window.runCapture; delete window.runCaptureByName; delete window.saveConnector; delete window.saveCredential; delete window.showConnectorForm; delete window.showCredentialForm; delete window.switchTab; };
}
