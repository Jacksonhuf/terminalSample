export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/llm.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let editingProfileId = null;
    const profileCache = {};

    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + name).classList.add('active');
      if (name === 'profiles') switchTab(params.tab || 'profiles');
      if (name === 'proxy') loadProxy();
    }

    async function loadStatus() {
      try {
        const active = await api('/llm/active');
        if (!active.configured) {
          document.getElementById('status-info').textContent = '未配置存储路径，请使用 --store-path 启动';
          return;
        }
        const name = active.active ? active.active.name : '（未配置默认模型）';
        const proxyNote = active.active
          ? (active.proxy_will_be_used ? '将使用代理' : '不走代理/直连')
          : '';
        document.getElementById('status-info').textContent = `当前默认: ${name} ${proxyNote}`;
      } catch (e) {
        document.getElementById('status-info').textContent = e.message;
      }
    }

    async function loadCredentialOptions() {
      const select = document.getElementById('p-api-key-ref');
      const current = select.value;
      select.innerHTML = '<option value="">（无 / 内网免鉴权）</option>';
      try {
        const data = await api('/credentials');
        if (!data.configured) return;
        data.credentials.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.id;
          opt.textContent = `${c.name} (${c.id})`;
          select.appendChild(opt);
        });
        select.value = current;
      } catch (_) {}
    }

    async function loadProfiles() {
      await loadCredentialOptions();
      try {
        const data = await api('/llm/profiles');
        if (!data.configured) {
          document.getElementById('profiles-table').innerHTML = `<div class="empty-state card">${escHtml(data.message || '')}</div>`;
          return;
        }
        data.profiles.forEach(p => { profileCache[p.id] = p; });
        if (!data.profiles.length) {
          document.getElementById('profiles-table').innerHTML = '<div class="empty-state card">暂无模型配置</div>';
          return;
        }
        document.getElementById('profiles-table').innerHTML = `
          <table class="data-table">
            <thead><tr>
              <th>名称</th><th>Model</th><th>Base URL</th><th>Planner</th><th>代理</th><th>默认</th><th>操作</th>
            </tr></thead>
            <tbody>
              ${data.profiles.map(p => `<tr>
                <td>${escHtml(p.name)}</td>
                <td>${escHtml(p.model)}</td>
                <td>${escHtml(p.base_url)}</td>
                <td>${escHtml(p.planner_mode)}</td>
                <td>${escHtml(p.proxy_mode)}</td>
                <td>${p.is_default ? '✓' : ''}</td>
                <td>
                  <button class="btn btn-secondary btn-sm" onclick="editProfile('${escHtml(p.id)}')">编辑</button>
                  <button class="btn btn-secondary btn-sm" onclick="testProfileById('${escHtml(p.id)}')">测试</button>
                  <button class="btn btn-secondary btn-sm" onclick="deleteProfile('${escHtml(p.id)}')">删除</button>
                </td>
              </tr>`).join('')}
            </tbody>
          </table>`;
      } catch (e) {
        document.getElementById('profiles-table').innerHTML = `<div class="empty-state card">${escHtml(e.message)}</div>`;
      }
      loadStatus();
    }

    function showProfileForm() {
      editingProfileId = null;
      document.getElementById('profile-form-title').textContent = '新建模型';
      document.getElementById('p-id').value = '';
      document.getElementById('p-id').disabled = false;
      document.getElementById('p-name').value = '';
      document.getElementById('p-model').value = '';
      document.getElementById('p-base-url').value = '';
      document.getElementById('p-api-key-ref').value = '';
      document.getElementById('p-planner-mode').value = 'auto';
      document.getElementById('p-proxy-mode').value = 'bypass';
      document.getElementById('p-temperature').value = '0.2';
      document.getElementById('p-timeout').value = '60';
      document.getElementById('p-default').checked = false;
      document.getElementById('p-enabled').checked = true;
      document.getElementById('test-output').style.display = 'none';
      document.getElementById('profile-form').style.display = 'block';
    }

    function hideProfileForm() { document.getElementById('profile-form').style.display = 'none'; }

    function editProfile(id) {
      const p = profileCache[id];
      if (!p) return;
      editingProfileId = id;
      document.getElementById('profile-form-title').textContent = `编辑: ${p.name}`;
      document.getElementById('p-id').value = p.id;
      document.getElementById('p-id').disabled = true;
      document.getElementById('p-name').value = p.name;
      document.getElementById('p-provider').value = p.provider;
      document.getElementById('p-model').value = p.model;
      document.getElementById('p-base-url').value = p.base_url;
      document.getElementById('p-api-key-ref').value = p.api_key_ref || '';
      document.getElementById('p-planner-mode').value = p.planner_mode;
      document.getElementById('p-proxy-mode').value = p.proxy_mode;
      document.getElementById('p-temperature').value = p.temperature;
      document.getElementById('p-timeout').value = p.timeout_sec;
      document.getElementById('p-default').checked = p.is_default;
      document.getElementById('p-enabled').checked = p.enabled;
      document.getElementById('profile-form').style.display = 'block';
    }

    function profilePayload() {
      return {
        id: document.getElementById('p-id').value.trim(),
        name: document.getElementById('p-name').value.trim(),
        provider: document.getElementById('p-provider').value,
        model: document.getElementById('p-model').value.trim(),
        base_url: document.getElementById('p-base-url').value.trim(),
        api_key_ref: document.getElementById('p-api-key-ref').value,
        planner_mode: document.getElementById('p-planner-mode').value,
        proxy_mode: document.getElementById('p-proxy-mode').value,
        temperature: parseFloat(document.getElementById('p-temperature').value || '0.2'),
        timeout_sec: parseInt(document.getElementById('p-timeout').value || '60', 10),
        is_default: document.getElementById('p-default').checked,
        enabled: document.getElementById('p-enabled').checked,
        max_tokens: 4096,
      };
    }

    async function saveProfile() {
      const payload = profilePayload();
      if (!payload.name || !payload.model) { toast('请填写名称和 Model', 'error'); return; }
      try {
        if (editingProfileId) {
          await api(`/llm/profiles/${editingProfileId}`, { method: 'PUT', body: JSON.stringify(payload) });
        } else {
          await api('/llm/profiles', { method: 'POST', body: JSON.stringify(payload) });
        }
        toast('已保存');
        hideProfileForm();
        switchTab(params.tab || 'profiles');
      } catch (e) { toast(e.message, 'error'); }
    }

    async function deleteProfile(id) {
      if (!confirm(`删除模型 ${id}?`)) return;
      try {
        await api(`/llm/profiles/${id}`, { method: 'DELETE' });
        toast('已删除');
        switchTab(params.tab || 'profiles');
      } catch (e) { toast(e.message, 'error'); }
    }

    async function testProfile() {
      const id = editingProfileId || document.getElementById('p-id').value.trim();
      if (!id) { toast('请先保存模型', 'error'); return; }
      await testProfileById(id);
    }

    async function testProfileById(id) {
      try {
        const result = await api(`/llm/profiles/${id}/test`, { method: 'POST' });
        const out = document.getElementById('test-output');
        out.style.display = 'block';
        out.textContent = JSON.stringify(result, null, 2);
        toast(result.success ? '连接成功' : result.message, result.success ? 'success' : 'error');
      } catch (e) { toast(e.message, 'error'); }
    }

    async function loadProxy() {
      try {
        const data = await api('/llm/proxy');
        if (!data.configured) return;
        document.getElementById('proxy-enabled').checked = !!data.enabled;
        document.getElementById('proxy-http').value = data.http_proxy || '';
        document.getElementById('proxy-https').value = data.https_proxy || '';
        document.getElementById('proxy-no-proxy').value = data.no_proxy || '';
        document.getElementById('proxy-internal-bypass').checked = data.internal_bypass_proxy !== false;
      } catch (e) { toast(e.message, 'error'); }
    }

    async function saveProxy() {
      const payload = {
        enabled: document.getElementById('proxy-enabled').checked,
        http_proxy: document.getElementById('proxy-http').value.trim(),
        https_proxy: document.getElementById('proxy-https').value.trim(),
        no_proxy: document.getElementById('proxy-no-proxy').value.trim(),
        internal_bypass_proxy: document.getElementById('proxy-internal-bypass').checked,
      };
      try {
        await api('/llm/proxy', { method: 'PUT', body: JSON.stringify(payload) });
        toast('代理配置已保存');
        loadStatus();
      } catch (e) { toast(e.message, 'error'); }
    }

    switchTab(params.tab || 'profiles');

  Object.assign(window, { profilePayload, testProfile, testProfileById, loadProxy, saveProxy, hideProfileForm, saveProfile, editProfile, switchTab, loadCredentialOptions, loadProfiles, loadStatus, deleteProfile, showProfileForm });
  return () => { delete window.deleteProfile; delete window.editProfile; delete window.hideProfileForm; delete window.loadCredentialOptions; delete window.loadProfiles; delete window.loadProxy; delete window.loadStatus; delete window.profilePayload; delete window.saveProfile; delete window.saveProxy; delete window.showProfileForm; delete window.switchTab; delete window.testProfile; delete window.testProfileById; };
}
