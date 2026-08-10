export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/ontologies.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  async function loadOntologies() {
      try {
        const data = await api('/ontologies');
        document.getElementById('dir-info').textContent = `目录: ${data.directory}`;
        const list = document.getElementById('ontology-list');

        if (!data.ontologies.length) {
          list.innerHTML = `<div class="empty-state card" style="grid-column:1/-1">
            <h3>暂无本体</h3>
            <p>点击「新建本体」开始定义你的第一个 Ontology</p>
          </div>`;
          return;
        }

        list.innerHTML = data.ontologies.map(o => `
          <div class="card ontology-card" onclick="openOntology('${o.name}')">
            <h3>${escHtml(o.name)} <span class="badge badge-blue">v${escHtml(o.version)}</span></h3>
            <p>${escHtml(o.description || '无描述')}</p>
            <div class="stats">
              <span class="stat"><strong>${o.object_type_count}</strong> 对象类型</span>
              <span class="stat"><strong>${o.link_count}</strong> 关系</span>
              <span class="stat"><strong>${o.action_count}</strong> 动作</span>
            </div>
            <div style="margin-top:12px;display:flex;gap:8px">
              <a href="#" onclick="event.stopPropagation();navigate('/admin/ontologies/${escAttr(o.name)}/edit');return false;" class="btn btn-secondary btn-sm">编辑</a>
              <a href="#" onclick="event.stopPropagation();navigate('/admin/ontologies/${escAttr(o.name)}/graph');return false;" class="btn btn-secondary btn-sm">可视化</a>
              <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteOntology('${escAttr(o.name)}')">删除</button>
            </div>
          </div>
        `).join('');
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    function openOntology(name) { navigate(`/admin/ontologies/${name}/edit`); }

    function showCreateModal() {
      document.getElementById('create-modal').classList.add('open');
    }

    function hideCreateModal() {
      document.getElementById('create-modal').classList.remove('open');
    }

    function showImportModal() {
      document.getElementById('import-file').value = '';
      document.getElementById('import-overwrite').checked = false;
      document.getElementById('import-modal').classList.add('open');
    }

    function hideImportModal() {
      document.getElementById('import-modal').classList.remove('open');
    }

    function downloadImportTemplate() {
      window.location.href = '/api/ontologies/import/template';
    }

    async function importOntology() {
      const input = document.getElementById('import-file');
      const file = input.files?.[0];
      if (!file) return toast('请选择 Excel 文件', 'error');

      const overwrite = document.getElementById('import-overwrite').checked;
      const form = new FormData();
      form.append('file', file);

      try {
        const res = await fetch(`/api/ontologies/import?overwrite=${overwrite ? 'true' : 'false'}`, {
          method: 'POST',
          body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.detail || res.statusText);
        }
        hideImportModal();
        toast(`导入成功：${data.ontology.name}`);
        loadOntologies();
        navigate(`/admin/ontologies/${data.ontology.name}/edit`);
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function createOntology() {
      const name = document.getElementById('new-name').value.trim();
      if (!name) return toast('请输入名称', 'error');
      try {
        await api('/ontologies', {
          method: 'POST',
          body: JSON.stringify({
            name,
            description: document.getElementById('new-desc').value,
            version: document.getElementById('new-version').value || '1.0',
          }),
        });
        hideCreateModal();
        toast('本体创建成功');
        navigate(`/admin/ontologies/${name}/edit`);
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    async function deleteOntology(name) {
      if (!confirm(`确认删除本体「${name}」？此操作不可恢复。`)) return;
      try {
        await api(`/ontologies/${encodeURIComponent(name)}`, { method: 'DELETE' });
        toast('本体已删除');
        loadOntologies();
      } catch (e) {
        toast(e.message, 'error');
      }
    }

    loadOntologies();

  Object.assign(window, {
    createOntology, deleteOntology, downloadImportTemplate, hideCreateModal,
    hideImportModal, importOntology, loadOntologies, openOntology,
    showCreateModal, showImportModal,
  });
  return () => {
    delete window.createOntology; delete window.deleteOntology; delete window.downloadImportTemplate;
    delete window.hideCreateModal; delete window.hideImportModal; delete window.importOntology;
    delete window.loadOntologies; delete window.openOntology; delete window.showCreateModal;
    delete window.showImportModal;
  };
}
