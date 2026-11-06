/* Stock Trader AI 本地 Web UI — 原生 JS，无构建、无 CDN */

/* 兼容两种调用：$('id') 与 $('#id') —— 历史上两种写法都存在，
   getElementById 对 '#id' 永远返回 null，这里统一剥掉前缀。 */
const $ = (sel) => document.getElementById(String(sel).replace(/^#/, ''));
let activeTab = 'overview';

function setStatus(online, text) {
  const el = $('status');
  el.className = 'status ' + (online ? 'online' : 'offline');
  el.innerHTML = '<i></i>' + (text || (online ? '服务正常' : '服务不可用'));
}

function showError(err) {
  const el = $('alert');
  el.textContent = err;
  el.classList.remove('hidden');
}
function clearError() { $('alert').classList.add('hidden'); }

async function api(path) {
  const res = await fetch(path);
  let payload;
  try { payload = await res.json(); } catch (e) { throw new Error('服务返回格式异常'); }
  if (!res.ok || !payload.ok) throw new Error(payload.error || ('HTTP ' + res.status));
  return payload.data;
}

function fmt(v, digits = 2) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '-';
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function signed(v, digits = 2) {
  const n = Number(v || 0);
  return (n >= 0 ? '+' : '') + fmt(n, digits);
}
function cls(v) { const n = Number(v || 0); return n > 0 ? 'up' : (n < 0 ? 'down' : 'neutral'); }
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function emptyRow(table, colspan, text) {
  table.querySelector('tbody').innerHTML =
    `<tr><td class="empty" colspan="${colspan}">${esc(text)}</td></tr>`;
}

function card(k, v, color = '', hint = '') {
  return `<div class="card"><div class="k">${esc(k)}</div>
    <div class="v ${color}">${v}</div>${hint ? `<div class="hint">${esc(hint)}</div>` : ''}</div>`;
}

/* ---------------- 总览 ---------------- */
async function loadOverview() {
  const d = await api('/api/overview');
  const p = d.portfolio || {}, a = d.analysis || {};
  $('overview-time').textContent = '更新于 ' + (d.generated_at || '-').replace('T', ' ');
  $('version').textContent = 'v' + (window.ST.version || '-');

  const profit = p.total_profit || 0;
  $('cards').innerHTML = [
    card('总盈亏', signed(profit) + ' 元', cls(profit)),
    card('浮动盈亏', signed(p.total_unrealized_profit) + ' 元', cls(p.total_unrealized_profit)),
    card('持仓市值', fmt(p.total_market_value) + ' 元', 'neutral', `${fmt(p.total_cost)} 元成本`),
    card('交易笔数', fmt(a.total_trades, 0), 'neutral', `胜率 ${fmt(a.win_rate, 1)}%`),
  ].join('');

  $('meta-cards').innerHTML = [
    card('启用预警', fmt(d.alerts_active, 0), 'neutral'),
    card('ML 模型', fmt(d.models, 0), 'neutral'),
    card('报告文件', fmt(d.reports, 0), 'neutral'),
  ].join('');

  const warnings = d.warnings || [];
  $('warnings').innerHTML = warnings.length
    ? '⚠️ ' + warnings.map(esc).join(' · ') : '';

  const holdings = p.holdings || [];
  const tbody = $('holdings').querySelector('tbody');
  if (!holdings.length) { emptyRow($('holdings'), 8, '当前无持仓'); return; }
  tbody.innerHTML = holdings.map(h => {
    const pnl = h.unrealized_profit || 0, rate = h.unrealized_profit_rate || 0;
    return `<tr><td>${esc(h.stock_code)}</td><td>${esc(h.stock_name || '')}</td>
      <td class="num">${fmt(h.quantity, 0)}</td><td class="num">${fmt(h.avg_cost)}</td>
      <td class="num">${fmt(h.current_price)}</td><td class="num">${fmt(h.market_value)}</td>
      <td class="num ${cls(pnl)}">${signed(pnl)}</td>
      <td class="num ${cls(rate)}">${signed(rate)}%</td></tr>`;
  }).join('');
}

/* ---------------- 行情 ---------------- */
async function loadQuotes() {
  const codes = $('codes').value.trim();
  if (!codes) { showError('请输入股票代码'); return; }
  const d = await api('/api/quote?codes=' + encodeURIComponent(codes));
  const tbody = $('quotes').querySelector('tbody');
  if (!d.rows.length) { emptyRow($('quotes'), 8, '未获取到行情，请检查代码或数据源'); return; }
  tbody.innerHTML = d.rows.map(q => {
    const chg = q.change_percent || 0;
    return `<tr><td>${esc(q.code)}</td><td>${esc(q.name || '')}</td>
      <td class="num">${fmt(q.price)}</td><td class="num ${cls(chg)}">${signed(chg)}%</td>
      <td class="num ${cls(q.change)}">${signed(q.change)}</td>
      <td class="num">${fmt(q.open)}</td><td class="num">${fmt(q.high)}</td>
      <td class="num">${fmt(q.low)}</td></tr>`;
  }).join('');
}

async function loadKline() {
  const code = $('kline-code').value.trim();
  if (!code) { showError('请输入股票代码'); return; }
  const d = await api('/api/kline?code=' + encodeURIComponent(code) + '&count=120');
  const rows = (d.rows || []).filter(r => r.close !== null && r.close !== undefined);
  if (rows.length < 2) { $('chart').innerHTML = '<span class="dim">K 线数据不足</span>'; return; }

  const vals = rows.map(r => Number(r.close));
  const min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const W = 800, H = 200, PAD = 10;
  const pts = vals.map((v, i) => {
    const x = PAD + i * (W - 2 * PAD) / (vals.length - 1);
    const y = H - PAD - ((v - min) / span) * (H - 2 * PAD);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const rising = vals[vals.length - 1] >= vals[0];
  const color = rising ? '#e5484d' : '#30a46c';
  const area = `M${pts[0]} L` + pts.slice(1).join(' L') + ` L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z`;

  $('chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#g)"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>
    <text x="${PAD}" y="14" fill="#8b95a5" font-size="11">${esc(code)} · ${fmt(min)} ~ ${fmt(max)}</text>
    <text x="${W - PAD}" y="14" fill="#8b95a5" font-size="11" text-anchor="end">${esc(rows[rows.length - 1].date || '')}</text>
  </svg>`;
}

/* ---------------- 报告 ---------------- */
async function openMarkdownReport(name) {
  clearError();
  try {
    const d = await api('/api/reports/' + encodeURIComponent(name) + '/content');
    const box = $('report-body');
    box.classList.remove('hidden');
    const pre = document.createElement('pre');
    pre.className = 'report-md';
    pre.textContent = String(d.content ?? '');
    box.replaceChildren(pre);
  } catch (e) {
    showError(String(e.message || e));
  }
}

async function loadReports() {
  const d = await api('/api/reports');
  const files = d.files || [];
  const body = $('report-body');
  if (!files.length) {
    $('report-list').innerHTML = '<div class="card dim">暂无报告，运行 <code>stock-ai report</code> 或等待每日定时任务生成</div>';
    if (body) {
      body.classList.add('hidden');
      body.replaceChildren();
    }
    return;
  }
  $('report-list').innerHTML = files.map(f => {
    const kb = (f.size / 1024).toFixed(1);
    const tag = f.kind === 'html' ? '<span class="badge html">HTML</span>' : '<span class="badge">MD</span>';
    const head = `<div class="name">${esc(f.name)}${tag}</div>`;
    const meta = `<div class="meta">${kb} KB · ${esc((f.updated_at || '').replace('T', ' '))}</div>`;
    if (f.kind === 'html') {
      const href = `/reports/${encodeURIComponent(f.name)}`;
      return `<a class="report-item" href="${href}" target="_blank" rel="noopener">${head}${meta}</a>`;
    }
    return `<button type="button" class="report-item" data-md="${esc(f.name)}" onclick="openMarkdownReport(this.getAttribute('data-md'))">${head}${meta}</button>`;
  }).join('');
}
globalThis.loadReports = loadReports;
globalThis.openMarkdownReport = openMarkdownReport;

/* ---------------- 公共能力（供 p1.js 复用） ---------------- */
async function post(path, body) {
  const res = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let payload;
  try { payload = await res.json(); } catch (e) { throw new Error('服务返回格式异常'); }
  if (!res.ok || !payload.ok) throw new Error(payload.error || ('HTTP ' + res.status));
  return payload.data;
}

function sparkline(vals, label) {
  const clean = vals.filter(v => v !== null && v !== undefined && !Number.isNaN(Number(v))).map(Number);
  if (clean.length < 2) return '<span class="dim">数据点不足</span>';
  const min = Math.min(...clean), max = Math.max(...clean), span = (max - min) || 1;
  const W = 800, H = 200, PAD = 10;
  const pts = clean.map((v, i) => {
    const x = PAD + i * (W - 2 * PAD) / (clean.length - 1);
    const y = H - PAD - ((v - min) / span) * (H - 2 * PAD);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const rising = clean[clean.length - 1] >= clean[0];
  const color = rising ? '#e5484d' : '#30a46c';
  const area = `M${pts[0]} L` + pts.slice(1).join(' L') + ` L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z`;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${area}" fill="url(#sg)"/>
    <polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>
    <text x="${PAD}" y="14" fill="#8b95a5" font-size="11">${esc(label)} · ${fmt(min)} ~ ${fmt(max)}</text>
  </svg>`;
}

/* ---------------- 调度 ---------------- */
const loaders = { overview: loadOverview, market: loadQuotes, reports: loadReports };

window.ST = {
  $, api, post, fmt, signed, cls, esc, emptyRow, card, sparkline,
  setStatus, showError, clearError,
  finite(v, digits = 2) {
    const n = Number(v);
    return Number.isFinite(n) ? fmt(n, digits) : '-';
  },
  tableRows(table, rows, cols, emptyText) {
    if (!rows || !rows.length) { emptyRow(table, cols, emptyText || '暂无数据'); return; }
    table.querySelector('tbody').innerHTML = rows;
  },
  register(name, loader) { loaders[name] = loader; },
};

async function refresh() {
  clearError();
  try {
    /* health 与页面数据并行；version 在这里统一写入，避免 loadOverview
       再发一次 /api/health（原来是串行两次请求）。 */
    const healthP = api('/api/health');
    const loaderP = loaders[activeTab] ? loaders[activeTab]() : Promise.resolve();
    const health = await healthP;
    window.ST.version = health.version;
    $('version').textContent = 'v' + health.version;
    setStatus(true);
    await loaderP;
  } catch (e) {
    setStatus(false, '连接失败');
    showError(String(e.message || e) + ' · 请确认服务已启动（双击 启动.bat）');
  }
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeTab = btn.dataset.tab;
    document.querySelectorAll('.panel').forEach(p => p.classList.add('hidden'));
    $('panel-' + activeTab).classList.remove('hidden');
    refresh();
  });
});
$('refresh').addEventListener('click', () => {
  if (window.ST && window.ST.forceRefresh) window.ST.forceRefresh();
  else refresh();
});
$('quote-btn').addEventListener('click', () => refreshSafe(loadQuotes));
$('kline-btn').addEventListener('click', () => refreshSafe(loadKline));
$('codes').addEventListener('keydown', e => { if (e.key === 'Enter') refreshSafe(loadQuotes); });
$('kline-code').addEventListener('keydown', e => { if (e.key === 'Enter') refreshSafe(loadKline); });

async function refreshSafe(fn) {
  clearError();
  try { setStatus(true); await fn(); }
  catch (e) { showError(String(e.message || e)); }
}

/* 等 ux.js / p1.js / p2.js 都注册完再跑首次加载，
   这样增强层（超时、缓存、骨架、表格工具条）对首屏同样生效。 */
document.addEventListener('DOMContentLoaded', () => window.refresh());
