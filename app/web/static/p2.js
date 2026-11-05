/* P2 页面：录入交易 / 预警 / 模拟盘 / 设置 + 持仓手工校正
   所有写操作：勾选确认 + 幂等键 + 明确结果提示。
   包在 IIFE 里，避免与 app.js / p1.js 的顶层 const 重名。 */

(() => {
const ST2 = window.ST;
const { $, api, post, fmt, signed, cls, esc, card,
        showError, clearError, register, finite, tableRows } = ST2;

function clientId(btn) {
  if (!btn.dataset.cid) {
    btn.dataset.cid = (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : 'cid-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  }
  return btn.dataset.cid;
}

async function doWrite(btn, path, body, opts = {}) {
  clearError();
  if (opts.confirmId && !$(opts.confirmId).checked) {
    showError('请先勾选「确认执行」');
    return null;
  }
  const original = btn.textContent;
  btn.disabled = true; btn.textContent = '提交中…';
  try {
    const d = await post(path, Object.assign({}, body, {
      confirm: true, client_id: clientId(btn),
    }));
    delete btn.dataset.cid;                 // 成功后换新键，允许下一笔独立提交
    if (opts.confirmId) $(opts.confirmId).checked = false;
    if (opts.hintId) $(opts.hintId).textContent = d.cached ? '幂等命中：返回上次结果' : '执行成功';
    return d;
  } catch (e) {
    showError(String(e.message || e));
    return null;
  } finally {
    btn.disabled = false; btn.textContent = original;
    // doWrite 成功后会清掉确认勾选，门禁要同步回「未勾选 → 按钮禁用」
    if (window.ST && window.ST.syncConfirmGates) window.ST.syncConfirmGates();
  }
}

/* ---------------- 录入交易 ---------------- */
function loadWrite() {
  const el = $('#w-result');
  if (!el.innerHTML) el.innerHTML = '<div class="result-box dim">填写表单并勾选确认即可写入。写入后会同时重建持仓。</div>';
}

async function submitTrade() {
  const btn = $('#w-submit');
  const body = {
    action: $('#w-side').value,
    code: $('#w-code').value.trim(),
    price: Number($('#w-price').value),
    quantity: Number($('#w-qty').value),
    name: $('#w-name').value.trim(),
    strategy: $('#w-strategy').value.trim(),
    reason: $('#w-reason').value.trim(),
  };
  if (!body.code || !body.price || !body.quantity) { showError('请填完整代码 / 价格 / 数量'); return; }
  const d = await doWrite(btn, '/api/write/trade', body, { confirmId: 'w-confirm', hintId: 'w-hint' });
  if (!d) return;
  const t = d.result.result || d.result;
  $('#w-result').innerHTML = `<div class="result-box ok"><h3>已写入</h3>
    交易 #${esc(t.id)} · ${esc(t.stock_code)} · ${t.action === 'buy' ? '买入' : '卖出'}
    ${fmt(t.quantity, 0)} 股 @ ${fmt(t.price)}（金额 ${fmt(t.amount)}）</div>`;
  $('#w-code').value = ''; $('#w-price').value = '';
  $('#w-name').value = '';
  delete $('#w-name').dataset.autoName;
}

/* ---------------- 预警 ---------------- */
let alertTypesCache = null;

async function loadAlerts() {
  const [d, t] = await Promise.all([api('/api/alerts'), api('/api/alert-types')]);
  alertTypesCache = t.items || [];
  const sel = $('#a-type');
  if (!sel.dataset.filled) {
    sel.innerHTML = alertTypesCache.map(x =>
      `<option value="${esc(x.type || x.value || x.name)}">${esc(x.label || x.desc || x.description || x.name)}</option>`
    ).join('');
    sel.dataset.filled = '1';
  }
  const tbody = $('#alert-list').querySelector('tbody');
  const rows = d.rows || [];
  tbody.innerHTML = rows.length ? rows.map(a => `<tr>
    <td>${esc(a.stock_code)}</td><td>${esc(a.condition_desc || a.condition_type)}</td>
    <td class="num">${a.threshold === null || a.threshold === undefined ? '-' : fmt(a.threshold)}</td>
    <td>${a.is_active ? '<span class="tag good">启用</span>' : '<span class="tag">暂停</span>'}</td>
    <td>${esc(a.note || '')}</td>
    <td><div class="row-actions">
      <button class="btn ghost" data-op="toggle" data-id="${a.id}">启停</button>
      <button class="btn ghost danger" data-op="delete" data-id="${a.id}">删除</button>
    </div></td></tr>`).join('')
    : '<tr><td class="empty" colspan="6">暂无预警规则</td></tr>';
}

async function addAlert() {
  const btn = $('#a-add');
  const threshold = $('#a-threshold').value;
  const body = {
    op: 'add',
    code: $('#a-code').value.trim(),
    condition_type: $('#a-type').value,
    threshold: threshold === '' ? null : Number(threshold),
    repeat: false,
    note: $('#a-note').value.trim(),
  };
  if (!body.code) { showError('请填股票代码'); return; }
  const d = await doWrite(btn, '/api/write/alert', body, { confirmId: 'a-confirm', hintId: 'a-hint' });
  if (d) { $('#a-code').value = ''; $('#a-threshold').value = ''; await loadAlerts(); }
}

async function rowAction(btn) {
  const op = btn.dataset.op, id = Number(btn.dataset.id);
  const label = op === 'toggle' ? '切换启用状态' : '删除';
  if (!window.confirm(`确定要${label}这条预警规则吗？`)) return;
  const d = await doWrite(btn, '/api/write/alert', { op, alert_id: id });
  if (d) await loadAlerts();
}

/* ---------------- 模拟盘 ---------------- */
async function loadPaper() {
  const d = await api('/api/paper');
  const s = d.summary || {};
  $('#paper-cards').innerHTML = [
    card('总资产', fmt(s.equity) + ' 元'),
    card('可用现金', fmt(s.cash) + ' 元'),
    card('总收益率', signed(s.total_return) + '%', cls(s.total_return)),
    card('浮动盈亏', signed(s.unrealized_profit) + ' 元', cls(s.unrealized_profit)),
  ].join('');

  const positions = d.positions || [], orders = d.orders || [];
  $('#paper-positions').querySelector('tbody').innerHTML = positions.length
    ? positions.map(p => `<tr><td>${esc(p.code)}</td><td class="num">${fmt(p.quantity, 0)}</td>
        <td class="num">${fmt(p.avg_cost)}</td>
        <td class="num ${cls(p.realized_profit)}">${signed(p.realized_profit)}</td></tr>`).join('')
    : '<tr><td class="empty" colspan="4">暂无持仓</td></tr>';
  $('#paper-orders').querySelector('tbody').innerHTML = orders.length
    ? orders.slice(0, 10).map(o => `<tr><td>${esc(o.code)}</td>
        <td>${o.side === 'buy' ? '<span class="up">买入</span>' : '<span class="down">卖出</span>'}</td>
        <td class="num">${fmt(o.price)}</td><td class="num">${fmt(o.quantity, 0)}</td></tr>`).join('')
    : '<tr><td class="empty" colspan="4">暂无成交</td></tr>';
}

async function submitPaper(reset = false) {
  const btn = reset ? $('#p-reset') : $('#p-submit');
  if (reset && !window.confirm('确定重置模拟盘账户？所有虚拟持仓与成交记录会被清空。')) return;
  const body = reset
    ? { op: 'reset' }
    : {
        op: $('#p-side').value,
        code: $('#p-code').value.trim(),
        price: Number($('#p-price').value),
        quantity: Number($('#p-qty').value),
      };
  if (!reset && (!body.code || !body.price)) { showError('请填完整代码与价格'); return; }
  const opts = reset ? { hintId: 'p-hint' } : { confirmId: 'p-confirm', hintId: 'p-hint' };
  const d = await doWrite(btn, '/api/write/paper', body, opts);
  if (d) await loadPaper();
}

/* ---------------- 设置 ---------------- */
async function loadSettings() {
  const d = await api('/api/settings');
  const rows = d.rows || [];
  $('#settings-list').querySelector('tbody').innerHTML = rows.map(x => `<tr>
    <td>${esc(x.label)}<div class="dim">${esc(x.key)}</div></td>
    <td>${x.sensitive ? '<span class="tag">' + esc(x.value) + '</span>' : esc(x.value === null ? '未设置' : String(x.value))}</td>
    <td><code>${esc(x.env_key)}</code></td>
    <td>${x.env_set ? '<span class="tag good">环境变量</span>' : '<span class="tag">配置文件/默认值</span>'}</td>
  </tr>`).join('');
  $('#settings-note').textContent = d.note || '';
}

/* ---------------- 注册与事件 ---------------- */
register('write', loadWrite);
register('alerts', loadAlerts);
register('paper', loadPaper);
register('settings', loadSettings);

$('#w-submit').addEventListener('click', submitTrade);
$('#a-add').addEventListener('click', addAlert);
$('#p-submit').addEventListener('click', () => submitPaper(false));
$('#p-reset').addEventListener('click', () => submitPaper(true));
$('#alert-list').querySelector('tbody').addEventListener('click', e => {
  const btn = e.target.closest('button[data-op]');
  if (btn) rowAction(btn);
});

/* ---------------- 行情页：我的自选实时行情 ---------------- */
async function loadWatchlistQuotes() {
  const hint = $('#watchlist-hint');
  hint.textContent = '加载中…';
  try {
    const d = await api('/api/watchlist/quotes');
    const rows = d.rows || [];
    $('#watchlist-time').textContent = '更新于 '
      + String(d.generated_at || '').replace('T', ' ');
    tableRows($('#watchlist-quotes'), rows.map(x => `<tr class="clickable" data-code="${esc(x.code)}">
      <td>${esc(x.code)}</td><td>${esc(x.name || '')}</td>
      <td class="num">${finite(x.price)}</td>
      <td class="num ${cls(x.change_percent)}">${signed(x.change_percent)}%</td>
      <td class="num ${cls(x.change)}">${signed(x.change)}</td>
      <td class="num">${finite(x.open)}</td><td class="num">${finite(x.high)}</td>
      <td class="num">${finite(x.low)}</td>
      <td>${esc(x.note || '')}</td>
      <td><div class="row-actions">
        <button class="btn ghost" data-wl="note" data-code="${esc(x.code)}"
          data-note="${esc(x.note || '')}">改备注</button>
        <button class="btn ghost danger" data-wl="remove"
          data-code="${esc(x.code)}">移除</button>
      </div></td></tr>`).join(''),
      10, '暂无自选股，可在上方表单添加');
    hint.textContent = rows.length
      ? `共 ${rows.length} 只 · 点击一行填入查询 / K 线框，右侧按钮可编辑`
      : '暂无自选股';
  } catch (e) {
    hint.textContent = '自选行情加载失败：' + String(e.message || e);
  }
}

async function loadMarket() {
  await Promise.all([loadQuotes(), loadWatchlistQuotes()]);
}
register('market', loadMarket);

async function wlWrite(btn, op, extra = {}) {
  const code = $('#wl-code').value.trim();
  if (!code) { showError('请填股票代码'); return; }
  const body = Object.assign({ op, code, note: $('#wl-note').value.trim() }, extra);
  const d = await doWrite(btn, '/api/write/watchlist', body,
    { confirmId: 'wl-confirm', hintId: 'wl-hint' });
  if (!d) return;
  if (op === 'add') { $('#wl-code').value = ''; $('#wl-note').value = ''; }
  await loadWatchlistQuotes();
}

async function removeWatch(btn) {
  const code = btn.dataset.code;
  if (!window.confirm(`确定从自选中移除 ${code}？（只取消关注，不会删除股票记录）`)) return;
  const d = await doWrite(btn, '/api/write/watchlist', { op: 'remove', code });
  if (d) await loadWatchlistQuotes();
}

$('#watchlist-refresh').addEventListener('click', loadWatchlistQuotes);
$('#wl-add').addEventListener('click', e => wlWrite(e.currentTarget, 'add'));
$('#wl-note-save').addEventListener('click', e => wlWrite(e.currentTarget, 'note'));
$('#watchlist-quotes').querySelector('tbody').addEventListener('click', e => {
  const btn = e.target.closest('button[data-wl]');
  if (btn) {
    if (btn.dataset.wl === 'note') {
      $('#wl-code').value = btn.dataset.code;
      $('#wl-note').value = btn.dataset.note || '';
      $('#wl-note').focus();
      $('#wl-hint').textContent = '改好备注后勾选确认，点「保存备注」';
    } else if (btn.dataset.wl === 'remove') {
      removeWatch(btn);
    }
    return;
  }
  const tr = e.target.closest('tr[data-code]');
  if (!tr) return;
  $('#codes').value = tr.dataset.code;
  $('#kline-code').value = tr.dataset.code;
});

/* ---------------- 持仓手工校正（覆盖 P1 的只读交易持仓页） ---------------- */
async function loadTradesWithEdit() {
  const showCleared = $('#pos-show-cleared').checked;
  const [p, t] = await Promise.all([
    api('/api/portfolio?include_cleared=' + showCleared),
    api('/api/trades?limit=30'),
  ]);
  const holdings = p.holdings || [];
  const active = holdings.filter(h => !h.is_cleared).length;
  $('#pos-summary').textContent = `当前持仓 ${active} 只`
    + (showCleared ? ` · 已清仓 ${holdings.length - active} 只` : '');

  tableRows($('#trades-holdings'), holdings.map(h => `<tr class="${h.is_cleared ? 'cleared' : ''}">
    <td>${esc(h.stock_code)}</td><td>${esc(h.stock_name || '')}</td>
    <td class="num">${finite(h.quantity, 0)}</td><td class="num">${finite(h.avg_cost)}</td>
    <td class="num">${finite(h.current_price)}</td>
    <td class="num ${cls(h.unrealized_profit)}">${signed(h.unrealized_profit)}</td>
    <td>${h.is_cleared ? '<span class="tag bad">已清仓</span> ' : ''}${h.manual_override
      ? `<span class="tag bad" title="${esc(h.override_note || '')}">手工锁定</span>`
      : '<span class="tag">交易派生</span>'}</td>
    <td><div class="row-actions">
      <button class="btn ghost" data-pos="edit" data-code="${esc(h.stock_code)}"
        data-qty="${h.quantity}" data-cost="${h.avg_cost}"
        data-name="${esc(h.stock_name || '')}">编辑</button>
      ${h.is_cleared ? ''
        : `<button class="btn ghost danger" data-pos="clear" data-code="${esc(h.stock_code)}">清仓</button>`}
      ${h.manual_override
        ? `<button class="btn ghost" data-pos="unlock" data-code="${esc(h.stock_code)}">解除锁定</button>`
        : ''}
    </div></td></tr>`).join(''), 8, showCleared ? '暂无持仓记录' : '当前无持仓（可勾选「显示已清仓」）');

  tableRows($('#trades-list'), (t.rows || []).map(x => `<tr>
    <td>${esc(String(x.trade_time || '').slice(0, 16))}</td>
    <td>${esc(x.stock_code)}</td>
    <td>${x.action === 'buy' ? '<span class="up">买入</span>' : '<span class="down">卖出</span>'}</td>
    <td class="num">${finite(x.price)}</td><td class="num">${finite(x.quantity, 0)}</td>
    <td class="num ${cls(x.profit)}">${x.profit === null || x.profit === undefined ? '-' : signed(x.profit)}</td>
    <td>${esc(x.strategy || '')}</td></tr>`).join(''), 7, '暂无交易记录');
}
register('trades', loadTradesWithEdit);

/* ---------------- 代码 → 名称自动填充 ----------------
   优先走 /api/stock/name（本地库命中不触网）。只覆盖「空名称」或
   「上次自动填充的名称」，用户手动改过的名称一律保留。 */
const NAME_FILL_TIMERS = {};

function autoFillName(codeId, nameId) {
  const codeEl = $(codeId), nameEl = $(nameId);
  if (!codeEl || !nameEl) return;
  const code = codeEl.value.trim();
  const auto = nameEl.dataset.autoName || '';
  if (nameEl.value && nameEl.value !== auto) return;
  if (!code) return;
  api('/api/stock/name?code=' + encodeURIComponent(code)).then(d => {
    if (codeEl.value.trim() !== code) return;   // 期间代码又变了
    if (d.name) {
      nameEl.value = d.name;
      nameEl.dataset.autoName = d.name;
    }
  }).catch(() => { /* 查不到名称时保持可手填 */ });
}

function bindNameFill(codeId, nameId) {
  const el = $(codeId);
  if (!el) return;
  el.addEventListener('input', () => {
    clearTimeout(NAME_FILL_TIMERS[codeId]);
    NAME_FILL_TIMERS[codeId] = setTimeout(() => autoFillName(codeId, nameId), 300);
  });
  el.addEventListener('change', () => {
    clearTimeout(NAME_FILL_TIMERS[codeId]);
    autoFillName(codeId, nameId);
  });
}
bindNameFill('pos-code', 'pos-name');
bindNameFill('w-code', 'w-name');

/* 金额实时预估：价格 × 数量，输入时即时显示 */
function bindAmountPreview() {
  [
    { price: 'w-price', qty: 'w-qty', out: 'w-amount', label: '预估金额' },
    { price: 'pos-cost', qty: 'pos-qty', out: 'pos-amount', label: '预估成本' },
  ].forEach(p => {
    const a = $(p.price), b = $(p.qty), out = $(p.out);
    if (!a || !b || !out) return;
    const sync = () => {
      const v = Number(a.value) * Number(b.value);
      out.textContent = Number.isFinite(v) && v > 0
        ? p.label + ' ' + fmt(v, 2) + ' 元' : '';
    };
    a.addEventListener('input', sync);
    b.addEventListener('input', sync);
    sync();
  });
}
bindAmountPreview();

function openPosEdit(btn, mode = 'edit') {
  const box = $('#pos-edit-box');
  const creating = mode === 'create';
  box.dataset.mode = mode;
  box.dataset.code = creating ? '' : btn.dataset.code;
  $('#pos-edit-title').textContent = creating ? '新增持仓' : '编辑持仓';
  $('#pos-edit-code').textContent = creating ? '' : btn.dataset.code;
  $('#pos-code-wrap').classList.toggle('hidden', !creating);
  $('#pos-code').value = '';
  $('#pos-qty').value = creating ? '' : btn.dataset.qty;
  $('#pos-cost').value = creating ? '' : btn.dataset.cost;
  $('#pos-name').value = creating ? '' : btn.dataset.name;
  delete $('#pos-name').dataset.autoName;
  $('#pos-reason').value = '';
  $('#pos-confirm').checked = false;
  $('#pos-hint').textContent = creating
    ? '新增需填代码、数量与成本价，保存后该行会被手工锁定' : '';
  box.classList.remove('hidden');
  box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function savePosEdit() {
  const btn = $('#pos-save');
  const box = $('#pos-edit-box');
  const creating = box.dataset.mode === 'create';
  const code = creating ? $('#pos-code').value.trim() : box.dataset.code;
  if (!code) { showError('请填股票代码'); return; }
  if ($('#pos-qty').value === '' || $('#pos-cost').value === '') {
    showError('数量与成本价都必须填写'); return;
  }
  const body = {
    op: 'edit', code,
    quantity: Number($('#pos-qty').value),
    avg_cost: Number($('#pos-cost').value),
    name: $('#pos-name').value.trim(),
    reason: $('#pos-reason').value.trim(),
  };
  const d = await doWrite(btn, '/api/write/portfolio', body,
    { confirmId: 'pos-confirm', hintId: 'pos-hint' });
  if (!d) return;
  box.classList.add('hidden');
  delete box.dataset.code;
  await loadTradesWithEdit();
}

async function clearPos(btn) {
  const code = btn.dataset.code;
  if (!window.confirm(`确定把 ${code} 标记为已清仓？数量会置 0 并锁定该行。`)) return;
  const d = await doWrite(btn, '/api/write/portfolio',
    { op: 'clear', code, reason: '页面手工清仓' });
  if (d) await loadTradesWithEdit();
}

async function unlockPos(btn) {
  const code = btn.dataset.code;
  if (!window.confirm(`解除 ${code} 的手工锁定？会立即按交易记录恢复该持仓。`)) return;
  const d = await doWrite(btn, '/api/write/portfolio', { op: 'unlock', code });
  if (d) await loadTradesWithEdit();
}

async function rebuildPos() {
  if (!window.confirm('确定从交易记录全量重建？所有手工校正都会被清除且不可恢复。')) return;
  const btn = $('#pos-rebuild');
  const d = await doWrite(btn, '/api/write/portfolio', { op: 'rebuild' },
    { hintId: 'pos-rebuild-hint' });
  if (d) await loadTradesWithEdit();
}

$('#trades-holdings').querySelector('tbody').addEventListener('click', e => {
  const btn = e.target.closest('button[data-pos]');
  if (!btn) return;
  const op = btn.dataset.pos;
  if (op === 'edit') openPosEdit(btn);
  else if (op === 'unlock') unlockPos(btn);
  else if (op === 'clear') clearPos(btn);
});
$('#pos-add').addEventListener('click', () => openPosEdit(null, 'create'));
$('#pos-show-cleared').addEventListener('change', loadTradesWithEdit);
$('#pos-save').addEventListener('click', savePosEdit);
$('#pos-cancel').addEventListener('click', () => $('#pos-edit-box').classList.add('hidden'));
$('#pos-rebuild').addEventListener('click', rebuildPos);
})();
