/* UX 增强层：toast / 超时取消 / 慢任务缓存 / 骨架屏 / 表格工具条 /
   空状态引导 / 通用代码选择器 / 自动刷新 / 命令面板 / 记住上次 tab

   必须在 app.js 之后、p1.js 与 p2.js 之前加载：p1/p2 从 window.ST
   解构公共能力，这里覆盖后它们拿到的就是增强版。
   包在 IIFE 里，避免与其它经典 script 的顶层 const 重名。 */

(() => {
  const ST = window.ST;
  const $ = ST.$, esc = ST.esc;
  const LS = window.localStorage;
  const PAGE_SIZE = 20;
  const CACHE_TTL = 10 * 60 * 1000;
  const CACHE_PATHS = /^\/api\/(backtest\/|lab\/|predict)/;
  const PICKER_IDS = [
    'wl-code', 'codes', 'kline-code', 'bt-code', 'lab-code',
    'pos-code', 'w-code', 'a-code', 'p-code',
  ];
  const TABS = [
    ['overview', '总览'], ['market', '行情'], ['analysis', '统计'],
    ['backtest', '回测'], ['lab', '策略实验室'], ['predict', 'AI 预测'],
    ['trades', '交易持仓'], ['write', '录入交易'], ['alerts', '预警'],
    ['paper', '模拟盘'], ['settings', '设置'], ['reports', '报告'],
  ];
  const EMPTY_ACTIONS = {
    'holdings': [['去录入交易', 'write']],
    'trades-holdings': [['录入一笔交易', 'write'], ['新增持仓', 'trades']],
    'trades-list': [['录入交易', 'write']],
    'watchlist-quotes': [['添加自选', 'market']],
    'alert-list': [['新增预警', 'alerts']],
    'paper-positions': [['虚拟下单', 'paper']],
    'paper-orders': [['虚拟下单', 'paper']],
    'quotes': [['查询行情', 'market']],
  };

  /* ==================== 1. toast ==================== */
  function toast(msg, type = 'info', ms = 3200) {
    const box = $('toast-box');
    if (!box) return;
    const item = document.createElement('div');
    item.className = 'toast ' + type;
    item.textContent = msg;
    box.appendChild(item);
    setTimeout(() => item.remove(), ms);
  }
  ST.toast = toast;

  /* ==================== 2. 请求：超时 / 取消 / 缓存 ==================== */
  const cache = new Map();
  let activeReq = null;

  function setBusy(on, text) {
    const bar = $('busy-bar');
    if (!bar) return;
    bar.classList.toggle('hidden', !on);
    if (on) $('busy-text').textContent = text || '加载中…';
  }

  async function request(path, options) {
    options = options || {};
    const method = options.method || 'GET';
    const body = options.body || '';
    const cacheable = CACHE_PATHS.test(path);
    const key = method + '|' + path + '|' + body;

    if (cacheable && cache.has(key)) {
      const hit = cache.get(key);
      if (Date.now() - hit.ts < CACHE_TTL) {
        toast('使用缓存结果（相同参数 10 分钟内不重跑）', 'info', 2400);
        return hit.data;
      }
      cache.delete(key);
    }

    const ctrl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; ctrl.abort(); },
      cacheable ? 120000 : 30000);
    activeReq = { ctrl, timer };
    if (cacheable) setBusy(true, '计算中…可点「取消」中止');

    try {
      const res = await fetch(path, Object.assign({}, options, {
        method, signal: ctrl.signal,
        headers: Object.assign({ 'Content-Type': 'application/json' }, options.headers || {}),
      }));
      let payload;
      try { payload = await res.json(); }
      catch (e) { throw new Error('服务返回格式异常'); }
      if (!res.ok || !payload.ok) throw new Error(payload.error || ('HTTP ' + res.status));
      if (cacheable) cache.set(key, { data: payload.data, ts: Date.now() });
      return payload.data;
    } catch (e) {
      if (e.name === 'AbortError') {
        throw new Error(timedOut ? '请求超时，请缩小参数后重试' : '已取消本次请求');
      }
      throw e;
    } finally {
      clearTimeout(timer);
      activeReq = null;
      setBusy(false);
    }
  }

  ST.api = (path) => request(path, {});
  ST.post = (path, body) => request(path, {
    method: 'POST', body: JSON.stringify(body || {}),
  });
  ST.cancelActive = () => { if (activeReq) activeReq.ctrl.abort(); };
  ST.clearCache = () => cache.clear();
  $('busy-cancel').addEventListener('click', () => {
    ST.cancelActive();
    toast('已取消本次请求', 'info', 1800);
  });

  /* ==================== 3. 错误条 + 重试 / 首次加载包装 ==================== */
  const baseShowError = window.showError;
  function showErrorEx(err) {
    baseShowError(err);
    const el = $('alert');
    if (!el || el.querySelector('.retry-btn')) return;
    const btn = document.createElement('button');
    btn.className = 'btn ghost retry-btn';
    btn.textContent = '重试';
    btn.addEventListener('click', () => { ST.clearError(); window.refresh(); });
    el.appendChild(btn);
  }
  window.showError = showErrorEx;
  ST.showError = showErrorEx;

  function goTab(name) {
    const btn = document.querySelector('.tab[data-tab="' + name + '"]');
    if (btn) btn.click();
  }
  ST.goTab = goTab;

  function showSkeleton() {
    const panel = $('panel-' + activeTab);
    if (!panel) return;
    panel.querySelectorAll('table').forEach(t => {
      const tbody = t.querySelector('tbody');
      if (!tbody || tbody.querySelector('tr')) return;
      const cols = t.querySelectorAll('thead th').length || 4;
      let html = '';
      for (let i = 0; i < 3; i++) {
        html += `<tr class="skeleton-row"><td colspan="${cols}"><span class="skeleton-bar"></span></td></tr>`;
      }
      tbody.innerHTML = html;
    });
  }
  function hideSkeleton() {
    document.querySelectorAll('.skeleton-row').forEach(tr => tr.remove());
  }
  function stampUpdate() {
    const el = $('last-update');
    if (el) el.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
  }

  const baseRefresh = window.refresh;
  window.refresh = async function () {
    showSkeleton();
    try { await baseRefresh(); }
    finally { hideSkeleton(); stampUpdate(); }
  };

  /* ==================== 4. 表格：排序 / 筛选 / 分页 / CSV / 空状态 ==================== */
  function emptyRowEx(table, colspan, text) {
    const tbody = table.querySelector('tbody');
    const actions = EMPTY_ACTIONS[table.id] || [];
    const btns = actions.map(([label, tab]) =>
      `<button type="button" class="btn ghost empty-action" data-tab="${tab}">${esc(label)}</button>`
    ).join('');
    tbody.innerHTML = `<tr><td class="empty" colspan="${colspan}">${esc(text || '暂无数据')}`
      + (btns ? `<div class="empty-actions">${btns}</div>` : '') + '</td></tr>';
    bindEmptyActions(tbody);
  }
  function bindEmptyActions(tbody) {
    tbody.querySelectorAll('.empty-action').forEach(b =>
      b.addEventListener('click', () => goTab(b.dataset.tab)));
  }
  window.emptyRow = emptyRowEx;
  ST.emptyRow = emptyRowEx;

  function cellText(tr, idx) {
    const td = tr.children[idx];
    return td ? td.textContent.trim() : '';
  }

  function exportCsv(table) {
    const heads = Array.from(table.querySelectorAll('thead th'))
      .map(th => th.textContent.trim());
    const rows = (table._allRows || []).filter(tr => !tr.querySelector('td.empty'));
    const lines = [heads.map(h => '"' + h.replace(/"/g, '""') + '"').join(',')]
      .concat(rows.map(tr => Array.from(tr.children)
        .map(td => '"' + td.textContent.trim().replace(/"/g, '""') + '"').join(',')));
    const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (table.id || 'table') + '_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast('已导出 ' + rows.length + ' 行 CSV', 'ok');
  }

  function applyTable(table) {
    const tbody = table.querySelector('tbody');
    if (!tbody || typeof tbody.replaceChildren !== 'function') return;
    const all = table._allRows || [];
    if (!all.length) return;
    const bar = table.parentNode.querySelector('.table-tools');

    if (all.length === 1 && all[0].querySelector('td.empty')) {
      tbody.replaceChildren(all[0].cloneNode(true));
      bindEmptyActions(tbody);
      if (bar) bar.classList.add('hidden');
      return;
    }
    if (bar) bar.classList.remove('hidden');

    let rows = all.slice();
    const kw = (table.dataset.filter || '').toLowerCase();
    if (kw) rows = rows.filter(tr => tr.textContent.toLowerCase().includes(kw));

    if (table.dataset.sortCol !== undefined && table.dataset.sortDir) {
      const col = Number(table.dataset.sortCol);
      const dir = table.dataset.sortDir === 'asc' ? 1 : -1;
      rows.sort((a, b) => {
        const av = cellText(a, col), bv = cellText(b, col);
        const an = Number(av.replace(/[,%+\s]/g, '')), bn = Number(bv.replace(/[,%+\s]/g, ''));
        if (av && bv && !Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * dir;
        return av.localeCompare(bv, 'zh-CN') * dir;
      });
    }

    const size = Number(table.dataset.pageSize || PAGE_SIZE);
    const pages = Math.max(1, Math.ceil(rows.length / size));
    const page = Math.min(Math.max(0, Number(table.dataset.page || 0)), pages - 1);
    table.dataset.page = String(page);
    tbody.replaceChildren(...rows.slice(page * size, (page + 1) * size)
      .map(tr => tr.cloneNode(true)));

    if (bar) {
      bar.querySelector('.table-count').textContent = '共 ' + rows.length + ' 行';
      bar.querySelector('.table-page').textContent = (page + 1) + '/' + pages;
      bar.querySelector('.table-prev').disabled = page === 0;
      bar.querySelector('.table-next').disabled = page >= pages - 1;
    }
  }

  function enhanceTable(table) {
    if (!table) return;
    table._allRows = Array.from(table.querySelector('tbody').children)
      .map(tr => tr.cloneNode(true));
    if (table.dataset.enhanced) { applyTable(table); return; }
    table.dataset.enhanced = '1';

    const bar = document.createElement('div');
    bar.className = 'table-tools';
    bar.innerHTML = `<input type="text" class="table-filter" placeholder="筛选…">
      <button type="button" class="btn ghost table-export">导出 CSV</button>
      <span class="table-count dim"></span>
      <span class="table-pager">
        <button type="button" class="btn ghost table-prev">‹</button>
        <span class="table-page">1/1</span>
        <button type="button" class="btn ghost table-next">›</button>
      </span>`;
    table.parentNode.insertBefore(bar, table);
    const filter = bar.querySelector('.table-filter');
    filter.addEventListener('input', () => {
      table.dataset.filter = filter.value.trim().toLowerCase();
      table.dataset.page = '0';
      applyTable(table);
    });
    bar.querySelector('.table-export').addEventListener('click', () => exportCsv(table));
    bar.querySelector('.table-prev').addEventListener('click', () => {
      table.dataset.page = String(Math.max(0, Number(table.dataset.page || 0) - 1));
      applyTable(table);
    });
    bar.querySelector('.table-next').addEventListener('click', () => {
      table.dataset.page = String(Number(table.dataset.page || 0) + 1);
      applyTable(table);
    });
    table.querySelectorAll('thead th').forEach((th, idx) => {
      th.classList.add('sortable');
      th.title = '点击排序';
      th.addEventListener('click', () => {
        const dir = table.dataset.sortDir === 'asc'
          && table.dataset.sortCol === String(idx) ? 'desc' : 'asc';
        table.dataset.sortCol = String(idx);
        table.dataset.sortDir = dir;
        table.dataset.page = '0';
        applyTable(table);
      });
    });
    applyTable(table);
  }

  const baseTableRows = ST.tableRows;
  ST.tableRows = function (table, rows, cols, emptyText) {
    baseTableRows(table, rows, cols, emptyText);
    enhanceTable(table);
  };

  /* ==================== 5. 通用代码选择器 ==================== */
  let pickerData = null;
  async function ensurePickerData() {
    if (pickerData) return pickerData;
    try { pickerData = await ST.api('/api/code-picker'); }
    catch (e) { pickerData = { watchlist: [], holdings: [] }; }
    return pickerData;
  }

  function attachCodePicker(input) {
    if (!input || !input.parentNode) return;
    const wrap = document.createElement('span');
    wrap.className = 'picker-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn ghost picker-btn';
    btn.textContent = '自选/持仓';
    btn.title = '从已收藏或持仓中选代码';
    wrap.appendChild(btn);

    const pop = document.createElement('div');
    pop.className = 'picker-pop hidden';
    pop.innerHTML = '<input type="text" class="picker-search" placeholder="搜索代码或名称…">'
      + '<div class="picker-items"></div>';
    wrap.appendChild(pop);
    const search = pop.querySelector('.picker-search');
    const items = pop.querySelector('.picker-items');

    async function render() {
      const d = await ensurePickerData();
      const kw = search.value.trim().toLowerCase();
      let html = '';
      for (const [label, rows] of [['我的自选', d.watchlist || []], ['当前持仓', d.holdings || []]]) {
        const matched = rows.filter(x => !kw
          || (x.code + ' ' + (x.name || '')).toLowerCase().includes(kw));
        if (!matched.length) continue;
        html += '<div class="picker-group">' + esc(label) + ' (' + matched.length + ')</div>';
        html += matched.map(x => '<button type="button" class="picker-item" data-code="'
          + esc(x.code) + '"><code>' + esc(x.code) + '</code> ' + esc(x.name || '') + '</button>').join('');
      }
      items.innerHTML = html || '<div class="dim picker-empty">没有匹配的股票</div>';
      items.querySelectorAll('.picker-item').forEach(b => b.addEventListener('click', () => {
        const code = b.dataset.code;
        if (input.id === 'codes') {
          const cur = input.value.trim();
          input.value = cur ? cur + ',' + code : code;
        } else {
          input.value = code;
        }
        pop.classList.add('hidden');
        toast('已选择 ' + code, 'ok', 1600);
      }));
    }

    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const willOpen = pop.classList.contains('hidden');
      document.querySelectorAll('.picker-pop').forEach(p => p.classList.add('hidden'));
      if (willOpen) { pop.classList.remove('hidden'); await render(); search.focus(); }
    });
    search.addEventListener('input', render);
    pop.addEventListener('click', e => e.stopPropagation());
  }
  PICKER_IDS.forEach(id => attachCodePicker($(id)));
  document.addEventListener('click', () =>
    document.querySelectorAll('.picker-pop').forEach(p => p.classList.add('hidden')));

  /* ==================== 6. 自动刷新（可暂停 + 更新时间） ==================== */
  const autoBox = $('auto-refresh'), intervalSel = $('auto-interval');
  let autoTimer = null;
  function applyAuto() {
    if (autoTimer) clearInterval(autoTimer);
    autoTimer = null;
    if (!autoBox.checked) return;
    autoTimer = setInterval(() => { if (!document.hidden) window.refresh(); },
      Number(intervalSel.value || 30000));
  }
  try {
    autoBox.checked = LS.getItem('st.auto') === '1';
    intervalSel.value = LS.getItem('st.interval') || '30000';
  } catch (e) { /* localStorage 不可用时用默认值 */ }
  autoBox.addEventListener('change', () => {
    try { LS.setItem('st.auto', autoBox.checked ? '1' : '0'); } catch (e) { /* ignore */ }
    applyAuto();
    toast(autoBox.checked ? '自动刷新已开启' : '自动刷新已暂停', 'info', 1800);
  });
  intervalSel.addEventListener('change', () => {
    try { LS.setItem('st.interval', intervalSel.value); } catch (e) { /* ignore */ }
    applyAuto();
  });
  applyAuto();

  /* ==================== 7. 命令面板 + 记住上次 tab ==================== */
  const COMMANDS = TABS.map(([id, label]) => ({
    label: '打开 ' + label, hint: '页面', run: () => goTab(id),
  })).concat([
    { label: '刷新当前页', hint: '重新拉取数据', run: () => window.refresh() },
    { label: '清除慢任务缓存', hint: '回测 / 寻优 / 预测',
      run: () => { ST.clearCache(); toast('缓存已清除', 'ok'); } },
    { label: '导出当前页表格 CSV', hint: '第一张表',
      run: () => {
        const panel = $('panel-' + activeTab);
        const table = panel && panel.querySelector('table');
        if (table) exportCsv(table); else toast('当前页没有表格', 'info');
      } },
    { label: '切换自动刷新', hint: '开 / 关',
      run: () => { autoBox.checked = !autoBox.checked; applyAuto();
        toast(autoBox.checked ? '自动刷新已开启' : '自动刷新已暂停', 'info', 1800); } },
  ]);
  let cmdIndex = 0, cmdFiltered = COMMANDS.slice();

  function renderCmd() {
    const kw = $('cmd-input').value.trim().toLowerCase();
    cmdFiltered = COMMANDS.filter(c => !kw || (c.label + c.hint).toLowerCase().includes(kw));
    cmdIndex = Math.min(cmdIndex, Math.max(0, cmdFiltered.length - 1));
    $('cmd-list').innerHTML = cmdFiltered.length
      ? cmdFiltered.map((c, i) => '<div class="cmd-item ' + (i === cmdIndex ? 'active' : '')
          + '" data-i="' + i + '"><span>' + esc(c.label) + '</span><span class="dim">'
          + esc(c.hint) + '</span></div>').join('')
      : '<div class="dim cmd-empty">没有匹配的命令</div>';
    $('cmd-list').querySelectorAll('.cmd-item').forEach(el =>
      el.addEventListener('click', () => { cmdIndex = Number(el.dataset.i); runCmd(); }));
  }
  function openCmd(help) {
    $('cmd-panel').classList.remove('hidden');
    const input = $('cmd-input');
    input.value = '';
    input.placeholder = help ? '快捷键：Ctrl+K 命令面板 · ? 帮助 · Esc 关闭'
      : '输入页面名或动作，回车执行…';
    cmdIndex = 0;
    renderCmd();
    input.focus();
  }
  function closeCmd() { $('cmd-panel').classList.add('hidden'); }
  function runCmd() {
    const c = cmdFiltered[cmdIndex];
    if (!c) return;
    closeCmd();
    c.run();
  }
  $('cmd-input').addEventListener('input', () => { cmdIndex = 0; renderCmd(); });
  $('cmd-input').addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') {
      cmdIndex = Math.min(cmdIndex + 1, cmdFiltered.length - 1); renderCmd(); e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      cmdIndex = Math.max(cmdIndex - 1, 0); renderCmd(); e.preventDefault();
    } else if (e.key === 'Enter') { runCmd(); }
    else if (e.key === 'Escape') { closeCmd(); }
  });
  $('cmd-open').addEventListener('click', () => openCmd(false));
  $('cmd-panel').addEventListener('click', e => { if (e.target.id === 'cmd-panel') closeCmd(); });
  document.addEventListener('keydown', e => {
    const tag = (e.target && e.target.tagName) || '';
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(tag);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault(); openCmd(false);
    } else if (e.key === 'Escape') { closeCmd(); }
    else if (e.key === '?' && !typing) { e.preventDefault(); openCmd(true); }
  });

  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => {
    try { LS.setItem('st.tab', btn.dataset.tab); } catch (e) { /* ignore */ }
  }));
  document.addEventListener('DOMContentLoaded', () => {
    let saved = null;
    try { saved = LS.getItem('st.tab'); } catch (e) { /* ignore */ }
    if (saved && document.querySelector('.tab[data-tab="' + saved + '"]')) goTab(saved);
  });
})();
