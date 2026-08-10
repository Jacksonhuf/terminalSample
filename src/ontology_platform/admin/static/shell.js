/** Unified admin shell: sidebar navigation + client-side routing. */

const MENU = [
  {
    group: '本体建模',
    items: [
      { label: '本体列表', path: '/admin/ontologies' },
      { label: '本体编辑器', path: '/admin/ontologies/edit' },
      { label: '关系可视化', path: '/admin/ontologies/graph' },
    ],
  },
  {
    group: '数据集成',
    items: [
      { label: '数据连接', path: '/admin/integration/connectors' },
      { label: '凭据库', path: '/admin/integration/credentials' },
      { label: '映射 · 浏览', path: '/admin/integration/mappings/discover' },
      { label: '映射 · 配置', path: '/admin/integration/mappings/profiles' },
      { label: '映射 · 同步', path: '/admin/integration/mappings/sync' },
    ],
  },
  {
    group: '运营中心',
    items: [
      { label: '样机看板', path: '/admin/operations/dashboard' },
      { label: '审批工作台', path: '/admin/operations/approvals' },
      { label: '审计日志', path: '/admin/operations/audit' },
      { label: '消息记录', path: '/admin/operations/messages' },
      { label: '跟催任务', path: '/admin/operations/outreach' },
    ],
  },
  {
    group: '系统设置',
    items: [
      { label: 'LLM 配置', path: '/admin/settings/llm' },
      { label: '网络与代理', path: '/admin/settings/proxy' },
    ],
  },
];

const ROUTES = [
  { pattern: /^\/admin\/?$/, redirect: '/admin/ontologies' },
  { pattern: /^\/admin\/ontologies$/, module: 'ontologies', title: '本体列表', breadcrumb: ['本体建模', '本体列表'] },
  { pattern: /^\/admin\/ontologies\/edit$/, module: 'editor', title: '本体编辑器', breadcrumb: ['本体建模', '编辑器'] },
  { pattern: /^\/admin\/ontologies\/([^/]+)\/edit$/, module: 'editor', title: '本体编辑器', breadcrumb: ['本体建模', '编辑器'], params: (m) => ({ name: m[1] }) },
  { pattern: /^\/admin\/ontologies\/graph$/, module: 'graph', title: '关系可视化', breadcrumb: ['本体建模', '可视化'] },
  { pattern: /^\/admin\/ontologies\/([^/]+)\/graph$/, module: 'graph', title: '关系可视化', breadcrumb: ['本体建模', '可视化'], params: (m) => ({ name: m[1] }) },
  { pattern: /^\/admin\/integration\/connectors$/, module: 'connectors', title: '数据连接', breadcrumb: ['数据集成', '数据连接'], params: () => ({ tab: 'connectors' }) },
  { pattern: /^\/admin\/integration\/credentials$/, module: 'connectors', title: '凭据库', breadcrumb: ['数据集成', '凭据库'], params: () => ({ tab: 'credentials' }) },
  { pattern: /^\/admin\/integration\/mappings\/(discover|profiles|sync)$/, module: 'mappings', title: '数据映射', breadcrumb: ['数据集成', '数据映射'], params: (m) => ({ tab: m[1] }) },
  { pattern: /^\/admin\/operations\/(dashboard|audit|approvals|messages|outreach)$/, module: 'operations', title: '运营中心', breadcrumb: ['运营中心'], params: (m) => ({ tab: m[1] }) },
  { pattern: /^\/admin\/settings\/llm$/, module: 'llm', title: 'LLM 配置', breadcrumb: ['系统设置', 'LLM 配置'], params: () => ({ tab: 'profiles' }) },
  { pattern: /^\/admin\/settings\/proxy$/, module: 'llm', title: '网络与代理', breadcrumb: ['系统设置', '网络与代理'], params: () => ({ tab: 'proxy' }) },
];

const LEGACY_REDIRECTS = {
  '/': '/admin/ontologies',
  '/editor': '/admin/ontologies/edit',
  '/visualize': '/admin/ontologies/graph',
  '/operations': '/admin/operations/dashboard',
  '/connectors': '/admin/integration/connectors',
  '/mappings': '/admin/integration/mappings/discover',
  '/settings/llm': '/admin/settings/llm',
};

let currentUnmount = null;
let currentPath = '';

