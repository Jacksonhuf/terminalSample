export async function mount(container, params, ctx) {
  const html = await fetch('/static/partials/graph.html').then(r => r.text());
  container.innerHTML = html;
  const navigate = ctx.navigate;
  const escAttr = ctx.escAttr || ((s) => String(s).replace(/"/g, '&quot;'));
  let network = null;

    async function init() {
      const data = await api('/ontologies');
      const sel = document.getElementById('ontology-select');
      sel.innerHTML = '<option value="">选择本体...</option>' +
        data.ontologies.map(o => `<option value="${o.name}">${o.name}</option>`).join('');
      const param = params.name;
      if (param) { sel.value = param; await loadGraph(param); }
    }

    async function loadGraph(name) {
      if (!name) return;
      try {
        const data = await api(`/ontologies/${name}/graph`);
        document.getElementById('page-title').textContent = `${name} 图谱`;
        document.getElementById('page-subtitle').textContent =
          `${data.stats.object_types} 对象类型 · ${data.stats.links} 关系 · ${data.stats.actions} 动作`;
        document.getElementById('edit-link').onclick = () => navigate(`/admin/ontologies/${name}/edit`);
        document.getElementById('graph-stats').textContent =
          `节点: ${data.nodes.length} | 边: ${data.edges.length}`;
        history.replaceState(null, '', `?name=${name}`);

        const nodes = new vis.DataSet(data.nodes.map(n => ({
          id: n.id,
          label: n.label,
          group: n.group,
          title: n.title + (n.property_count ? `\n${n.property_count} 个属性` : ''),
          font: { color: '#e8eaf0', size: 14 },
          shape: n.type === 'action' ? 'diamond' : 'box',
          color: n.type === 'action'
            ? { background: '#2d2050', border: '#a78bfa', highlight: { background: '#3d2e6a', border: '#c4b5fd' } }
            : { background: '#1e3a5f', border: '#5b8def', highlight: { background: '#264a73', border: '#7aaef7' } },
        })));

        const edges = new vis.DataSet(data.edges.map(e => ({
          id: e.id,
          from: e.from,
          to: e.to,
          label: e.label,
          title: e.title || e.label,
          arrows: e.arrows || 'to',
          dashes: e.dashes || false,
          font: { color: '#8b90a5', size: 11, strokeWidth: 0 },
          color: { color: '#4a5068', highlight: '#5b8def' },
        })));

        const container = document.getElementById('graph-container');
        if (network) network.destroy();

        network = new vis.Network(container, { nodes, edges }, {
          layout: {
            improvedLayout: true,
            hierarchical: { enabled: false },
          },
          physics: {
            stabilization: { iterations: 150 },
            barnesHut: { gravitationalConstant: -3000, springLength: 180 },
          },
          interaction: {
            hover: true,
            tooltipDelay: 100,
            navigationButtons: true,
            keyboard: true,
          },
          nodes: { borderWidth: 2, margin: 10 },
          edges: { smooth: { type: 'continuous' } },
        });

        network.on('click', params => {
          if (params.nodes.length) {
            const nodeId = params.nodes[0];
            const node = data.nodes.find(n => n.id === nodeId);
            if (node) {
              document.getElementById('graph-stats').textContent =
                `选中: ${node.label} (${node.type}) — 双击可在编辑器中修改`;
            }
          }
        });

        network.on('doubleClick', params => {
          if (params.nodes.length) {
            navigate(`/admin/ontologies/${name}/edit`);
          }
        });

      } catch (e) {
        toast(e.message, 'error');
      }
    }

    init();
    const editLink = document.getElementById('edit-link');
    if (editLink) {
      editLink.addEventListener('click', (e) => {
        e.preventDefault();
        const name = document.getElementById('ontology-select').value;
        if (name) navigate(`/admin/ontologies/${name}/edit`);
      });
    }

  Object.assign(window, { init, loadGraph });
  return () => { delete window.init; delete window.loadGraph; };
}
