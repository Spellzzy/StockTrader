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
  if (!holdings.length) {
    emptyRow($('holdings'), 8, '当前无持仓');
  } else {
    const tbody = $('holdings').querySelector('tbody');
    tbody.innerHTML = holdings.map(h => {
      const pnl = h.unrealized_profit || 0, rate = h.unrealized_profit_rate || 0;
      return `<tr><td>${esc(h.stock_code)}</td><td>${esc(h.stock_name || '')}</td>
        <td class="num">${fmt(h.quantity, 0)}</td><td class="num">${fmt(h.avg_cost)}</td>
        <td class="num">${fmt(h.current_price)}</td><td class="num">${fmt(h.market_value)}</td>
        <td class="num ${cls(pnl)}">${signed(pnl)}</td>
        <td class="num ${cls(rate)}">${signed(rate)}%</td></tr>`;
    }).join('');
  }
  await loadTodayDigest();
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
function reportBadge(kind) {
  if (kind === 'html') return '<span class="badge html">HTML</span>';
  if (kind === 'json') return '<span class="badge json">JSON</span>';
  return '<span class="badge">MD</span>';
}

function finiteNumber(v) {
  if (typeof v === 'boolean' || typeof v !== 'number' || !Number.isFinite(v)) return null;
  return v;
}

/* quality 上有可用数字就用它；显式 null 才回落到条目。非空的坏值不回落，避免编造。 */
function preferQualityNumber(quality, item, key) {
  if (quality && Object.prototype.hasOwnProperty.call(quality, key)) {
    const fromQuality = finiteNumber(quality[key]);
    if (fromQuality !== null) return fromQuality;
    if (quality[key] != null) return null;
  }
  if (item && Object.prototype.hasOwnProperty.call(item, key)) return finiteNumber(item[key]);
  return null;
}

function qualityPreviewText(q) {
  if (!q || typeof q !== 'object' || Array.isArray(q)) return '';
  const bits = [];
  if (q.below_baseline === true) bits.push('弱于基线');
  else if (q.below_baseline === false) bits.push('优于基线');
  const acc = q.mean_accuracy;
  const base = q.baseline;
  if (typeof acc === 'number' && typeof base === 'number') {
    bits.push(`准确率 ${(acc * 100).toFixed(1)}% · 基线 ${(base * 100).toFixed(1)}%`);
  } else if (typeof acc === 'number') {
    bits.push(`准确率 ${(acc * 100).toFixed(1)}%`);
  } else if (typeof base === 'number') {
    bits.push(`基线 ${(base * 100).toFixed(1)}%`);
  }
  if (typeof q.factor === 'number') bits.push(`降权 ${q.factor.toFixed(2)}`);
  if (typeof q.note === 'string' && q.note.trim()) bits.push(q.note.trim());
  return bits.join(' · ');
}

function digestSnapshot(item) {
  const src = item && typeof item === 'object' && !Array.isArray(item) ? item : {};
  const snap = {
    code: src.code == null ? '' : String(src.code),
    name: src.name == null ? '' : String(src.name),
    signal: src.signal,
    score: src.score,
    stars: src.stars,
    confidence: src.confidence,
    models_used: src.models_used,
    key_factors: Array.isArray(src.key_factors) ? src.key_factors.slice() : [],
  };
  if (Object.prototype.hasOwnProperty.call(src, 'quality')) snap.quality = src.quality;
  if (Object.prototype.hasOwnProperty.call(src, 'trade_range')) snap.trade_range = src.trade_range;
  return snap;
}

