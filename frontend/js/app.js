/* 华晟 ERP 前端主逻辑 */
let CURRENT_USER = null;
let CURRENT_PAGE = 'dashboard';
let CACHE = {}; // 下拉数据缓存

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (n) => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 });

function toast(msg, type = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 2600);
}

/* ---------- 菜单定义 ---------- */
const MENU = [
  { group: '工作台', items: [
    { id: 'dashboard', name: '经营概览', ico: '📊' },
  ]},
  { group: '基础数据', items: [
    { id: 'materials', name: '物料档案', ico: '📦' },
    { id: 'customers', name: '客户档案', ico: '🏢' },
    { id: 'suppliers', name: '供应商档案', ico: '🚚' },
    { id: 'warehouses', name: '仓库库位', ico: '🏭' },
    { id: 'boms', name: 'BOM 管理', ico: '🧩' },
  ]},
  { group: '业务管理', items: [
    { id: 'purchase', name: '采购管理', ico: '🛒' },
    { id: 'sales', name: '销售管理', ico: '💰' },
    { id: 'inventory', name: '库存管理', ico: '🗃️' },
    { id: 'production', name: '生产管理', ico: '⚙️' },
  ]},
  { group: '财务与报表', items: [
    { id: 'finance', name: '财务管理', ico: '💳' },
    { id: 'reports', name: '报表中心', ico: '📈' },
  ]},
  { group: '系统', items: [
    { id: 'system', name: '系统管理', ico: '🔧' },
  ]},
];

function renderMenu() {
  let html = '';
  MENU.forEach(g => {
    html += `<div class="menu-group">${g.group}</div>`;
    g.items.forEach(it => {
      html += `<div class="menu-item ${it.id === CURRENT_PAGE ? 'active' : ''}" data-page="${it.id}">
        <span class="ico">${it.ico}</span><span>${it.name}</span></div>`;
    });
  });
  $('#menu').innerHTML = html;
  document.querySelectorAll('.menu-item').forEach(el => {
    el.onclick = () => navigate(el.dataset.page);
  });
}

async function navigate(page) {
  CURRENT_PAGE = page;
  const item = MENU.flatMap(g => g.items).find(i => i.id === page);
  $('#page-title').textContent = item ? item.name : page;
  renderMenu();
  $('#content').innerHTML = '<div class="empty">加载中…</div>';
  try {
    await PAGES[page]();
  } catch (e) {
    $('#content').innerHTML = `<div class="card"><div class="empty text-danger">加载失败：${esc(e.message)}</div></div>`;
  }
}

/* ---------- 登录 ---------- */
$('#login-form').onsubmit = async (e) => {
  e.preventDefault();
  try {
    const r = await API.login($('#login-user').value, $('#login-pwd').value);
    if (r.code !== 0) { toast(r.msg, 'error'); return; }
    CURRENT_USER = r.data;
    $('#login-page').classList.add('hidden');
    $('#app').classList.remove('hidden');
    $('#current-user').textContent = (CURRENT_USER.real_name || CURRENT_USER.username);
    await preload();
    navigate('dashboard');
  } catch (err) { toast(err.message, 'error'); }
};

$('#logout').onclick = () => location.reload();
$('#toggle-sidebar').onclick = () => {
  $('.sidebar').classList.toggle('collapsed');
  $('#app').classList.toggle('sidebar-collapsed');
};

async function preload() {
  const [mat, cus, sup, wh] = await Promise.all([
    API.list('materials'), API.list('customers'), API.list('suppliers'), API.list('warehouses')
  ]);
  CACHE.materials = mat.data; CACHE.customers = cus.data; CACHE.suppliers = sup.data; CACHE.warehouses = wh.data;
}

/* ---------- 模态框 ---------- */
function openModal(title, bodyHtml, onOk, wide = false) {
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = bodyHtml;
  $('.modal-dialog').classList.toggle('wide', wide);
  $('#modal').classList.remove('hidden');
  $('#modal-ok').onclick = async () => {
    try { await onOk(); } catch (e) { toast(e.message, 'error'); }
  };
}
function closeModal() { $('#modal').classList.add('hidden'); }
document.querySelectorAll('[data-close]').forEach(el => el.onclick = closeModal);

/* ---------- 统一删除确认（替代原生 confirm） ----------
 * confirmDelete({ title, target, tip, onConfirm, onDisable })
 *   - title:     弹窗标题
 *   - target:    要删除的对象描述（如编码+名称），让用户确认删的是哪条
 *   - tip:       补充说明（如被引用不可删、将级联删除子件等）
 *   - onConfirm: 异步函数，只有点「确认删除」才执行；抛错则保留弹窗
 *   - onDisable: 可选。若删除因「已被引用」失败(code=3)，弹窗内提供「改为停用」按钮
 */
function confirmDelete({ title = '确认删除', target = '', tip = '删除后不可恢复，请确认无误。', onConfirm, onDisable }) {
  $('#modal-title').textContent = title;
  $('#modal-body').innerHTML = `
    <div class="delete-confirm">
      <div class="delete-ico">⚠️</div>
      <div>
        <div class="delete-msg">确定要删除这条记录吗？</div>
        ${target ? `<div class="delete-target">删除对象：<b>${esc(target)}</b></div>` : ''}
        <div class="delete-tip" id="delete-tip">${esc(tip)}</div>
      </div>
    </div>`;
  $('.modal-dialog').classList.remove('wide');
  $('#modal').classList.remove('hidden');

  const ok = $('#modal-ok');
  const footer = $('.modal-footer');
  const disableBtn = document.createElement('button');
  disableBtn.className = 'btn btn-warning hidden';
  disableBtn.id = 'modal-disable';
  disableBtn.textContent = '改为停用';
  footer.insertBefore(disableBtn, ok);
  ok.className = 'btn btn-danger';
  ok.textContent = '确认删除';
  ok.disabled = false;
  const restore = () => {
    ok.className = 'btn btn-primary';
    ok.textContent = '确定';
    ok.disabled = false;
    ok.onclick = null;
    disableBtn.remove();
    document.querySelectorAll('#modal [data-close]').forEach(el => el.onclick = closeModal);
  };
  document.querySelectorAll('#modal [data-close]').forEach(el => {
    el.onclick = () => { restore(); closeModal(); };
  });
  disableBtn.onclick = async () => {
    disableBtn.disabled = true;
    disableBtn.textContent = '处理中…';
    try {
      await onDisable();
      toast('已停用，该记录将不再参与新业务', 'success');
      restore(); closeModal();
    } catch (e) {
      disableBtn.disabled = false;
      disableBtn.textContent = '改为停用';
      toast(e.message, 'error');
    }
  };
  ok.onclick = async () => {
    if (ok.disabled) return;
    ok.disabled = true;
    ok.textContent = '删除中…';
    try {
      await onConfirm();
      restore(); closeModal();
    } catch (e) {
      ok.disabled = false;
      ok.textContent = '确认删除';
      if (e.code === 3 && onDisable) {
        $('#delete-tip').innerHTML = `<b>${esc(e.message)}</b><br>可点击下方「改为停用」，使其不再参与新业务。`;
        disableBtn.classList.remove('hidden');
      } else {
        toast(e.message, 'error');
      }
    }
  };
}

