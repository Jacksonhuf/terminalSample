export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/editor.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let ontology = null;
    let currentName = null;

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
      });
    });

    async function loadOntologyList() {
      const data = await api('/ontologies');
      const sel = document.getElementById('ontology-select');
      sel.innerHTML = '<option value="">选择本体...</option>' +
        data.ontologies.map(o => `<option value="${o.name}">${o.name}</option>`).join('');
      const param = params.name;
      if (param) { sel.value = param; await loadOntology(param); }
    }

    async function switchOntology(name) {
      if (name) await loadOntology(name);
    }

    async function loadOntology(name) {
      try {
        ontology = await api(`/ontologies/${name}`);
        currentName = name;
        document.getElementById('editor-content').style.display = 'block';
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('page-title').textContent = ontology.name;
        document.getElementById('page-subtitle').textContent = ontology.description || '无描述';
        renderAll();
        history.replaceState(null, '', `?name=${name}`);
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    function renderAll() {
      document.getElementById('ont-name').value = ontology.name;
      document.getElementById('ont-version').value = ontology.version;
      document.getElementById('ont-desc').value = ontology.description || '';
      document.getElementById('json-editor').value = JSON.stringify(ontology, null, 2);
      renderObjectTypes();
      renderLinks();
      renderActions();
    }

    function renderObjectTypes() {
      const tbody = document.getElementById('object-types-table');
      tbody.innerHTML = (ontology.object_types || []).map((ot, i) => `
        <tr>
          <td><span class="badge badge-blue">${escHtml(ot.name)}</span></td>
          <td>${escHtml(ot.display_name || '')}</td>
          <td>${(ot.properties || []).map(p => `<span class="badge badge-green">${escHtml(p.name)}:${p.type}</span>`).join(' ')}</td>
          <td>${escHtml(ot.primary_key || 'id')}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteObjectType(${i})">删除</button></td>
        </tr>
      `).join('') || '<tr><td colspan="5" style="color:var(--text-muted)">暂无对象类型</td></tr>';
    }

    function renderLinks() {
      const tbody = document.getElementById('links-table');
      tbody.innerHTML = (ontology.links || []).map((l, i) => `
        <tr>
          <td>${escHtml(l.name)}</td>
          <td><span class="badge badge-blue">${escHtml(l.source_type)}</span></td>
          <td>→ <span class="badge badge-blue">${escHtml(l.target_type)}</span></td>
          <td>${escHtml(l.cardinality || 'many')}</td>
          <td>${escHtml(l.description || '')}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteLink(${i})">删除</button></td>
        </tr>
      `).join('') || '<tr><td colspan="6" style="color:var(--text-muted)">暂无关系</td></tr>';
    }

    function renderActions() {
      const tbody = document.getElementById('actions-table');
      tbody.innerHTML = (ontology.actions || []).map((a, i) => `
        <tr>
          <td>${escHtml(a.name)}</td>
          <td>${escHtml(a.display_name || '')}</td>
          <td><span class="badge badge-blue">${escHtml(a.target_type)}</span></td>
          <td>${a.requires_approval ? '<span class="badge badge-orange">需审批</span>' : '-'}</td>
          <td>${(a.parameters || []).map(p => escHtml(p.name)).join(', ') || '-'}</td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteAction(${i})">删除</button></td>
        </tr>
      `).join('') || '<tr><td colspan="6" style="color:var(--text-muted)">暂无动作</td></tr>';
    }

    function syncFromOverview() {
      ontology.version = document.getElementById('ont-version').value;
      ontology.description = document.getElementById('ont-desc').value;
    }

    async function saveOntology() {
      if (!ontology) return;
      syncFromOverview();
      try {
        await api(`/ontologies/${currentName}`, {
          method: 'PUT',
          body: JSON.stringify(ontology),
        });
        toast('保存成功');
        document.getElementById('json-editor').value = JSON.stringify(ontology, null, 2);
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    function applyJson() {
      try {
        ontology = JSON.parse(document.getElementById('json-editor').value);
        renderAll();
        toast('JSON 已应用，请点击保存写入文件');
      } catch (e) {
        toast('JSON 格式错误: ' + e.message, 'error');
      }
    }

    function showModal(html) {
      document.getElementById('modal-body').innerHTML = html;
      document.getElementById('modal').classList.add('open');
    }

    function hideModal() {
      document.getElementById('modal').classList.remove('open');
    }

    function showAddObjectType() {
      const typeNames = (ontology.object_types || []).map(t => t.name);
      showModal(`
        <h2>添加对象类型</h2>
        <div class="form-group"><label>名称</label><input id="f-name" placeholder="Prototype"></div>
        <div class="form-group"><label>显示名</label><input id="f-display" placeholder="样机"></div>
        <div class="form-group"><label>描述</label><input id="f-desc"></div>
        <div class="form-group"><label>主键</label><input id="f-pk" value="id"></div>
        <div class="form-group"><label>属性 (每行一个: 名称:类型, 如 id:string)</label>
          <textarea id="f-props" rows="4" placeholder="id:string&#10;name:string&#10;status:enum"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" onclick="hideModal()">取消</button>
          <button class="btn btn-primary" onclick="addObjectType()">添加</button>
        </div>
      `);
    }

    function addObjectType() {
      const name = document.getElementById('f-name').value.trim();
      if (!name) return toast('请输入名称', 'error');
      const props = (document.getElementById('f-props').value || '').split('\n').filter(Boolean).map(line => {
        const [n, t = 'string'] = line.split(':').map(s => s.trim());
        const p = { name: n, type: t, required: true };
        if (t === 'enum') p.enum_values = [];
        return p;
      });
      ontology.object_types.push({
        name,
        display_name: document.getElementById('f-display').value,
        description: document.getElementById('f-desc').value,
        primary_key: document.getElementById('f-pk').value || 'id',
        properties: props,
      });
      hideModal();
      renderObjectTypes();
      toast('已添加，记得保存');
    }

    function deleteObjectType(i) {
      if (!confirm('确认删除?')) return;
      ontology.object_types.splice(i, 1);
      renderObjectTypes();
    }

    function showAddLink() {
      const types = (ontology.object_types || []).map(t => t.name);
      const opts = types.map(t => `<option value="${t}">${t}</option>`).join('');
      showModal(`
        <h2>添加关系</h2>
        <div class="form-group"><label>名称</label><input id="f-name" placeholder="belongs_to"></div>
        <div class="form-row">
          <div class="form-group"><label>源类型</label><select id="f-source">${opts}</select></div>
          <div class="form-group"><label>目标类型</label><select id="f-target">${opts}</select></div>
        </div>
        <div class="form-group"><label>描述</label><input id="f-desc"></div>
        <div class="modal-actions">
          <button class="btn btn-secondary" onclick="hideModal()">取消</button>
          <button class="btn btn-primary" onclick="addLink()">添加</button>
        </div>
      `);
    }

    function addLink() {
      ontology.links.push({
        name: document.getElementById('f-name').value.trim(),
        source_type: document.getElementById('f-source').value,
        target_type: document.getElementById('f-target').value,
        cardinality: 'many',
        description: document.getElementById('f-desc').value,
      });
      hideModal();
      renderLinks();
      toast('已添加，记得保存');
    }

    function deleteLink(i) {
      if (!confirm('确认删除?')) return;
      ontology.links.splice(i, 1);
      renderLinks();
    }

    function showAddAction() {
      const types = (ontology.object_types || []).map(t => t.name);
      const opts = types.map(t => `<option value="${t}">${t}</option>`).join('');
      showModal(`
        <h2>添加动作</h2>
        <div class="form-group"><label>名称</label><input id="f-name" placeholder="ReservePrototype"></div>
        <div class="form-group"><label>显示名</label><input id="f-display" placeholder="预约样机"></div>
        <div class="form-group"><label>目标类型</label><select id="f-target">${opts}</select></div>
        <div class="form-group"><label>关键词 (逗号分隔)</label><input id="f-keywords" placeholder="预约,reserve"></div>
        <div class="form-group"><label><input type="checkbox" id="f-approval"> 需要审批</label></div>
        <div class="form-group"><label>参数 (每行: 名称:类型)</label>
          <textarea id="f-params" rows="3" placeholder="person_id:string"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" onclick="hideModal()">取消</button>
          <button class="btn btn-primary" onclick="addAction()">添加</button>
        </div>
      `);
    }

    function addAction() {
      const params = (document.getElementById('f-params').value || '').split('\n').filter(Boolean).map(line => {
        const [n, t = 'string'] = line.split(':').map(s => s.trim());
        return { name: n, type: t, required: true };
      });
      ontology.actions.push({
        name: document.getElementById('f-name').value.trim(),
        display_name: document.getElementById('f-display').value,
        target_type: document.getElementById('f-target').value,
        requires_approval: document.getElementById('f-approval').checked,
        keywords: document.getElementById('f-keywords').value.split(',').map(s => s.trim()).filter(Boolean),
        parameters: params,
      });
      hideModal();
      renderActions();
      toast('已添加，记得保存');
    }

    function deleteAction(i) {
      if (!confirm('确认删除?')) return;
      ontology.actions.splice(i, 1);
      renderActions();
    }

    function viewGraph() {
      if (currentName) window.location.href = `/visualize?name=${currentName}`;
    }

    loadOntologyList();

  Object.assign(window, { deleteAction, renderAll, deleteLink, renderActions, addAction, deleteObjectType, applyJson, switchOntology, showAddLink, viewGraph, addObjectType, hideModal, loadOntology, showAddAction, saveOntology, syncFromOverview, renderLinks, showAddObjectType, showModal, addLink, renderObjectTypes, loadOntologyList });
  return () => { delete window.addAction; delete window.addLink; delete window.addObjectType; delete window.applyJson; delete window.deleteAction; delete window.deleteLink; delete window.deleteObjectType; delete window.hideModal; delete window.loadOntology; delete window.loadOntologyList; delete window.renderActions; delete window.renderAll; delete window.renderLinks; delete window.renderObjectTypes; delete window.saveOntology; delete window.showAddAction; delete window.showAddLink; delete window.showAddObjectType; delete window.showModal; delete window.switchOntology; delete window.syncFromOverview; delete window.viewGraph; };
}