function formatCount(n) {
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

function signed1(n) {
  const text = n.toFixed(1);
  if (n > 0) return '+' + text;
  if (n === 0) return '+0.0';
  return text;
}

/* 抽屉「可信证据」只吃行快照。缺数字就省略该行，不现场重算。 */
function renderDigestEvidence(item) {
  const snapshot = item && typeof item === 'object' && !Array.isArray(item) ? item : {};
  const q = snapshot.quality;
  const valid = !!q && typeof q === 'object' && !Array.isArray(q);
  if (!valid) {
    return '<section class="digest-evidence" aria-label="可信证据">'
      + '<h3>可信证据</h3><div class="dim">本条无质量字段</div></section>';
  }
  const below = q.below_baseline === true;
  const noteRaw = typeof q.note === 'string' ? q.note.trim() : '';
  const note = noteRaw || (below ? '弱于基线，勿当强信号' : '质量正常');
  const rows = [];
  const signalBits = [];
  if (typeof snapshot.signal === 'string' && snapshot.signal.trim()) {
    signalBits.push(snapshot.signal.trim());
  }
  const score = finiteNumber(snapshot.score);
  if (score !== null) signalBits.push('评分 ' + signed1(score));
  const stars = finiteNumber(snapshot.stars);
  if (stars !== null && stars > 0) {
    const count = Math.min(5, Math.floor(stars));
    if (count > 0) signalBits.push('⭐'.repeat(count));
  }
  if (signalBits.length) rows.push(['信号', signalBits.join(' · ')]);
  if (q.below_baseline === true) rows.push(['质量', '弱于基线']);
  else if (q.below_baseline === false) rows.push(['质量', '优于基线']);
  rows.push(['说明', note]);
  const acc = finiteNumber(q.mean_accuracy);
  const base = finiteNumber(q.baseline);
  if (acc !== null && base !== null) {
    rows.push(['准确率 · 基线', `${(acc * 100).toFixed(1)}% · ${(base * 100).toFixed(1)}%`]);
  } else if (acc !== null) {
    rows.push(['准确率', `${(acc * 100).toFixed(1)}%`]);
  } else if (base !== null) {
    rows.push(['基线', `${(base * 100).toFixed(1)}%`]);
  }
  const factor = finiteNumber(q.factor);
  if (factor !== null) rows.push(['降权', factor.toFixed(2)]);
  const conf = preferQualityNumber(q, snapshot, 'confidence');
  if (conf !== null) rows.push(['置信度', conf.toFixed(1) + '%']);
  const models = preferQualityNumber(q, snapshot, 'models_used');
  if (models !== null) rows.push(['模型数', formatCount(models)]);
  const factors = Array.isArray(snapshot.key_factors) ? snapshot.key_factors : [];
  const shown = [];
  for (let i = 0; i < factors.length && shown.length < 3; i++) {
    const text = String(factors[i] == null ? '' : factors[i]).trim();
    if (text) shown.push(text);
  }
  if (shown.length) rows.push(['依据', shown.join('、')]);
  const tr = snapshot.trade_range;
  const hasRange = tr && typeof tr === 'object'
    && ['low', 'high', 'buy', 'sell'].every(k => Number.isFinite(Number(tr[k])));
  if (hasRange) {
    rows.push(['今日参考区间',
      `${Number(tr.low).toFixed(2)} ~ ${Number(tr.high).toFixed(2)}`
      + ` · 买 ${Number(tr.buy).toFixed(2)} / 卖 ${Number(tr.sell).toFixed(2)}（统计参考）`]);
  }
  const kv = '<div class="detail-kv">' + rows.map(([k, v]) =>
    `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join('') + '</div>';
  const body = below ? `<div class="quality-warn">${kv}</div>` : kv;
  return `<section class="digest-evidence" aria-label="可信证据"><h3>可信证据</h3>${body}</section>`;
}

function eventEl(target) {
  if (!target) return null;
  if (target.nodeType === 3) return target.parentElement || null;
  return target;
}

function readRowEvidence(row) {
  if (!row) return null;
  let raw = '';
  if (typeof row.getAttribute === 'function') raw = row.getAttribute('data-evidence') || '';
  if (!raw && row.dataset) raw = row.dataset.evidence || '';
  if (!raw) return null;
  try { return JSON.parse(decodeURIComponent(raw)); }
  catch (e) { return null; }
}

function activateDigestEvidenceRow(row) {
  if (!row || !window.ST || typeof window.ST.openStockDetail !== 'function') return;
  const evidence = readRowEvidence(row) || {};
  const code = String(evidence.code || (row.dataset && row.dataset.code) || '').trim();
  if (!code) return;
  window.ST.openStockDetail(code, { evidence });
}

function digestRows(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return '<div class="dim">无</div>';
  const body = rows.map(item => {
    const q = item && item.quality;
    const conf = q && typeof q.confidence === 'number' ? q.confidence : item && item.confidence;
    const models = q && typeof q.models_used === 'number' ? q.models_used : item && item.models_used;
    const quality = qualityPreviewText(q);
    const extra = typeof models === 'number'
      ? (quality ? ' · ' : '') + '模型数 ' + (Number.isInteger(models) ? String(models) : models.toFixed(2))
      : '';
    const score = Number(item && item.score);
    const snap = digestSnapshot(item);
    const tr = item && item.trade_range;
    const hasRange = tr && typeof tr === 'object'
      && Number.isFinite(Number(tr.low)) && Number.isFinite(Number(tr.high))
      && Number.isFinite(Number(tr.buy)) && Number.isFinite(Number(tr.sell));
    const rangeLine = hasRange
      ? `<div class="dim">📐 区间 ${Number(tr.low).toFixed(2)} ~ ${Number(tr.high).toFixed(2)}`
        + ` · 买 ${Number(tr.buy).toFixed(2)} / 卖 ${Number(tr.sell).toFixed(2)}（统计参考）</div>`
      : '';
    const label = '查看'
      + (snap.code ? ' ' + snap.code : '')
      + (snap.name ? ' ' + snap.name : '')
      + ' 的可信证据';
    return `<tr class="clickable digest-evidence-row" role="button" tabindex="0"
      data-code="${esc(snap.code)}"
      data-evidence="${encodeURIComponent(JSON.stringify(snap))}"
      aria-label="${esc(label)}"
      title="点击、回车或空格打开个股详情中的可信证据">
      <td>${esc(snap.code)}</td>
      <td>${esc(snap.name)}</td>
      <td>${esc(item && item.signal)}</td>
      <td class="num">${Number.isFinite(score) ? score.toFixed(1) : '-'}</td>
      <td class="num">${typeof conf === 'number' ? conf.toFixed(1) + '%' : '-'}</td>
      <td>${esc(quality)}${esc(extra)}${rangeLine}</td>
    </tr>`;
  }).join('');
  return `<div class="table-wrap"><table><thead><tr>
      <th>代码</th><th>名称</th><th>信号</th><th class="num">评分</th>
      <th class="num">置信度</th><th>质量</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}

const DIGEST_JSON_NAME = /^digest_.+\.json$/;

function pickLatestDigestFile(files) {
  const list = Array.isArray(files) ? files : [];
  for (let i = 0; i < list.length; i++) {
    const file = list[i];
    if (!file || file.kind !== 'json') continue;
    if (DIGEST_JSON_NAME.test(String(file.name || ''))) return file;
  }
  return null;
}

function setTodayDigestOpen(name) {
  const btn = $('today-digest-open');
  if (!btn) return;
  if (name) {
    btn.disabled = false;
    btn.hidden = false;
    if (btn.classList) btn.classList.remove('hidden');
    if (btn.dataset) btn.dataset.name = name;
    return;
  }
  btn.disabled = true;
  if (btn.dataset) btn.dataset.name = '';
}

function showTodayDigestEmpty(text) {
  const box = $('today-digest');
  if (box) box.innerHTML = `<div class="dim">${esc(text)}</div>`;
  const meta = $('today-digest-meta');
  if (meta) meta.textContent = '';
  setTodayDigestOpen('');
}

function renderTodayDigest(name, data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    showTodayDigestEmpty('日报读取失败');
    return;
  }
  const bullish = Array.isArray(data.bullish) ? data.bullish : [];
  const bearish = Array.isArray(data.bearish) ? data.bearish : [];
  const neutral = Array.isArray(data.neutral) ? data.neutral : [];
  const total = data.total === undefined || data.total === null || data.total === '' ? '-' : data.total;
  const meta = $('today-digest-meta');
  if (meta) {
    meta.textContent = `${data.date || '-'} · ${data.slot || '-'} · ${total} 只 · 震荡 ${neutral.length}`;
  }
  const box = $('today-digest');
  if (box) {
    box.innerHTML = `<h3>看涨 · ${bullish.length}</h3>${digestRows(bullish.slice(0, 5))}
      <h3>看跌 · ${bearish.length}</h3>${digestRows(bearish.slice(0, 5))}`;
  }
  setTodayDigestOpen(name);
}

async function loadTodayDigest() {
  try {
    const listed = await api('/api/reports');
    const file = pickLatestDigestFile(listed && listed.files);
    if (!file) {
      showTodayDigestEmpty('暂无结构化日报');
      return;
    }
    const data = await api('/api/reports/' + encodeURIComponent(file.name) + '/content');
    renderTodayDigest(file.name, data);
  } catch (e) {
    showTodayDigestEmpty('日报读取失败');
  }
}

function renderDigestPreview(name, data) {
  const box = document.createElement('div');
  box.className = 'report-json';
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    box.textContent = '无法按结构化日报预览';
    return box;
  }
  const total = data.total === undefined || data.total === null ? '-' : data.total;
  box.innerHTML = `<div class="report-json-head"><strong>${esc(name || '结构化日报')}</strong>
      <span class="dim">只读预览 · ${esc(data.date || '-')} · ${esc(data.slot || '-')} · ${esc(total)} 只</span></div>
    <h3>看涨 · ${(Array.isArray(data.bullish) ? data.bullish.length : 0)}</h3>${digestRows(data.bullish)}
    <h3>看跌 · ${(Array.isArray(data.bearish) ? data.bearish.length : 0)}</h3>${digestRows(data.bearish)}
    <h3>震荡 · ${(Array.isArray(data.neutral) ? data.neutral.length : 0)}</h3>${digestRows(data.neutral)}`;
  return box;
}

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