/* ---------- 通用表格渲染 ---------- */
function tableHtml(cols, rows, opts = {}) {
  if (!rows.length) return '<div class="empty">暂无数据</div>';
  let h = '<div class="table-wrap"><table><thead><tr>';
  cols.forEach(c => h += `<th>${c.title}</th>`);
  if (opts.actions) h += '<th>操作</th>';
  h += '</tr></thead><tbody>';
  rows.forEach(r => {
    h += '<tr>';
    cols.forEach(c => {
      let v = r[c.key] ?? '';
      if (c.render) v = c.render(r);
      h += `<td class="${c.cls || ''}">${v}</td>`;
    });
    if (opts.actions) h += `<td><div class="inline-actions">${opts.actions(r)}</div></td>`;
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

const STATUS_BADGE = (s) => {
  const map = { draft:'草稿', confirmed:'已确认', partial:'部分完成', received:'已入库',
    shipped:'已发货', done:'已完工', paid:'已结清', open:'未付款', issued:'已领料',
    wip:'生产中', released:'已下达', calculated:'已运算', cancelled:'已取消' };
  return `<span class="badge badge-${s}">${map[s] || s}</span>`;
};

/* ================= 页面：经营概览 ================= */
PAGES = {};
PAGES.dashboard = async () => {
  const d = (await API.get('/api/dashboard')).data;
  const cards = [
    { label: '销售总额', value: '¥' + fmt(d.sales_amount), cls: '', sub: `销售订单 ${d.so_count} 张` },
    { label: '采购入库额', value: '¥' + fmt(d.purchase_amount), cls: 'green', sub: `采购订单 ${d.po_count} 张` },
    { label: '库存总金额', value: '¥' + fmt(d.stock_amount), cls: 'orange', sub: `${d.material_count} 种物料在库` },
    { label: '应收账款', value: '¥' + fmt(d.ar_balance), cls: 'red', sub: '客户未结算' },
    { label: '应付账款', value: '¥' + fmt(d.ap_balance), cls: 'red', sub: '供应商未结算' },
    { label: '订单交付率', value: d.delivery_rate + '%', cls: 'green', sub: `生产工单 ${d.wo_count} 张` },
  ];
  let html = '<div class="stats-grid">';
  cards.forEach(c => html += `<div class="stat-card ${c.cls}"><div class="stat-label">${c.label}</div>
    <div class="stat-value">${c.value}</div><div class="stat-sub">${c.sub}</div></div>`);
  html += '</div>';

  // 销售趋势图
  const maxV = Math.max(1, ...d.sales_trend.map(x => x.value));
  let bars = '';
  d.sales_trend.forEach(x => {
    const h = Math.max(2, Math.round(x.value / maxV * 130));
    bars += `<div class="bar-col"><div class="bar-value">¥${fmt(x.value)}</div>
      <div class="bar" style="height:${h}px"></div><div class="bar-label">${x.month}</div></div>`;
  });
  const maxP = Math.max(1, ...d.purchase_trend.map(x => x.value));
  let barsP = '';
  d.purchase_trend.forEach(x => {
    const h = Math.max(2, Math.round(x.value / maxP * 130));
    barsP += `<div class="bar-col"><div class="bar-value">¥${fmt(x.value)}</div>
      <div class="bar orange" style="height:${h}px"></div><div class="bar-label">${x.month}</div></div>`;
  });
  html += `<div class="grid-2">
    <div class="card"><div class="card-header"><span class="card-title">销售趋势（按月）</span></div>
      <div class="bars">${bars || '<div class="empty">暂无数据</div>'}</div></div>
    <div class="card"><div class="card-header"><span class="card-title">采购趋势（按月）</span></div>
      <div class="bars">${barsP || '<div class="empty">暂无数据</div>'}</div></div>
  </div>`;
  html += `<div class="card"><div class="card-header"><span class="card-title">业务提示</span></div>
    <div class="section-desc">${d.low_stock_count > 0
      ? `⚠️ 当前有 <b class="text-danger">${d.low_stock_count}</b> 项物料低于安全库存，请到「库存管理」查看预警。`
      : '✅ 当前无库存预警，所有物料库存充足。'}</div>
    <div class="flow-step">销售订单 <span class="flow-arrow">→</span> MRP运算 <span class="flow-arrow">→</span>
      采购/生产 <span class="flow-arrow">→</span> 入库 <span class="flow-arrow">→</span>
      发货 <span class="flow-arrow">→</span> 应收应付 <span class="flow-arrow">→</span> 报表</div></div>`;
  $('#content').innerHTML = html;
};

/* ================= 页面：基础数据（物料/客户/供应商/仓库） ================= */
const BASIC_FIELDS = {
  materials: [
    { k:'code', l:'物料编码', req:true }, { k:'name', l:'物料名称', req:true },
    { k:'spec', l:'规格型号' },
    { k:'category', l:'物料类别', type:'select', opts:['原材料','外购件','半成品','成品'] },
    { k:'unit', l:'计量单位' },
    { k:'standard_cost', l:'标准成本', type:'number' },
    { k:'safety_stock', l:'安全库存', type:'number' },
    { k:'is_batch', l:'批次管理', type:'bool' },
    { k:'enabled', l:'是否启用', type:'bool' },
  ],
  customers: [
    { k:'code', l:'客户编码', req:true }, { k:'name', l:'客户名称', req:true },
    { k:'contact', l:'联系人' }, { k:'phone', l:'电话' },
    { k:'address', l:'地址', full:true },
    { k:'credit_limit', l:'信用额度', type:'number' },
    { k:'settle_type', l:'结算方式', type:'select', opts:['现款现货','月结30天','月结60天'] },
    { k:'enabled', l:'是否启用', type:'bool' },
  ],
  suppliers: [
    { k:'code', l:'供应商编码', req:true }, { k:'name', l:'供应商名称', req:true },
    { k:'contact', l:'联系人' }, { k:'phone', l:'电话' },
    { k:'supply_type', l:'供货类别' },
    { k:'pay_terms', l:'结算账期', type:'select', opts:['现款现货','月结30天','月结60天'] },
    { k:'qualified', l:'合格供应商', type:'bool' },
    { k:'enabled', l:'是否启用', type:'bool' },
  ],
  warehouses: [
    { k:'code', l:'仓库编码', req:true }, { k:'name', l:'仓库名称', req:true },
    { k:'location', l:'位置', full:true },
    { k:'enabled', l:'是否启用', type:'bool' },
  ],
};

function basicPage(resource) {
  return async () => {
    const rows = (await API.list(resource)).data;
    const cols = BASIC_FIELDS[resource].slice(0, resource === 'materials' ? 6 : 5).map(f => ({ key:f.k, title:f.l }));
    cols.push({ key:'enabled', title:'状态', render: r => r.enabled
      ? '<span class="badge badge-done">启用</span>' : '<span class="badge badge-draft">停用</span>' });
    $('#content').innerHTML = `<div class="card">
      <div class="card-header"><span class="card-title">${MENU.flatMap(g=>g.items).find(i=>i.id===resource)?.name}</span>
        <button class="btn btn-primary" id="add-btn">+ 新增</button></div>
      <div class="section-desc">已被业务单据引用的记录无法删除，可先「停用」使其不再参与新业务（停用后仍可在历史单据中查看）。</div>
      <div class="toolbar"><input id="kw" placeholder="搜索编码或名称…"><button class="btn btn-ghost" id="search-btn">查询</button></div>
      <div id="table-area">${tableHtml(cols, rows)}</div></div>`;
    const reload = async () => {
      const kw = $('#kw').value.trim();
      let list = (await API.list(resource)).data;
      if (kw) list = list.filter(r => (r.name + r.code).toLowerCase().includes(kw.toLowerCase()));
      $('#table-area').innerHTML = tableHtml(cols, list, {
        actions: r => `<button class="btn btn-ghost btn-sm" data-edit="${r.id}">编辑</button>
          <button class="btn btn-ghost btn-sm" data-toggle="${r.id}">${r.enabled ? '停用' : '启用'}</button>
          <button class="btn btn-ghost btn-sm text-danger" data-del="${r.id}">删除</button>`
      });
      bindRowActions(resource, reload, list);
    };
    $('#search-btn').onclick = reload;
    $('#add-btn').onclick = () => openBasicForm(resource, null, reload);
    await reload();
  };
}

function openBasicForm(resource, row, done) {
  const fields = BASIC_FIELDS[resource];
  let h = '<div class="form-grid">';
  fields.forEach(f => {
    // 新增时 enabled 默认启用，其余 bool 默认否
    const v = row ? row[f.k] : (f.k === 'enabled' ? true : '');
    h += `<div class="${f.full ? 'full' : ''}"><label>${f.l}${f.req ? ' *' : ''}</label>`;
    if (f.type === 'select') {
      h += `<select data-k="${f.k}">${f.opts.map(o => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
    } else if (f.type === 'bool') {
      h += `<select data-k="${f.k}"><option value="true" ${v ? 'selected' : ''}>是</option>
        <option value="false" ${!v ? 'selected' : ''}>否</option></select>`;
    } else {
      h += `<input data-k="${f.k}" type="${f.type === 'number' ? 'number' : 'text'}" step="any" value="${esc(v)}">`;
    }
    h += '</div>';
  });
  h += '</div>';
  openModal((row ? '编辑' : '新增') + MENU.flatMap(g=>g.items).find(i=>i.id===resource)?.name, h, async () => {
    const data = { operator: CURRENT_USER?.username };
    if (row) data.id = row.id;
    document.querySelectorAll('#modal-body [data-k]').forEach(el => {
      const f = fields.find(x => x.k === el.dataset.k);
      let v = el.value;
      if (f.type === 'number') v = v === '' ? 0 : Number(v);
      if (f.type === 'bool') v = v === 'true';
      data[el.dataset.k] = v;
    });
    for (const f of fields) if (f.req && !data[f.k]) { toast(f.l + '不能为空', 'error'); return; }
    await API.save(resource, data);
    closeModal(); toast('保存成功', 'success'); await done();
    if (resource === 'materials' || resource === 'customers' || resource === 'suppliers' || resource === 'warehouses') await preload();
  });
}

function bindRowActions(resource, reload, rows) {
  const nameOf = MENU.flatMap(g => g.items).find(i => i.id === resource)?.name || '记录';
  document.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
    const row = rows.find(r => r.id === Number(b.dataset.edit));
    openBasicForm(resource, row, reload);
  });
  const doToggle = async (rid) => {
    const r = await API.action(`${resource}/${rid}/toggle`, { operator: CURRENT_USER?.username });
    toast(r.msg, 'success');
    await preload(); await reload();
  };
  document.querySelectorAll('[data-toggle]').forEach(b => b.onclick = async () => {
    try { await doToggle(b.dataset.toggle); }
    catch (e) { toast(e.message, 'error'); }
  });
  document.querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
    const row = rows.find(r => r.id === Number(b.dataset.del)) || {};
    confirmDelete({
      title: '删除' + nameOf,
      target: `${row.code || ''} ${row.name || ''}`.trim() || ('ID ' + b.dataset.del),
      tip: '若该记录已被业务单据引用，系统将拒绝删除，届时可一键「改为停用」。',
      onConfirm: async () => {
        const r = await API.del(resource, b.dataset.del, { operator: CURRENT_USER?.username });
        toast(r.msg || '删除成功', 'success');
        await preload();  // 删除后刷新下拉缓存，避免表单仍引用已删记录
        await reload();
      },
      onDisable: () => doToggle(b.dataset.del)
    });
  });
}

PAGES.materials = basicPage('materials');
PAGES.customers = basicPage('customers');
PAGES.suppliers = basicPage('suppliers');
PAGES.warehouses = basicPage('warehouses');

/* ================= 页面：BOM 管理 ================= */
PAGES.boms = async () => {
  const boms = (await API.list('boms')).data;
  const cols = [
    { key:'id', title:'ID' }, { key:'product_name', title:'产品名称' },
    { key:'version', title:'版本' }, { key:'qty_base', title:'基准产量' },
    { key:'effective_date', title:'生效日期' },
  ];
  $('#content').innerHTML = `<div class="card">
    <div class="card-header"><span class="card-title">BOM 物料清单</span>
      <button class="btn btn-primary" id="add-btn">+ 新增 BOM</button></div>
    <div class="section-desc">BOM 描述产品由哪些子件构成，是 MRP 运算的基础。子件用量支持损耗率。</div>
    <div id="table-area">${tableHtml(cols, boms, { actions: r =>
      `<button class="btn btn-ghost btn-sm" data-view="${r.id}">明细</button>
       <button class="btn btn-ghost btn-sm" data-edit="${r.id}">编辑</button>
       <button class="btn btn-ghost btn-sm text-danger" data-del="${r.id}">删除</button>` })}</div></div>`;
  const reload = () => navigate('boms');
  document.querySelectorAll('[data-view]').forEach(b => b.onclick = async () => {
    const d = (await API.get('/api/boms/' + b.dataset.view)).data;
    openModal('BOM 明细 — ' + d.head.product_name, tableHtml([
      { key:'material_code', title:'子件编码' }, { key:'material_name', title:'子件名称' },
      { key:'qty', title:'单位用量' }, { key:'loss_rate', title:'损耗率%' },
      { key:'unit', title:'单位' }
    ], d.items), async () => closeModal(), true);
    $('#modal-ok').textContent = '关闭';
  });
  $('#add-btn').onclick = () => openBomForm(null, reload);
  document.querySelectorAll('[data-edit]').forEach(b => b.onclick = async () => {
    const d = (await API.get('/api/boms/' + b.dataset.edit)).data;
    openBomForm(d, reload);
  });
  document.querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
    const row = boms.find(r => r.id === Number(b.dataset.del)) || {};
    confirmDelete({
      title: '删除 BOM',
      target: `${row.product_code || ''} ${row.product_name || ''} · ${row.version || ''}`.trim() || ('ID ' + b.dataset.del),
      tip: '将同时删除该 BOM 下的全部子件明细，删除后不可恢复。',
      onConfirm: async () => {
        const r = await API.del('boms', b.dataset.del, { operator: CURRENT_USER?.username });
        toast(r.msg || '删除成功', 'success'); await reload();
      }
    });
  });
};

function openBomForm(d, done) {
  const products = CACHE.materials.filter(m => ['成品','半成品'].includes(m.category));
  let h = `<div class="form-grid">
    <div><label>产出产品 *</label><select data-k="product_id">${products.map(m =>
      `<option value="${m.id}" ${d && d.head.product_id === m.id ? 'selected' : ''}>${m.code} ${m.name}</option>`).join('')}</select></div>
    <div><label>版本号</label><input data-k="version" value="${d ? esc(d.head.version) : 'V1'}"></div>
    <div><label>基准产量</label><input data-k="qty_base" type="number" step="any" value="${d ? d.head.qty_base : 1}"></div>
    <div><label>生效日期</label><input data-k="effective_date" type="date" value="${d ? (d.head.effective_date||'').slice(0,10) : ''}"></div>
  </div><h4 style="margin:18px 0 8px">子件明细</h4>
  <table class="line-items"><thead><tr><th>子件物料</th><th>单位用量</th><th>损耗率(%)</th><th></th></tr></thead><tbody id="bom-lines"></tbody></table>
  <span class="add-line" id="bom-add">+ 添加子件</span>`;
  openModal(d ? '编辑 BOM' : '新增 BOM', h, async () => {
    const items = [];
    document.querySelectorAll('#bom-lines tr').forEach(tr => {
      items.push({ material_id: Number(tr.querySelector('.m-sel').value),
        qty: Number(tr.querySelector('.m-qty').value) || 0,
        loss_rate: Number(tr.querySelector('.m-loss').value) || 0 });
    });
    if (!items.length) { toast('请添加子件', 'error'); return; }
    const data = { product_id: Number($('[data-k=product_id]').value),
      version: $('[data-k=version]').value, qty_base: Number($('[data-k=qty_base]').value),
      effective_date: $('[data-k=effective_date]').value || null,
      items, operator: CURRENT_USER?.username };
    if (d) data.id = d.head.id;
    await API.save('boms', data);
    closeModal(); toast('BOM 保存成功', 'success'); await done();
  }, true);

  const addLine = (item) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><select class="m-sel">${CACHE.materials.map(m =>
      `<option value="${m.id}" ${item && item.material_id === m.id ? 'selected' : ''}>${m.code} ${m.name}</option>`).join('')}</select></td>
      <td><input class="m-qty" type="number" step="any" value="${item ? item.qty : 1}"></td>
      <td><input class="m-loss" type="number" step="any" value="${item ? item.loss_rate : 0}"></td>
      <td><button class="btn btn-ghost btn-sm" type="button">×</button></td>`;
    tr.querySelector('button').onclick = () => tr.remove();
    $('#bom-lines').appendChild(tr);
  };
  $('#bom-add').onclick = () => addLine();
  if (d) d.items.forEach(addLine); else addLine();
}

/* ================= 页面：采购管理 ================= */
PAGES.purchase = async () => {
  const orders = (await API.list('purchase-orders')).data;
  const cols = [
    { key:'po_no', title:'采购单号' }, { key:'supplier_name', title:'供应商' },
    { key:'order_date', title:'日期' }, { key:'total_amt', title:'金额', render:r=>'¥'+fmt(r.total_amt), cls:'text-right' },
    { key:'received_amt', title:'已入库额', render:r=>'¥'+fmt(r.received_amt), cls:'text-right' },
    { key:'status', title:'状态', render:r=>STATUS_BADGE(r.status) },
  ];
  const actions = (r) => {
    let btns = `<button class="btn btn-ghost btn-sm" data-detail="${r.id}">明细</button>`;
    if (r.status === 'draft') btns += `<button class="btn btn-primary btn-sm" data-confirm="${r.id}">确认</button>`;
    if (r.status === 'confirmed' || r.status === 'partial') btns += `<button class="btn btn-success btn-sm" data-receive="${r.id}">到货入库</button>`;
    if (r.status === 'draft' || r.status === 'confirmed') btns += `<button class="btn btn-ghost btn-sm" data-cancel="${r.id}">取消</button>`;
    return btns;
  };
  $('#content').innerHTML = `<div class="card">
    <div class="card-header"><span class="card-title">采购订单</span>
      <button class="btn btn-primary" id="add-btn">+ 新建采购单</button></div>
    <div class="section-desc">流程：新建订单 <b>→</b> 确认 <b>→</b> 到货入库（自动生成应付账 + 库存分类账 + 凭证）</div>
    <div id="table-area">${tableHtml(cols, orders, { actions })}</div></div>`;
  $('#add-btn').onclick = () => openPoForm();
  document.querySelectorAll('[data-detail]').forEach(b => b.onclick = async () => {
    const d = (await API.get('/api/purchase-orders/' + b.dataset.detail)).data;
    openModal('采购单明细 — ' + d.head.po_no,
      `<div class="section-desc">供应商：${esc(d.head.supplier_name)}　收货仓：${esc(d.head.warehouse_name)}　状态：${STATUS_BADGE(d.head.status)}</div>` +
      tableHtml([{key:'material_code',title:'编码'},{key:'material_name',title:'物料'},
        {key:'qty',title:'订购'},{key:'price',title:'单价',render:r=>'¥'+fmt(r.price)},
        {key:'received_qty',title:'已入库'},{key:'amount',title:'金额',render:r=>'¥'+fmt(r.amount)}], d.items),
      async () => closeModal(), true);
    $('#modal-ok').textContent = '关闭';
  });
  document.querySelectorAll('[data-confirm]').forEach(b => b.onclick = async () => {
    try { const r = await API.action(`purchase-orders/${b.dataset.confirm}/confirm`); toast(r.msg,'success'); navigate('purchase'); }
    catch(e){ toast(e.message,'error'); }
  });
  document.querySelectorAll('[data-receive]').forEach(b => b.onclick = async () => {
    const d = (await API.get('/api/purchase-orders/' + b.dataset.receive)).data;
    let h = `<div class="section-desc">选择入库数量（可部分入库），系统自动记账并生成应付：</div>
      <table class="line-items"><thead><tr><th>物料</th><th>订购</th><th>已入库</th><th>本次入库</th></tr></thead><tbody>`;
    d.items.forEach(it => {
      const remain = Number(it.qty) - Number(it.received_qty);
      h += `<tr><td>${esc(it.material_name)}</td><td>${it.qty}</td><td>${it.received_qty}</td>
        <td><input class="recv-qty" type="number" step="any" data-id="${it.id}" value="${remain}" max="${remain}"></td></tr>`;
    });
    h += '</tbody></table>';
    openModal('到货入库 — ' + d.head.po_no, h, async () => {
      const items = [];
      document.querySelectorAll('.recv-qty').forEach(el => items.push({ item_id: Number(el.dataset.id), qty: Number(el.value)||0 }));
      const r = await API.action(`purchase-orders/${b.dataset.receive}/receive`, { items, operator: CURRENT_USER?.username });
      closeModal(); toast(r.msg + '，入库单 ' + r.data.receipt_no, 'success'); navigate('purchase');
    }, true);
  });
  document.querySelectorAll('[data-cancel]').forEach(b => b.onclick = async () => {
    if (!confirm('确定取消该订单？')) return;
    const r = await API.action(`purchase-orders/${b.dataset.cancel}/cancel`); toast(r.msg,'success'); navigate('purchase');
  });
};

function openPoForm() {
  let h = `<div class="form-grid">
    <div><label>供应商 *</label><select data-k="supplier_id">${CACHE.suppliers.map(s=>`<option value="${s.id}">${s.code} ${s.name}</option>`).join('')}</select></div>
    <div><label>收货仓库 *</label><select data-k="warehouse_id">${CACHE.warehouses.map(w=>`<option value="${w.id}">${w.name}</option>`).join('')}</select></div>
    <div><label>需求日期</label><input data-k="need_date" type="date"></div>
  </div><h4 style="margin:18px 0 8px">采购明细</h4>
  <table class="line-items"><thead><tr><th>物料</th><th>数量</th><th>单价(¥)</th><th>金额</th><th></th></tr></thead><tbody id="po-lines"></tbody></table>
  <span class="add-line" id="po-add">+ 添加明细</span>`;
  openModal('新建采购订单', h, async () => {
    const items = [];
    document.querySelectorAll('#po-lines tr').forEach(tr => items.push({
      material_id: Number(tr.querySelector('.m-sel').value),
      qty: Number(tr.querySelector('.m-qty').value)||0,
      price: Number(tr.querySelector('.m-price').value)||0 }));
    if (!items.length || items.some(i=>i.qty<=0)) { toast('请填写有效的明细数量','error'); return; }
    const r = await API.save('purchase-orders', {
      supplier_id: Number($('[data-k=supplier_id]').value),
      warehouse_id: Number($('[data-k=warehouse_id]').value),
      need_date: $('[data-k=need_date]').value || null,
      items, operator: CURRENT_USER?.username });
    closeModal(); toast(r.msg,'success'); navigate('purchase');
  }, true);
  const addLine = () => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><select class="m-sel">${CACHE.materials.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></td>
      <td><input class="m-qty" type="number" step="any" value="1"></td>
      <td><input class="m-price" type="number" step="any" value="0"></td><td class="amount">0</td>
      <td><button class="btn btn-ghost btn-sm" type="button">×</button></td>`;
    tr.querySelector('button').onclick = () => tr.remove();
    const calc = () => tr.querySelector('.amount').textContent = fmt(Number(tr.querySelector('.m-qty').value)*Number(tr.querySelector('.m-price').value));
    tr.querySelector('.m-qty').oninput = calc; tr.querySelector('.m-price').oninput = calc;
    $('#po-lines').appendChild(tr);
  };
  $('#po-add').onclick = addLine; addLine();
}

/* ================= 页面：销售管理 ================= */
PAGES.sales = async () => {
  const orders = (await API.list('sales-orders')).data;
  const cols = [
    { key:'so_no', title:'销售单号' }, { key:'customer_name', title:'客户' },
    { key:'order_date', title:'日期' }, { key:'total_amt', title:'金额', render:r=>'¥'+fmt(r.total_amt), cls:'text-right' },
    { key:'shipped_amt', title:'已发货额', render:r=>'¥'+fmt(r.shipped_amt), cls:'text-right' },
    { key:'paid_amt', title:'已收款', render:r=>'¥'+fmt(r.paid_amt), cls:'text-right' },
    { key:'status', title:'状态', render:r=>STATUS_BADGE(r.status) },
  ];
  const actions = r => {
    let b = `<button class="btn btn-ghost btn-sm" data-detail="${r.id}">明细</button>`;
    if (r.status==='draft') b += `<button class="btn btn-primary btn-sm" data-confirm="${r.id}">确认</button>`;
    if (r.status==='confirmed'||r.status==='partial') b += `<button class="btn btn-success btn-sm" data-ship="${r.id}">发货</button>`;
    if (r.status!=='draft'&&r.status!=='cancelled') b += `<button class="btn btn-warning btn-sm" data-pay="${r.id}">收款</button>`;
    return b;
  };
  $('#content').innerHTML = `<div class="card">
    <div class="card-header"><span class="card-title">销售订单</span>
      <button class="btn btn-primary" id="add-btn">+ 新建销售单</button></div>
    <div class="section-desc">流程：新建订单 <b>→</b> 确认（校验信用额度与库存） <b>→</b> 发货出库（扣库存、生成应收） <b>→</b> 收款核销</div>
    <div id="table-area">${tableHtml(cols, orders, { actions })}</div></div>`;
  $('#add-btn').onclick = () => openSoForm();
  document.querySelectorAll('[data-detail]').forEach(b => b.onclick = async () => {
    const d=(await API.get('/api/sales-orders/'+b.dataset.detail)).data;
    openModal('销售单明细 — '+d.head.so_no,
      `<div class="section-desc">客户：${esc(d.head.customer_name)}　状态：${STATUS_BADGE(d.head.status)}　地址：${esc(d.head.address||'-')}</div>`+
      tableHtml([{key:'material_code',title:'编码'},{key:'material_name',title:'产品'},
        {key:'qty',title:'订购'},{key:'price',title:'单价',render:r=>'¥'+fmt(r.price)},
        {key:'shipped_qty',title:'已发货'},{key:'amount',title:'金额',render:r=>'¥'+fmt(r.amount)}],d.items),
      async()=>closeModal(),true); $('#modal-ok').textContent='关闭';
  });
  document.querySelectorAll('[data-confirm]').forEach(b => b.onclick = async () => {
    try{const r=await API.action(`sales-orders/${b.dataset.confirm}/confirm`);toast(r.msg,'success');navigate('sales');}catch(e){toast(e.message,'error');}
  });
  document.querySelectorAll('[data-ship]').forEach(b => b.onclick = async () => {
    const d=(await API.get('/api/sales-orders/'+b.dataset.ship)).data;
    let h=`<div class="section-desc">选择发货数量：</div><table class="line-items"><thead><tr>
      <th>产品</th><th>订购</th><th>已发</th><th>本次发货</th></tr></thead><tbody>`;
    d.items.forEach(it=>{const remain=Number(it.qty)-Number(it.shipped_qty);
      h+=`<tr><td>${esc(it.material_name)}</td><td>${it.qty}</td><td>${it.shipped_qty}</td>
      <td><input class="ship-qty" type="number" step="any" data-id="${it.id}" value="${remain}" max="${remain}"></td></tr>`;});
    h+='</tbody></table>';
    openModal('发货出库 — '+d.head.so_no,h,async()=>{
      const items=[];document.querySelectorAll('.ship-qty').forEach(el=>items.push({item_id:Number(el.dataset.id),qty:Number(el.value)||0}));
      const r=await API.action(`sales-orders/${b.dataset.ship}/ship`,{items,operator:CURRENT_USER?.username});
      closeModal();toast(r.msg+'，发货单 '+r.data.delivery_no,'success');navigate('sales');
    },true);
  });
  document.querySelectorAll('[data-pay]').forEach(b => b.onclick = async () => {
    openModal('登记收款',`<div class="form-grid"><div><label>收款金额 *</label>
      <input data-k="amount" type="number" step="any"></div>
      <div><label>收款日期</label><input data-k="pay_date" type="date"></div>
      <div class="full"><label>备注</label><input data-k="remark"></div></div>`,async()=>{
      const r=await API.action(`sales-orders/${b.dataset.pay}/pay`,{
        amount:Number($('[data-k=amount]').value),pay_date:$('[data-k=pay_date]').value||null,
        remark:$('[data-k=remark]').value,operator:CURRENT_USER?.username});
      closeModal();toast(r.msg,'success');navigate('sales');
    });
  });
};

function openSoForm() {
  let h=`<div class="form-grid">
    <div><label>客户 *</label><select data-k="customer_id">${CACHE.customers.map(c=>`<option value="${c.id}">${c.code} ${c.name}</option>`).join('')}</select></div>
    <div><label>交货日期</label><input data-k="delivery_date" type="date"></div>
    <div class="full"><label>交货地址</label><input data-k="address"></div></div>
    <h4 style="margin:18px 0 8px">销售明细</h4>
    <table class="line-items"><thead><tr><th>产品</th><th>数量</th><th>单价(¥)</th><th>金额</th><th></th></tr></thead><tbody id="so-lines"></tbody></table>
    <span class="add-line" id="so-add">+ 添加明细</span>`;
  openModal('新建销售订单',h,async()=>{
    const items=[];document.querySelectorAll('#so-lines tr').forEach(tr=>items.push({
      material_id:Number(tr.querySelector('.m-sel').value),
      qty:Number(tr.querySelector('.m-qty').value)||0,price:Number(tr.querySelector('.m-price').value)||0}));
    if(!items.length||items.some(i=>i.qty<=0)){toast('请填写有效的明细数量','error');return;}
    const r=await API.save('sales-orders',{customer_id:Number($('[data-k=customer_id]').value),
      delivery_date:$('[data-k=delivery_date]').value||null,address:$('[data-k=address]').value,
      items,operator:CURRENT_USER?.username});
    closeModal();toast(r.msg,'success');navigate('sales');
  },true);
  const addLine=()=>{const tr=document.createElement('tr');
    const products=CACHE.materials.filter(m=>m.category==='成品');
    tr.innerHTML=`<td><select class="m-sel">${products.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></td>
      <td><input class="m-qty" type="number" step="any" value="1"></td>
      <td><input class="m-price" type="number" step="any" value="0"></td><td class="amount">0</td>
      <td><button class="btn btn-ghost btn-sm" type="button">×</button></td>`;
    tr.querySelector('button').onclick=()=>tr.remove();
    const calc=()=>tr.querySelector('.amount').textContent=fmt(Number(tr.querySelector('.m-qty').value)*Number(tr.querySelector('.m-price').value));
    tr.querySelector('.m-qty').oninput=calc;tr.querySelector('.m-price').oninput=calc;
    $('#so-lines').appendChild(tr);};
  $('#so-add').onclick=addLine;addLine();
}

/* ================= 页面：库存管理 ================= */
PAGES.inventory = async () => {
  const [stock, ledger] = await Promise.all([API.list('stock'), API.get('/api/stock/ledger')]);
  const cols=[
    {key:'material_code',title:'编码'},{key:'material_name',title:'物料'},
    {key:'warehouse_name',title:'仓库'},{key:'batch_no',title:'批次'},
    {key:'qty',title:'库存数量',render:r=>fmt(r.qty)+(r.warning?' ⚠️':'')},
    {key:'safety_stock',title:'安全库存'},{key:'avg_cost',title:'平均成本',render:r=>'¥'+fmt(r.avg_cost)},
    {key:'amount',title:'库存金额',render:r=>'¥'+fmt(r.amount),cls:'text-right'},
  ];
  $('#content').innerHTML=`<div class="card">
    <div class="card-header"><span class="card-title">库存结存</span>
      <div><button class="btn btn-ghost" id="adjust-btn">库存调整</button>
      <button class="btn btn-ghost" id="count-btn">盘点</button></div></div>
    <div class="section-desc">库存由"库存分类账"驱动，每笔出入库都留痕，支持账实核对。⚠️ 表示低于安全库存。</div>
    <div id="stock-area">${tableHtml(cols,stock.data)}</div></div>
    <div class="card"><div class="card-header"><span class="card-title">出入库流水</span>
      <button class="btn btn-ghost btn-sm" id="refresh-ledger">刷新</button></div>
      <div id="ledger-area">${tableHtml([
        {key:'txn_no',title:'流水号'},{key:'doc_type',title:'类型'},{key:'doc_no',title:'来源单号'},
        {key:'material_name',title:'物料'},{key:'direction',title:'方向',render:r=>r.direction==='IN'?'<span class="text-success">入库 +</span>':'<span class="text-danger">出库 −</span>'},
        {key:'qty',title:'数量'},{key:'operator',title:'经办人'},
      ],ledger.data.slice(0,50))}</div></div>`;
  $('#adjust-btn').onclick=()=>openAdjust();
  $('#count-btn').onclick=()=>openCount();
  $('#refresh-ledger').onclick=()=>navigate('inventory');
};

function openAdjust(){
  openModal('库存调整（其他出入库）',`<div class="form-grid">
    <div><label>物料 *</label><select data-k="material_id">${CACHE.materials.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></div>
    <div><label>数量（正=入库，负=出库）*</label><input data-k="qty" type="number" step="any" value="1"></div>
    <div><label>单位成本</label><input data-k="cost" type="number" step="any" value="0"></div>
    <div><label>备注</label><input data-k="remark"></div></div>`,async()=>{
    const r=await API.action('stock/adjust',{material_id:Number($('[data-k=material_id]').value),
      qty:Number($('[data-k=qty]').value),cost:Number($('[data-k=cost]').value),
      remark:$('[data-k=remark]').value,operator:CURRENT_USER?.username});
    closeModal();toast(r.msg,'success');navigate('inventory');
  });
}
function openCount(){
  openModal('库存盘点',`<div class="section-desc">录入实盘数量，系统自动计算盘盈盘亏；确认后调整账面库存。</div>
    <div class="form-grid">
    <div><label>物料 *</label><select data-k="material_id">${CACHE.materials.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></div>
    <div><label>仓库</label><select data-k="warehouse_id">${CACHE.warehouses.map(w=>`<option value="${w.id}">${w.name}</option>`).join('')}</select></div>
    <div><label>实盘数量 *</label><input data-k="actual_qty" type="number" step="any"></div></div>`,async()=>{
    const r=await API.save('counts',{material_id:Number($('[data-k=material_id]').value),
      warehouse_id:Number($('[data-k=warehouse_id]').value),actual_qty:Number($('[data-k=actual_qty]').value),
      operator:CURRENT_USER?.username});
    if(!confirm(`账面 ${r.data.book_qty}，实盘 ${r.data.actual_qty}，差异 ${r.data.diff_qty}。确认调整库存？`)){return;}
    await API.action(`counts/${r.data.id}/confirm`,{operator:CURRENT_USER?.username});
    closeModal();toast('盘点完成，库存已调整','success');navigate('inventory');
  });
}

/* ================= 页面：生产管理 ================= */
PAGES.production = async () => {
  const [mps, wos, mrp] = await Promise.all([
    API.list('mps'), API.list('work-orders'), API.get('/api/mrp/results')]);
  $('#content').innerHTML=`
    <div class="card"><div class="card-header"><span class="card-title">主生产计划 (MPS)</span>
      <div><button class="btn btn-warning" id="run-mrp">⚙️ 运行 MRP 运算</button>
      <button class="btn btn-primary" id="add-mps">+ 新增计划</button></div></div>
      <div class="section-desc">MRP 根据 BOM、现有库存、在途采购与在制工单计算净需求，自动生成采购/生产建议。</div>
      <div id="mps-area">${tableHtml([
        {key:'mps_no',title:'计划单号'},{key:'product_name',title:'产品'},
        {key:'qty',title:'计划数量'},{key:'plan_finish',title:'计划完工'},
        {key:'status',title:'状态',render:r=>STATUS_BADGE(r.status)}],mps.data)}</div></div>
    <div class="card"><div class="card-header"><span class="card-title">MRP 净需求建议</span></div>
      <div id="mrp-area">${tableHtml([
        {key:'code',title:'编码'},{key:'name',title:'物料'},
        {key:'gross_demand',title:'毛需求'},{key:'stock_qty',title:'现有库存'},
        {key:'net_demand',title:'净需求'},{key:'suggest_qty',title:'建议量'},
        {key:'suggest_type',title:'建议类型',render:r=>r.suggest_type==='PURCHASE'?'<span class="badge badge-draft">采购</span>':'<span class="badge badge-confirmed">自制</span>'}
      ],mrp.data)}</div></div>
    <div class="card"><div class="card-header"><span class="card-title">生产工单</span>
      <button class="btn btn-primary" id="add-wo">+ 新建工单</button></div>
      <div id="wo-area">${tableHtml([
        {key:'wo_no',title:'工单号'},{key:'product_name',title:'产品'},
        {key:'qty',title:'计划数'},{key:'produced_qty',title:'已完工'},
        {key:'plan_finish',title:'计划完工'},
        {key:'status',title:'状态',render:r=>STATUS_BADGE(r.status)}],wos.data,
        {actions:r=>{let b=`<button class="btn btn-ghost btn-sm" data-wodetail="${r.id}">明细</button>`;
          if(r.status==='draft')b+=`<button class="btn btn-primary btn-sm" data-release="${r.id}">下达</button>`;
          if(r.status==='released')b+=`<button class="btn btn-ghost btn-sm" data-issue="${r.id}">领料</button>`;
          if(['issued','wip','released'].includes(r.status))b+=`<button class="btn btn-success btn-sm" data-finish="${r.id}">完工入库</button>`;
          return b;}})}</div></div>`;
  $('#add-mps').onclick=()=>openMpsForm();
  $('#run-mrp').onclick=async()=>{
    try{const r=await API.action('mrp/run',{operator:CURRENT_USER?.username});toast(r.msg,'success');navigate('production');}
    catch(e){toast(e.message,'error');}};
  $('#add-wo').onclick=()=>openWoForm();
  document.querySelectorAll('[data-wodetail]').forEach(b=>b.onclick=async()=>{
    const d=(await API.get('/api/work-orders/'+b.dataset.wodetail)).data;
    openModal('工单明细 — '+d.head.wo_no,
      `<div class="section-desc">产品：${esc(d.head.product_name)}　计划：${d.head.qty}　已完工：${d.head.produced_qty}</div>`+
      tableHtml([{key:'issue_no',title:'领料单号'},{key:'material_code',title:'物料编码'},
        {key:'material_name',title:'物料'},{key:'qty',title:'数量'},{key:'operator',title:'经办人'}],d.issues),
      async()=>closeModal(),true);$('#modal-ok').textContent='关闭';
  });
  const bind=(attr,path,extra)=>document.querySelectorAll(`[data-${attr}]`).forEach(b=>b.onclick=async()=>{
    try{const r=await API.action(`work-orders/${b.dataset[attr]}/${path}`,{...extra,operator:CURRENT_USER?.username});
      toast(r.msg,'success');navigate('production');}catch(e){toast(e.message,'error');}});
  bind('release','release',{});
  bind('issue','issue',{});
  document.querySelectorAll('[data-finish]').forEach(b=>b.onclick=()=>{
    openModal('完工入库',`<div class="form-grid"><div><label>完工数量 *</label>
      <input data-k="qty" type="number" step="any" value="1"></div></div>`,async()=>{
      const r=await API.action(`work-orders/${b.dataset.finish}/finish`,{qty:Number($('[data-k=qty]').value),operator:CURRENT_USER?.username});
      closeModal();toast(r.msg,'success');navigate('production');
    });
  });
};
function openMpsForm(){
  const products=CACHE.materials.filter(m=>['成品','半成品'].includes(m.category));
  openModal('新增主生产计划',`<div class="form-grid">
    <div><label>产品 *</label><select data-k="product_id">${products.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></div>
    <div><label>计划数量 *</label><input data-k="qty" type="number" step="any" value="1"></div>
    <div><label>计划完工日期</label><input data-k="plan_finish" type="date"></div>
    <div><label>来源销售单号</label><input data-k="so_no" placeholder="选填"></div></div>`,async()=>{
    const r=await API.save('mps',{product_id:Number($('[data-k=product_id]').value),qty:Number($('[data-k=qty]').value),
      plan_finish:$('[data-k=plan_finish]').value||null,so_no:$('[data-k=so_no]').value||null,operator:CURRENT_USER?.username});
    closeModal();toast(r.msg,'success');navigate('production');
  });
}
function openWoForm(){
  const products=CACHE.materials.filter(m=>['成品','半成品'].includes(m.category));
  openModal('新建生产工单',`<div class="form-grid">
    <div><label>产品 *</label><select data-k="product_id">${products.map(m=>`<option value="${m.id}">${m.code} ${m.name}</option>`).join('')}</select></div>
    <div><label>生产数量 *</label><input data-k="qty" type="number" step="any" value="1"></div>
    <div><label>计划开工</label><input data-k="plan_start" type="date"></div>
    <div><label>计划完工</label><input data-k="plan_finish" type="date"></div></div>`,async()=>{
    const r=await API.save('work-orders',{product_id:Number($('[data-k=product_id]').value),qty:Number($('[data-k=qty]').value),
      plan_start:$('[data-k=plan_start]').value||null,plan_finish:$('[data-k=plan_finish]').value||null,operator:CURRENT_USER?.username});
    closeModal();toast(r.msg,'success');navigate('production');
  });
}

/* ================= 页面：财务管理 ================= */
PAGES.finance = async () => {
  const [ap, ar, vouchers] = await Promise.all([
    API.list('payables'), API.list('receivables'), API.list('vouchers')]);
  $('#content').innerHTML=`
    <div class="card"><div class="card-header"><span class="card-title">应付账款（供应商）</span></div>
      <div id="ap-area">${tableHtml([
        {key:'supplier_name',title:'供应商'},{key:'doc_no',title:'入库单号'},
        {key:'amount',title:'应付金额',render:r=>'¥'+fmt(r.amount)},
        {key:'paid_amount',title:'已付',render:r=>'¥'+fmt(r.paid_amount)},
        {key:'balance',title:'未付余额',render:r=>'¥'+fmt(r.balance),cls:'text-danger'},
        {key:'status',title:'状态',render:r=>STATUS_BADGE(r.status)}],ap.data,
        {actions:r=>r.status!=='paid'?`<button class="btn btn-warning btn-sm" data-payap="${r.id}">付款</button>`:''})}</div></div>
    <div class="card"><div class="card-header"><span class="card-title">应收账款（客户）</span></div>
      ${tableHtml([{key:'so_no',title:'销售单号'},{key:'customer_name',title:'客户'},
        {key:'amount',title:'应收金额',render:r=>'¥'+fmt(r.amount)},
        {key:'settled',title:'已收',render:r=>'¥'+fmt(r.settled)},
        {key:'balance',title:'未收余额',render:r=>'¥'+fmt(r.balance),cls:'text-danger'}],ar.data)}</div>
    <div class="card"><div class="card-header"><span class="card-title">财务凭证（对接导出）</span>
      <a class="btn btn-ghost btn-sm" href="/api/vouchers/export.csv" download>导出 CSV</a></div>
      <div class="section-desc">业务单据按规则生成凭证分录数据，可导出供外部财务系统核算。</div>
      ${tableHtml([{key:'voucher_no',title:'凭证号'},{key:'biz_doc_no',title:'业务单号'},
        {key:'summary',title:'摘要'},{key:'debit_account',title:'借方科目'},
        {key:'credit_account',title:'贷方科目'},{key:'amount',title:'金额',render:r=>'¥'+fmt(r.amount)}],vouchers.data)}</div>`;
  document.querySelectorAll('[data-payap]').forEach(b=>b.onclick=()=>{
    openModal('登记付款',`<div class="form-grid"><div><label>付款金额 *</label><input data-k="amount" type="number" step="any"></div>
      <div><label>付款日期</label><input data-k="pay_date" type="date"></div>
      <div class="full"><label>备注</label><input data-k="remark"></div></div>`,async()=>{
      const r=await API.action(`payables/${b.dataset.payap}/pay`,{amount:Number($('[data-k=amount]').value),
        pay_date:$('[data-k=pay_date]').value||null,remark:$('[data-k=remark]').value,operator:CURRENT_USER?.username});
      closeModal();toast(r.msg,'success');navigate('finance');
    });
  });
};

/* ================= 页面：报表中心 ================= */
const REPORT_LIST=[
  {id:'purchase_exec',name:'采购订单执行表',ico:'🛒'},
  {id:'stock_balance',name:'库存结存表',ico:'🗃️'},
  {id:'stock_ledger',name:'出入库流水账',ico:'📋'},
  {id:'sales_exec',name:'销售订单执行表',ico:'💰'},
  {id:'work_order',name:'工单进度表',ico:'⚙️'},
  {id:'mrp',name:'物料需求清单',ico:'🧮'},
  {id:'finance',name:'应收应付汇总表',ico:'💳'},
];
PAGES.reports=async()=>{
  const first=REPORT_LIST[0];
  $('#content').innerHTML=`<div class="card"><div class="card-header"><span class="card-title">报表中心</span>
      <a class="btn btn-ghost btn-sm" id="export-btn" href="/api/report/${first.id}/export" download>导出 Excel(CSV)</a></div>
    <div class="section-desc">所有报表数据实时来自 HighGo 业务单据，支持导出。金额保留两位小数，口径一致。</div>
    <div class="toolbar">${REPORT_LIST.map((r,i)=>`<button class="btn ${i===0?'btn-primary':'btn-ghost'} btn-sm report-tab" data-report="${r.id}">${r.ico} ${r.name}</button>`).join('')}</div>
    <div id="report-area"></div></div>`;
  const load=async(id)=>{
    const r=(await API.report(id)).data;
    $('#report-area').innerHTML=`<h4 style="margin-bottom:12px">${esc(r.title)} <span class="muted" style="font-size:12px">（${r.rows.length} 条）</span></h4>`+
      tableHtml(r.columns.map(c=>({key:c,title:c})),r.rows);
    $('#export-btn').href='/api/report/'+id+'/export';
  };
  document.querySelectorAll('.report-tab').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('.report-tab').forEach(x=>x.classList.remove('btn-primary'));
    b.classList.add('btn-primary');load(b.dataset.report);
  });
  await load(first.id);
};

/* ================= 页面：系统管理 ================= */
PAGES.system=async()=>{
  const [users,depts,logs,params]=await Promise.all([
    API.list('users'),API.list('departments'),API.list('logs'),API.list('params')]);
  $('#content').innerHTML=`
    <div class="card"><div class="card-header"><span class="card-title">用户管理</span></div>
      ${tableHtml([{key:'username',title:'用户名'},{key:'real_name',title:'姓名'},
        {key:'role',title:'角色'},{key:'dept',title:'部门'},
        {key:'enabled',title:'状态',render:r=>r.enabled?'<span class="badge badge-done">启用</span>':'<span class="badge badge-draft">停用</span>'},
        {key:'last_login',title:'最后登录'}],users.data)}</div>
    <div class="grid-2">
      <div class="card"><div class="card-header"><span class="card-title">操作日志</span></div>
        ${tableHtml([{key:'created_at',title:'时间'},{key:'username',title:'操作人'},
          {key:'module',title:'模块'},{key:'action',title:'操作'},{key:'detail',title:'内容'}],logs.data.slice(0,30))}</div>
      <div><div class="card"><div class="card-header"><span class="card-title">系统参数</span></div>
        ${tableHtml([{key:'param_key',title:'参数'},{key:'param_value',title:'值'},{key:'remark',title:'说明'}],params.data)}</div>
        <div class="card"><div class="card-header"><span class="card-title">数据库信息</span></div>
        <div class="section-desc">HighGo Database（PostgreSQL 10.6 兼容）<br>地址：127.0.0.1:5866<br>
          数据库：highgo　Schema：erp<br>业务表 31 张 + 报表视图 4 个</div></div></div>
    </div>`;
};

/* ---------- 启动：恢复会话（简单记住登录态） ---------- */
if (sessionStorage.getItem('erp_user')) {
  try {
    CURRENT_USER = JSON.parse(sessionStorage.getItem('erp_user'));
    $('#login-page').classList.add('hidden');
    $('#app').classList.remove('hidden');
    $('#current-user').textContent = CURRENT_USER.real_name || CURRENT_USER.username;
    preload().then(() => navigate('dashboard'));
  } catch(e) { sessionStorage.removeItem('erp_user'); }
}
const origLogin = $('#login-form').onsubmit;
$('#login-form').onsubmit = async (e) => {
  await origLogin(e);
  if (CURRENT_USER) sessionStorage.setItem('erp_user', JSON.stringify(CURRENT_USER));
};
$('#logout').onclick = () => { sessionStorage.removeItem('erp_user'); location.reload(); };
