export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/mappings.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let editingProfileId = null;
    let sourceFields = [];
    let targetProperties = [];

    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById('panel-' + name).classList.add('active');
      if (name === 'discover') loadStaging();
      if (name === 'configure') { loadConnectors(); loadProfiles(); }
      if (name === 'sync') loadSyncRuns();
    }

    async function loadStaging() {
      const data = await api('/mappings/staging');
      const rows = data.summaries || [];
      if (!rows.length) {
        document.getElementById('staging-table').innerHTML = '<p class="empty">暂无暂存数据。请先在「数据连接」完成采集并 ingest。</p>';
        return;
      }
      let html = '<table><thead><tr><th>连接器</th><th>记录类型</th><th>总数</th><th>未同步</th><th>已同步</th><th>样本字段</th><th>操作</th></tr></thead><tbody>';
      for (const r of rows) {
        const fields = (r.sample_fields || []).slice(0, 8).join(', ');
        html += `<tr>
          <td>${escHtml(r.connector_name)}</td>
          <td><code>${escHtml(r.record_type)}</code></td>
          <td>${r.total}</td>
          <td>${r.unsynced}</td>
          <td>${r.synced}</td>
          <td class="muted">${escHtml(fields)}</td>
          <td><button class="btn btn-secondary btn-sm" onclick="createMappingFromStaging('${escAttr(r.connector_name)}','${escAttr(r.record_type)}')">配置映射</button></td>
        </tr>`;
      }
      html += '</tbody></table>';
      document.getElementById('staging-table').innerHTML = html;
    }

    async function loadConnectors() {
      const data = await api('/connectors');
      const sel = document.getElementById('p-connector');
      sel.innerHTML = (data.connectors || []).map(c => `<option value="${escAttr(c.name)}">${escHtml(c.name)}</option>`).join('');
    }

    async function loadProfiles() {
      const data = await api('/mappings/profiles');
      const rows = data.profiles || [];
      if (!rows.length) {
        document.getElementById('profiles-table').innerHTML = '<p class="empty">暂无映射配置。</p>';
        return;
      }
      let html = '<table><thead><tr><th>名称</th><th>连接器</th><th>记录类型</th><th>目标</th><th>状态</th><th>操作</th></tr></thead><tbody>';
      for (const p of rows) {
        html += `<tr>
          <td>${escHtml(p.name)}</td>
          <td>${escHtml(p.connector_name)}</td>
          <td><code>${escHtml(p.record_type)}</code></td>
          <td>${escHtml(p.ontology_name)}.${escHtml(p.object_type)}</td>
          <td><span class="badge">${escHtml(p.status)}</span></td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick='editProfile(${JSON.stringify(p).replace(/'/g, "&#39;")})'>编辑</button>
            ${p.status !== 'active' ? `<button class="btn btn-primary btn-sm" onclick="activateProfile('${escAttr(p.id)}')">发布</button>` : ''}
            ${p.status === 'active' ? `<button class="btn btn-primary btn-sm" onclick="runSync('${escAttr(p.id)}', false)">同步</button>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="deleteProfile('${escAttr(p.id)}')">删除</button>
          </td>
        </tr>`;
      }
      html += '</tbody></table>';
      document.getElementById('profiles-table').innerHTML = html;
    }

    async function loadSyncRuns() {
      const data = await api('/mappings/sync-runs');
      const rows = data.runs || [];
      if (!rows.length) {
        document.getElementById('sync-runs-table').innerHTML = '<p class="empty">暂无同步记录。</p>';
        return;
      }
      let html = '<table><thead><tr><th>时间</th><th>连接器</th><th>记录类型</th><th>状态</th><th>处理</th><th>成功</th><th>失败</th><th>重跑</th></tr></thead><tbody>';
      for (const r of rows) {
        html += `<tr>
          <td>${escHtml(r.started_at)}</td>
          <td>${escHtml(r.connector_name)}</td>
          <td><code>${escHtml(r.record_type)}</code></td>
          <td>${escHtml(r.status)}</td>
          <td>${r.records_processed}</td>
          <td>${r.records_synced}</td>
          <td>${r.records_failed}</td>
          <td>${r.resync ? '是' : '否'}</td>
        </tr>`;
      }
      html += '</tbody></table>';
      document.getElementById('sync-runs-table').innerHTML = html;
    }

    function showProfileForm() {
      editingProfileId = null;
      document.getElementById('profile-form-title').textContent = '新建映射';
      document.getElementById('profile-form').style.display = 'block';
      document.getElementById('p-name').value = '';
      document.getElementById('p-status').value = 'draft';
      document.getElementById('p-record-type').value = '';
      document.getElementById('preview-output').style.display = 'none';
      loadConnectors().then(onConnectorChange);
    }

    function hideProfileForm() {
      document.getElementById('profile-form').style.display = 'none';
      editingProfileId = null;
    }

    async function createMappingFromStaging(connector, recordType) {
      switchTab('configure');
      showProfileForm();
      await loadConnectors();
      document.getElementById('p-connector').value = connector;
      document.getElementById('p-record-type').value = recordType;
      document.getElementById('p-name').value = `${connector} → ${recordType}`;
      await onConnectorChange();
    }

    async function onConnectorChange() {
      const connector = document.getElementById('p-connector').value;
      const recordType = document.getElementById('p-record-type').value;
      if (!connector || !recordType) return;
      try {
        const data = await api(`/mappings/staging/${encodeURIComponent(connector)}/${encodeURIComponent(recordType)}/samples`);
        sourceFields = data.fields || [];
        if (!editingProfileId && sourceFields.length) {
          await loadObjectTypes();
          autoSuggestRules();
        } else {
          renderFieldRules();
        }
      } catch (e) {
        sourceFields = [];
        renderFieldRules();
      }
    }

    async function loadObjectTypes() {
      const ontology = document.getElementById('p-ontology').value;
      const data = await api(`/mappings/ontologies/${encodeURIComponent(ontology)}/object-types`);
      const sel = document.getElementById('p-object-type');
      sel.innerHTML = (data.object_types || []).map(t => `<option value="${escAttr(t.name)}">${escHtml(t.display_name || t.name)}</option>`).join('');
      const selected = sel.value;
      const ot = (data.object_types || []).find(t => t.name === selected);
      targetProperties = ot ? ot.properties.map(p => p.name) : [];
      renderFieldRules();
    }

    function autoSuggestRules() {
      const container = document.getElementById('field-rules');
      container.innerHTML = '';
      for (const src of sourceFields) {
        const target = targetProperties.includes(src) ? src : '';
        addFieldRule(src, target);
      }
    }

    function renderFieldRules() {
      const container = document.getElementById('field-rules');
      if (!container.children.length) {
        addFieldRule();
      }
    }

    function addFieldRule(source = '', target = '') {
      const container = document.getElementById('field-rules');
      const row = document.createElement('div');
      row.className = 'form-grid';
      row.style.marginBottom = '8px';
      const srcOpts = sourceFields.map(f => `<option value="${escAttr(f)}" ${f===source?'selected':''}>${escHtml(f)}</option>`).join('');
      const tgtOpts = targetProperties.map(f => `<option value="${escAttr(f)}" ${f===target?'selected':''}>${escHtml(f)}</option>`).join('');
      row.innerHTML = `
        <label>源字段<select class="rule-source"><option value="">（自定义）</option>${srcOpts}</select></label>
        <label>目标属性<select class="rule-target"><option value="">（选择）</option>${tgtOpts}</select></label>
        <label>转换<select class="rule-transform"><option value="direct">direct</option><option value="default">default</option><option value="map">map</option></select></label>
        <label><button type="button" class="btn btn-secondary btn-sm" onclick="this.closest('.form-grid').remove()">删除</button></label>
      `;
      if (source && !sourceFields.includes(source)) {
        row.querySelector('.rule-source').innerHTML += `<option value="${escAttr(source)}" selected>${escHtml(source)}</option>`;
      }
      if (target) row.querySelector('.rule-target').value = target;
      container.appendChild(row);
    }

    function collectFieldRules() {
      const rules = [];
      document.querySelectorAll('#field-rules .form-grid').forEach(row => {
        const source = row.querySelector('.rule-source').value.trim();
        const target = row.querySelector('.rule-target').value.trim();
        const ttype = row.querySelector('.rule-transform').value;
        if (source && target) {
          rules.push({ source, target, transform: { type: ttype, mapping: {}, default: null } });
        }
      });
      return rules;
    }

    function collectProfileBody() {
      return {
        name: document.getElementById('p-name').value.trim(),
        connector_name: document.getElementById('p-connector').value,
        record_type: document.getElementById('p-record-type').value.trim(),
        ontology_name: document.getElementById('p-ontology').value,
        object_type: document.getElementById('p-object-type').value,
        source_id_field: document.getElementById('p-source-id').value.trim() || 'id',
        id_field: document.getElementById('p-id-field').value.trim() || 'id',
        field_rules: collectFieldRules(),
        status: document.getElementById('p-status').value,
      };
    }

    async function saveProfile() {
      const body = collectProfileBody();
      if (!body.name || !body.record_type || !body.field_rules.length) {
        alert('请填写名称、记录类型和至少一条字段映射');
        return;
      }
      if (editingProfileId) {
        await api(`/mappings/profiles/${editingProfileId}`, { method: 'PUT', body: JSON.stringify(body) });
      } else {
        await api('/mappings/profiles', { method: 'POST', body: JSON.stringify(body) });
      }
      hideProfileForm();
      loadProfiles();
    }

    async function editProfile(p) {
      editingProfileId = p.id;
      document.getElementById('profile-form-title').textContent = '编辑映射';
      document.getElementById('profile-form').style.display = 'block';
      await loadConnectors();
      document.getElementById('p-name').value = p.name;
      document.getElementById('p-status').value = p.status;
      document.getElementById('p-connector').value = p.connector_name;
      document.getElementById('p-record-type').value = p.record_type;
      document.getElementById('p-ontology').value = p.ontology_name;
      document.getElementById('p-source-id').value = p.source_id_field;
      document.getElementById('p-id-field').value = p.id_field;
      await onConnectorChange();
      await loadObjectTypes();
      document.getElementById('p-object-type').value = p.object_type;
      const container = document.getElementById('field-rules');
      container.innerHTML = '';
      for (const rule of (p.field_rules || [])) {
        addFieldRule(rule.source, rule.target);
      }
    }

    async function previewProfile() {
      let profileId = editingProfileId;
      if (!profileId) {
        const created = await api('/mappings/profiles', { method: 'POST', body: JSON.stringify({ ...collectProfileBody(), status: 'draft' }) });
        profileId = created.id;
        editingProfileId = profileId;
      } else {
        await api(`/mappings/profiles/${profileId}`, { method: 'PUT', body: JSON.stringify(collectProfileBody()) });
      }
      const result = await api(`/mappings/profiles/${profileId}/preview?limit=5`, { method: 'POST' });
      document.getElementById('preview-output').style.display = 'block';
      document.getElementById('preview-output').textContent = JSON.stringify(result.previews, null, 2);
    }

    async function activateProfile(id) {
      await api(`/mappings/profiles/${id}/activate`, { method: 'POST' });
      loadProfiles();
    }

    async function runSync(id, resync) {
      try {
        const result = await api(`/mappings/profiles/${id}/sync`, { method: 'POST', body: JSON.stringify({ resync }) });
        alert(`同步完成：成功 ${result.synced}，失败 ${result.failed}`);
        loadSyncRuns();
        switchTab({'discover':'discover','profiles':'configure','sync':'sync'}[params.tab || 'discover'] || 'discover');
      } catch (e) {
        alert('同步失败：' + e.message);
      }
    }

    async function deleteProfile(id) {
      if (!confirm('确定删除此映射？')) return;
      await api(`/mappings/profiles/${id}`, { method: 'DELETE' });
      loadProfiles();
    }

    document.getElementById('p-record-type').addEventListener('change', onConnectorChange);
    switchTab({'discover':'discover','profiles':'configure','sync':'sync'}[params.tab || 'discover'] || 'discover');

  Object.assign(window, { saveProfile, runSync, showProfileForm, deleteProfile, loadStaging, editProfile, switchTab, renderFieldRules, addFieldRule, activateProfile, collectProfileBody, loadConnectors, loadObjectTypes, loadSyncRuns, createMappingFromStaging, previewProfile, collectFieldRules, hideProfileForm, autoSuggestRules, onConnectorChange, loadProfiles });
  return () => { delete window.activateProfile; delete window.addFieldRule; delete window.autoSuggestRules; delete window.collectFieldRules; delete window.collectProfileBody; delete window.createMappingFromStaging; delete window.deleteProfile; delete window.editProfile; delete window.hideProfileForm; delete window.loadConnectors; delete window.loadObjectTypes; delete window.loadProfiles; delete window.loadStaging; delete window.loadSyncRuns; delete window.onConnectorChange; delete window.previewProfile; delete window.renderFieldRules; delete window.runSync; delete window.saveProfile; delete window.showProfileForm; delete window.switchTab; };
}