async function openJsonReport(name) {
  clearError();
  try {
    const data = await api('/api/reports/' + encodeURIComponent(name) + '/content');
    const box = $('report-body');
    box.classList.remove('hidden');
    box.replaceChildren(renderDigestPreview(name, data));
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
    const head = `<div class="name">${esc(f.name)}${reportBadge(f.kind)}</div>`;
    const meta = `<div class="meta">${kb} KB · ${esc((f.updated_at || '').replace('T', ' '))}</div>`;
    if (f.kind === 'html') {
      const href = `/reports/${encodeURIComponent(f.name)}`;
      return `<a class="report-item" href="${href}" target="_blank" rel="noopener">${head}${meta}</a>`;
    }
    if (f.kind === 'json') {
      return `<button type="button" class="report-item" data-json="${esc(f.name)}" onclick="openJsonReport(this.getAttribute('data-json'))">${head}${meta}</button>`;
    }
    return `<button type="button" class="report-item" data-md="${esc(f.name)}" onclick="openMarkdownReport(this.getAttribute('data-md'))">${head}${meta}</button>`;
  }).join('');
}
globalThis.loadReports = loadReports;
globalThis.openMarkdownReport = openMarkdownReport;
globalThis.openJsonReport = openJsonReport;
globalThis.renderDigestPreview = renderDigestPreview;
globalThis.pickLatestDigestFile = pickLatestDigestFile;
globalThis.loadOverview = loadOverview;
globalThis.loadTodayDigest = loadTodayDigest;
globalThis.openTodayDigestReport = openTodayDigestReport;

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
  setStatus, showError, clearError, renderDigestEvidence, activateDigestEvidenceRow,
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