function escAttr(str) {
  return String(str).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function navigate(path, { replace = false } = {}) {
  if (path === currentPath) {
    renderRoute(path);
    return;
  }
  if (replace) {
    history.replaceState({ path }, '', path);
  } else {
    history.pushState({ path }, '', path);
  }
  renderRoute(path);
}

function matchRoute(path) {
  for (const route of ROUTES) {
    const m = path.match(route.pattern);
    if (m) {
      if (route.redirect) return { redirect: route.redirect };
      return {
        module: route.module,
        title: route.title,
        breadcrumb: route.breadcrumb,
        params: route.params ? route.params(m) : {},
      };
    }
  }
  return null;
}

function isNavActive(itemPath, activePath) {
  if (activePath === itemPath) return true;
  if (itemPath === '/admin/ontologies/edit' && /^\/admin\/ontologies\/[^/]+\/edit$/.test(activePath)) return true;
  if (itemPath === '/admin/ontologies/graph' && /^\/admin\/ontologies\/[^/]+\/graph$/.test(activePath)) return true;
  return activePath.startsWith(itemPath + '/');
}

function renderSidebar(activePath) {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = MENU.map(section => `
    <div class="sidebar-group">
      <div class="sidebar-group-title">${section.group}</div>
      ${section.items.map(item => `
        <a href="${item.path}" class="sidebar-link ${isNavActive(item.path, activePath) ? 'active' : ''}"
           data-path="${item.path}">${item.label}</a>
      `).join('')}
    </div>
  `).join('');

  nav.querySelectorAll('.sidebar-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(link.dataset.path);
    });
  });
}

function renderBreadcrumb(parts) {
  document.getElementById('breadcrumb').innerHTML = parts
    .map((p, i) => i < parts.length - 1 ? `<span>${p}</span><span class="sep">/</span>` : `<strong>${p}</strong>`)
    .join('');
}

async function renderRoute(path) {
  const legacy = LEGACY_REDIRECTS[path.split('?')[0]];
  if (legacy) {
    const qs = path.includes('?') ? path.slice(path.indexOf('?')) : '';
    navigate(legacy + qs, { replace: true });
    return;
  }

  // legacy query redirects: /editor?name=x
  if (path.startsWith('/editor')) {
    const name = new URLSearchParams(path.split('?')[1] || '').get('name');
    navigate(name ? `/admin/ontologies/${name}/edit` : '/admin/ontologies/edit', { replace: true });
    return;
  }
  if (path.startsWith('/visualize')) {
    const name = new URLSearchParams(path.split('?')[1] || '').get('name');
    navigate(name ? `/admin/ontologies/${name}/graph` : '/admin/ontologies/graph', { replace: true });
    return;
  }

  const matched = matchRoute(path.split('?')[0]);
  const root = document.getElementById('page-root');
  if (!matched) {
    root.innerHTML = '<div class="empty-state card"><h3>页面不存在</h3><p>请从左侧菜单选择功能。</p></div>';
    return;
  }
  if (matched.redirect) {
    navigate(matched.redirect, { replace: true });
    return;
  }

  if (currentUnmount) {
    try { currentUnmount(); } catch (_) {}
    currentUnmount = null;
  }

  currentPath = path.split('?')[0];
  document.title = `${matched.title} - Ontology Platform`;
  renderSidebar(currentPath);
  renderBreadcrumb(matched.breadcrumb || [matched.title]);
  root.innerHTML = '<div class="loading-state">加载中...</div>';

  try {
    const mod = await import(`/static/modules/${matched.module}.js`);
    root.innerHTML = '';
    const ctx = { navigate, escAttr, params: matched.params };
    const result = await mod.mount(root, matched.params, ctx);
    if (typeof result === 'function') currentUnmount = result;
  } catch (err) {
    root.innerHTML = `<div class="empty-state card"><h3>加载失败</h3><p>${escHtml(err.message)}</p></div>`;
  }
}

async function loadGlobalStatus() {
  const el = document.getElementById('global-status');
  try {
    const status = await api('/operations/status');
    const bits = [];
    if (status.runtime_configured) bits.push('运行时 OK');
    if (status.prototype_configured) bits.push('样机 OK');
    if (status.credentials_configured) bits.push('凭据 OK');
    el.textContent = bits.length ? bits.join(' · ') : '演示模式（未配置 store-path）';
  } catch (e) {
    el.textContent = '状态未知';
  }
}

window.addEventListener('popstate', () => {
  renderRoute(location.pathname + location.search);
});

// export for app.js consumers
window.adminNavigate = navigate;
window.adminEscAttr = escAttr;

loadGlobalStatus();
renderRoute(location.pathname + location.search);
