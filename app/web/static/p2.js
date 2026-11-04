/* P2 页面：录入交易 / 预警 / 模拟盘 / 设置
   所有写操作：勾选确认 + 幂等键 + 明确结果提示。 */

const ST2 = window.ST;
const { $, api, post, fmt, signed, cls, esc, card, showError, clearError, register } = ST2;

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