/* 侧栏项仍是 .tab + data-tab。命令面板、空状态按钮和 #stock= 深链
   都通过点击这些按钮进入同一条切页路径。 */
let suppressTabRefresh = false;

function showTab(name) {
  const leaving = activeTab;
  activeTab = name;
  document.querySelectorAll('.tab').forEach(btn => {
    const on = !!(btn.dataset && btn.dataset.tab === name);
    btn.classList.toggle('active', on);
    if (on) {
      if (btn.setAttribute) btn.setAttribute('aria-current', 'page');
    } else if (btn.removeAttribute) {
      btn.removeAttribute('aria-current');
    }
  });
  const panels = document.querySelectorAll('.panel');
  if (panels && panels.length) {
    panels.forEach(p => { if (p.classList) p.classList.add('hidden'); });
  } else if (leaving && leaving !== name) {
    const prev = $('panel-' + leaving);
    if (prev && prev.classList) prev.classList.add('hidden');
  }
  const panel = $('panel-' + name);
  if (panel && panel.classList) panel.classList.remove('hidden');
}

async function openTodayDigestReport(name) {
  const target = String(name || '');
  if (!DIGEST_JSON_NAME.test(target)) return;
  showTab('reports');
  try { localStorage.setItem('st.tab', 'reports'); } catch (e) { /* 存不了偏好时仍切页 */ }
  const tab = document.querySelector('.tab[data-tab="reports"]');
  if (tab && typeof tab.click === 'function') {
    suppressTabRefresh = true;
    try { tab.click(); } finally { suppressTabRefresh = false; }
  }
  await refresh();
  await openJsonReport(target);
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    showTab(btn.dataset.tab);
    if (suppressTabRefresh) return;
    refresh();
  });
});
$('today-digest-open').addEventListener('click', () => {
  const btn = $('today-digest-open');
  if (!btn || btn.disabled) return;
  openTodayDigestReport((btn.dataset && btn.dataset.name) || '');
});
$('refresh').addEventListener('click', () => {
  if (window.ST && window.ST.forceRefresh) window.ST.forceRefresh();
  else refresh();
});
$('quote-btn').addEventListener('click', () => refreshSafe(loadQuotes));
$('kline-btn').addEventListener('click', () => refreshSafe(loadKline));
$('codes').addEventListener('keydown', e => { if (e.key === 'Enter') refreshSafe(loadQuotes); });
$('kline-code').addEventListener('keydown', e => { if (e.key === 'Enter') refreshSafe(loadKline); });

document.addEventListener('click', e => {
  const row = eventEl(e.target);
  const digestRow = row && row.closest && row.closest('tr.digest-evidence-row');
  if (!digestRow) return;
  activateDigestEvidenceRow(digestRow);
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const row = eventEl(e.target);
  const digestRow = row && row.closest && row.closest('tr.digest-evidence-row');
  if (!digestRow) return;
  if (e.preventDefault) e.preventDefault();
  activateDigestEvidenceRow(digestRow);
});

async function refreshSafe(fn) {
  clearError();
  try { setStatus(true); await fn(); }
  catch (e) { showError(String(e.message || e)); }
}

/* 等 ux.js / p1.js / p2.js 都注册完再跑首次加载，
   这样增强层（超时、缓存、骨架、表格工具条）对首屏同样生效。 */
document.addEventListener('DOMContentLoaded', () => window.refresh());
