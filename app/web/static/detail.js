/* 个股详情抽屉式子页面

   只读视图：一次 GET /api/stock/detail 聚合实时报价、60 日走势、轻量技术指标、
   本股自选/持仓/预警/最近交易；公司资料按需单独加载。
   入口：表格代码列、代码输入框「详情」按钮、命令面板、URL #stock=xxx。
   最后加载；通过 window.ST.openStockDetail 暴露给 ux.js。 */

(() => {
  const ST = window.ST;
  const $ = ST.$, api = ST.api, esc = ST.esc, fmt = ST.fmt;
  const signed = ST.signed, cls = ST.cls, card = ST.card;
  let currentCode = '';
  let currentData = null;

  const num = (v, digits = 2) => (v === null || v === undefined ? '-' : fmt(v, digits));

  function kv(pairs) {
    const rows = pairs.filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `<div><span>${esc(k)}</span><span>${v}</span></div>`).join('');
    return `<div class="detail-kv">${rows || '<div class="dim">暂无数据</div>'}</div>`;
  }

  function cap(v) {
    if (v === null || v === undefined || !Number.isFinite(Number(v))) return '-';
    const n = Number(v), abs = Math.abs(n);
    if (abs >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
    if (abs >= 1e4) return (n / 1e4).toFixed(2) + ' 万';
    return fmt(n, 0);
  }

  /* quote 的字段自带单位：成交额=万元、市值=亿元、量=手。
     原值 + 单位后缀展示，避免二次换算把量级写错。 */
  function unit(v, suffix, digits = 2) {
    if (v === null || v === undefined || !Number.isFinite(Number(v))) return '-';
    return fmt(v, digits) + ' ' + suffix;
  }

  function pctCell(v) {
    return (v === null || v === undefined || !Number.isFinite(v)) ? null
      : `<span class="${cls(v)}">${signed(v)}%</span>`;
  }

  function changeN(rows, n) {
    const closes = rows.map(r => r.close)
      .filter(v => v !== null && v !== undefined).map(Number);
    if (closes.length <= n || !closes[closes.length - 1 - n]) return null;
    return (closes[closes.length - 1] / closes[closes.length - 1 - n] - 1) * 100;
  }

  function orderBook(q) {
    const rows = [];
    for (let i = 5; i >= 1; i--) rows.push(['卖' + i, q['ask' + i], q['ask' + i + '_vol'], 'ask']);
    for (let i = 1; i <= 5; i++) rows.push(['买' + i, q['bid' + i], q['bid' + i + '_vol'], 'bid']);
    if (!rows.some(r => Number(r[1]) > 0)) return '';
    const maxVol = Math.max(1, ...rows.map(r => Number(r[2]) || 0));
    return `<table class="detail-table book-table"><tbody>${rows.map(([label, price, vol, side]) => {
      const w = Math.min(100, (Number(vol) || 0) / maxVol * 100).toFixed(0);
      return `<tr><td class="dim">${label}</td>
        <td class="num ${side === 'ask' ? 'down' : 'up'}">${num(price)}</td>
        <td class="num">${unit(vol, '手', 0)}</td>
        <td class="book-cell"><div class="book-bar ${side}" style="width:${w}%"></div></td></tr>`;
    }).join('')}</tbody></table>`;
  }

  function innerOuter(q) {
    const outer = Number(q.outer_volume) || 0, inner = Number(q.inner_volume) || 0;
    const total = outer + inner;
    if (!total) return '';
    const op = (outer / total * 100).toFixed(1);
    return `<h3>内外盘</h3><div class="io-bar">
        <div class="io-outer" style="width:${op}%"></div>
        <div class="io-inner" style="width:${(100 - Number(op)).toFixed(1)}%"></div>
      </div><div class="detail-kv">
        <div><span>外盘（主动买）</span><span class="up">${unit(outer, '手', 0)} · ${op}%</span></div>
        <div><span>内盘（主动卖）</span><span class="down">${unit(inner, '手', 0)} · ${(100 - Number(op)).toFixed(1)}%</span></div>
      </div>`;
  }

  /* 与 watch 着色一致：>=3 红、>=1.5 黄、>=0.8 绿，更低为灰。
     标签：>=1.5 放量，0.8–1.5 平量，<0.8 缩量；没有可用量比则只有「—」。
     优先 quote.volume_ratio，其次 vol_ratio，再次详情接口回退值。 */
  function positiveNum() {
    for (let i = 0; i < arguments.length; i++) {
      const n = Number(arguments[i]);
      if (Number.isFinite(n) && n > 0) return n;
    }
    return null;
  }

  function detailVolumeRatio(d) {
    const q = (d && d.quote) || {};
    const n = positiveNum(q.volume_ratio, q.vol_ratio, d && d.volume_ratio);
    if (n == null) return { text: '—', label: '', cls: 'dim', value: null };
    let color = 'dim';
    let label = '缩量';
    if (n >= 3) { color = 'up'; label = '放量'; }
    else if (n >= 1.5) { color = 'warn'; label = '放量'; }
    else if (n >= 0.8) { color = 'down'; label = '平量'; }
    return { text: fmt(n, 2), label, cls: color, value: n };
  }

  function volumeRatioCard(view) {
    const badge = view.label
      ? `<span class="tag vr-tag ${view.cls}">${esc(view.label)}</span>` : '';
    return `<div class="card vr-card"><div class="k">量比</div>
      <div class="v ${view.cls}">${esc(view.text)}${badge}</div></div>`;
  }

  function turnoverCard(q) {
    const hasRate = q.turnover_rate !== null && q.turnover_rate !== undefined
      && q.turnover_rate !== '';
    const v = hasRate ? q.turnover_rate : q.turnover;
    return `<div class="card turnover-card"><div class="k">换手</div>
      <div class="v">${num(v)}%</div></div>`;
  }

  /* 近 5 日量能只用详情里已有的 kline[].volume，不再请求新接口。 */
  function recentVolumeHtml(krows) {
    const rows = Array.isArray(krows) ? krows.slice(-5) : [];
    if (!rows.length) return '';
    const vols = rows.map(r => {
      const n = Number(r && r.volume);
      return Number.isFinite(n) ? n : 0;
    });
    const max = Math.max(1, ...vols);
    let steps = 0;
    let rising = null;
    for (let i = vols.length - 1; i > 0; i--) {
      if (vols[i] === vols[i - 1]) break;
      const up = vols[i] > vols[i - 1];
      if (rising === null) rising = up;
      else if (rising !== up) break;
      steps++;
    }
    let hint = `近 ${vols.length} 日量能`;
    if (steps >= 1) hint += rising ? ` · 连放 ${steps + 1} 日` : ` · 连缩 ${steps + 1} 日`;
    const bars = rows.map((r, i) => {
      const prev = i > 0 ? vols[i - 1] : null;
      const dir = prev === null || vols[i] === prev ? '' : (vols[i] > prev ? 'up' : 'down');
      const h = Math.max(4, Math.round(vols[i] / max * 100));
      const raw = String((r && r.date) || '');
      const label = raw.length >= 10 ? raw.slice(5, 10) : (raw || String(i + 1));
      return `<div class="vol-col" title="${esc(label + ' ' + cap(vols[i]))}">
        <div class="vol-track"><div class="vol-bar ${dir}" style="height:${h}%"></div></div>
        <span>${esc(label)}</span></div>`;
    }).join('');
    return `<h3>近 ${vols.length} 日量能</h3>
      <div class="vol-mini" aria-label="${esc(hint)}">${bars}</div>
      <div class="dim vol-hint">${esc(hint)}</div>`;
  }

  function overviewHtml(d) {
    const q = d.quote || {}, tech = d.tech || {}, s = d.stock || {}, h = d.holding;
    const price = q.price || 0;
    const chg = q.change_percent || 0;
    const amplitude = (q.prev_close && q.high && q.low)
      ? (Number(q.high) - Number(q.low)) / Number(q.prev_close) * 100 : null;
    const vrView = detailVolumeRatio(d);
    const cards = [
      card('现价', num(price), cls(chg)),
      card('涨跌额 / 幅', signed(q.change || 0) + ' / ' + signed(chg) + '%', cls(chg)),
      volumeRatioCard(vrView),
      card('昨收 / 今开', `${num(q.prev_close)} / ${num(q.open)}`, 'neutral'),
      card('最高 / 最低', `${num(q.high)} / ${num(q.low)}`, 'neutral'),
      card('振幅', amplitude === null ? '-' : num(amplitude) + '%', 'neutral'),
      card('成交额', unit(q.amount, '万元'), 'neutral'),
      card('成交量', unit(q.volume, '手', 0), 'neutral'),
      turnoverCard(q),
      card('PE / PB', `${num(q.pe_ratio)} / ${num(q.pb_ratio)}`, 'neutral'),
      card('总市值', unit(q.total_market_cap, '亿元'), 'neutral'),
      card('流通市值', unit(q.circulating_market_cap, '亿元'), 'neutral'),
    ].join('');

    const krows = d.kline || [];
    const vols = krows.map(r => Number(r.volume) || 0);
    const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : null;
    const lastVol = vols.length ? vols[vols.length - 1] : null;
    const volRatio = avgVol && lastVol ? lastVol / avgVol : null;

    const closes = (d.kline || []).map(r => r.close).filter(v => v !== null && v !== undefined);
    const chart = closes.length >= 2
      ? `<div class="detail-chart">${ST.sparkline(closes, d.code + ' 近 ' + closes.length + ' 日收盘')}</div>`
      : '<div class="result-box dim">暂无 K 线数据</div>';

    const tags = [
      s.is_watched ? '<span class="tag good">已收藏</span>' : '<span class="tag">未收藏</span>',
      h && !h.is_cleared
        ? '<span class="tag good">持仓中</span>'
        : (h ? '<span class="tag">已清仓</span>' : '<span class="tag">无持仓</span>'),
      `<span class="tag">预警 ${d.alert_count || 0} 条</span>`,
      h && h.manual_override ? '<span class="tag bad">手工锁定</span>' : '',
    ].filter(Boolean).join('');

    const holdingBlock = h ? kv([
      ['持仓数量', num(h.quantity, 0) + ' 股'],
      ['平均成本', num(h.avg_cost)],
      ['投入成本', num(h.total_cost)],
      ['已实现盈亏', `<span class="${cls(h.realized_profit)}">${signed(h.realized_profit)}</span>`],
    ]) : '<div class="result-box dim">本地没有这支股票的持仓记录</div>';

    const trades = d.recent_trades || [];
    const tradeTable = trades.length ? `<table class="detail-table">
      <thead><tr><th>时间</th><th>方向</th><th class="num">价格</th>
        <th class="num">数量</th><th class="num">盈亏</th></tr></thead><tbody>
      ${trades.map(t => `<tr><td>${esc(String(t.trade_time || '').slice(0, 16))}</td>
        <td>${t.action === 'buy' ? '<span class="up">买入</span>' : '<span class="down">卖出</span>'}</td>
        <td class="num">${num(t.price)}</td><td class="num">${num(t.quantity, 0)}</td>
        <td class="num ${cls(t.profit)}">${t.profit === null || t.profit === undefined ? '-' : signed(t.profit)}</td>
      </tr>`).join('')}</tbody></table>` : '<div class="result-box dim">暂无该股交易记录</div>';

    return `
      <h3>实时报价</h3><div class="cards">${cards}</div>
      ${kv([
        ['市场', esc(q.market_name || '')], ['代码', esc(q.symbol || '')],
        ['报价时间', esc(String(q.time || ''))],
        ['昨收', num(q.prev_close)],
        ['成交额', unit(q.amount, '万元')],
      ])}
      <h3>五档盘口</h3>${orderBook(q) || '<div class="dim">暂无盘口数据</div>'}
      ${innerOuter(q)}
      <h3>近 ${closes.length} 个交易日收盘走势</h3>${chart}
      ${recentVolumeHtml(krows)}
      <h3>技术指标（基于上述收盘价）</h3>${kv([
        ['MA5', num(tech.ma5, 3)], ['MA20', num(tech.ma20, 3)],
        ['5 日涨跌', pctCell(changeN(krows, 5))],
        ['20 日涨跌', pctCell(tech.change_20d)],
        ['60 日涨跌', pctCell(changeN(krows, 60))],
        ['20 日波动率', tech.volatility_20d === null || tech.volatility_20d === undefined
          ? null : num(tech.volatility_20d) + '%'],
        ['区间最高 / 最低', `${num(tech.high_60d)} / ${num(tech.low_60d)}`],
        ['区间位置', tech.range_position === null || tech.range_position === undefined
          ? null : num(tech.range_position, 1) + '%'],
        ['平均成交量', cap(avgVol)],
        ['最新量 / 均量', volRatio ? num(volRatio) + ' 倍' : null],
      ])}
      <h3>本股状态</h3><div class="detail-tags">${tags}</div>
      ${s.industry || s.sector || s.watch_note ? kv([
        ['市场', esc(s.market || '')], ['行业', esc(s.industry || '')],
        ['板块', esc(s.sector || '')], ['自选备注', esc(s.watch_note || '')],
      ]) : ''}
      ${holdingBlock}
      <h3>最近 5 笔交易</h3>${tradeTable}`;
  }

  /* ---------------- 内部 tab：概览 / 资金流 / 新闻 / 公司资料 ---------------- */
  let paneLoaded = {
    overview: true, kline: false, fund: false, news: false, profile: false,
  };
  let lastKlineRows = [];
  const PERIODS = [
    ['day', '日线'], ['week', '周线'], ['month', '月线'],
    ['m60', '60 分钟'], ['m30', '30 分钟'],
  ];

  function pane(name) {
    return $('detail-body').querySelector('.detail-pane[data-pane="' + name + '"]');
  }

  function render(d) {
    currentData = d;
    paneLoaded = {
      overview: true, kline: false, fund: false, news: false, profile: false,
    };
    lastKlineRows = [];
    $('detail-title').textContent = (d.name || d.code) + ' · ' + d.code;
    $('detail-sub').textContent = '更新于 '
      + String(d.generated_at || '').replace('T', ' ') + ' · 数据仅供参考';
    $('detail-body').innerHTML = `
      <div class="detail-tabs">
        <button type="button" class="detail-tab active" data-pane="overview">概览</button>
        <button type="button" class="detail-tab" data-pane="kline">K 线</button>
        <button type="button" class="detail-tab" data-pane="fund">资金流</button>
        <button type="button" class="detail-tab" data-pane="news">新闻</button>
        <button type="button" class="detail-tab" data-pane="profile">公司资料</button>
      </div>
      <div class="detail-pane" data-pane="overview">${overviewHtml(d)}</div>
      <div class="detail-pane hidden" data-pane="kline"></div>
      <div class="detail-pane hidden" data-pane="fund"></div>
      <div class="detail-pane hidden" data-pane="news"></div>
      <div class="detail-pane hidden" data-pane="profile"></div>`;
    $('detail-body').querySelectorAll('.detail-tab').forEach(btn =>
      btn.addEventListener('click', () => switchPane(btn.dataset.pane)));
  }

  function switchPane(name) {
    const body = $('detail-body');
    body.querySelectorAll('.detail-tab').forEach(b =>
      b.classList.toggle('active', b.dataset.pane === name));
    body.querySelectorAll('.detail-pane').forEach(p =>
      p.classList.toggle('hidden', p.dataset.pane !== name));
    if (paneLoaded[name]) return;
    const loader = paneLoaders[name];
    if (loader) loader();
  }

  function money(v) {
    if (v === null || v === undefined || !Number.isFinite(Number(v))) return '-';
    const n = Number(v), abs = Math.abs(n);
    if (abs >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
    if (abs >= 1e4) return (n / 1e4).toFixed(1) + ' 万';
    return n.toFixed(0);
  }

  function loading(name, text) {
    const el = pane(name);
    if (el) el.innerHTML = '<div class="detail-loading"><span class="spinner"></span> '
      + esc(text) + '…</div>';
  }

  async function loadFund() {
    loading('fund', '正在获取资金流向');
    try {
      const d = await api('/api/stock/fund?code=' + encodeURIComponent(currentCode) + '&days=10');
      const rows = d.rows || [];
      const el = pane('fund');
      if (!el) return;
      if (d.error) { el.innerHTML = '<div class="quality-warn">资金流获取失败：' + esc(d.error) + '</div>'; return; }
      if (!rows.length) { el.innerHTML = '<div class="result-box dim">暂无资金流向数据</div>'; return; }
      const total = rows.reduce((acc, r) => acc + (Number(r.main_net_in) || 0), 0);
      const max = Math.max(1, ...rows.map(r => Math.abs(Number(r.main_net_in) || 0)));
      el.innerHTML = `
        <h3>近 ${rows.length} 日主力净流入 · 合计 <span class="${cls(total)}">${money(total)}</span></h3>
        <table class="detail-table flow-table">
          <thead><tr><th>日期</th><th class="num">收盘价</th>
            <th>主力净流入</th><th class="num">散户/均价净流入</th></tr></thead>
          <tbody>${rows.map(r => {
            const v = Number(r.main_net_in) || 0;
            const w = Math.min(100, Math.abs(v) / max * 100).toFixed(0);
            return `<tr><td>${esc(r.date)}</td><td class="num">${num(r.price)}</td>
              <td><div class="flow-bar ${v >= 0 ? 'up' : 'down'}" style="width:${w}%"></div>
                <span class="${cls(v)}">${money(v)}</span></td>
              <td class="num ${cls(r.avg_in)}">${money(r.avg_in)}</td></tr>`;
          }).join('')}</tbody></table>
        <div class="dim">正值代表主力净流入；数据来自 stock-data，仅供参考。</div>`;
      paneLoaded.fund = true;
    } catch (e) {
      const el = pane('fund');
      if (el) el.innerHTML = '<div class="quality-warn">资金流加载失败：' + esc(String(e.message || e)) + '</div>';
    }
  }

  async function loadNews() {
    loading('news', '正在获取个股新闻');
    try {
      const d = await api('/api/stock/news?code=' + encodeURIComponent(currentCode) + '&size=15');
      const rows = d.rows || [];
      const el = pane('news');
      if (!el) return;
      if (d.error) { el.innerHTML = '<div class="quality-warn">新闻获取失败：' + esc(d.error) + '</div>'; return; }
      if (!rows.length) { el.innerHTML = '<div class="result-box dim">暂无相关新闻</div>'; return; }
      el.innerHTML = `<h3>最新 ${rows.length} 条${d.total ? ' · 共 ' + fmt(d.total, 0) + ' 条' : ''}</h3>
        <div class="news-list">${rows.map(n => `
          <a class="news-item" href="${esc(n.url || '#')}" target="_blank" rel="noopener noreferrer">
            <div class="news-title">${esc(n.title || '(无标题)')}</div>
            <div class="news-meta dim">${esc(n.time || '')}${n.source ? ' · ' + esc(n.source) : ''}</div>
            ${n.summary ? '<div class="news-summary dim">' + esc(n.summary) + '</div>' : ''}
          </a>`).join('')}</div>`;
      paneLoaded.news = true;
    } catch (e) {
      const el = pane('news');
      if (el) el.innerHTML = '<div class="quality-warn">新闻加载失败：' + esc(String(e.message || e)) + '</div>';
    }
  }

  /* ---------------- K 线蜡烛图 ---------------- */
  const UP_COLOR = '#e5484d', DOWN_COLOR = '#30a46c';

  function maSeries(closes, k) {
    return closes.map((_, i) => i < k - 1 ? null
      : closes.slice(i - k + 1, i + 1).reduce((a, b) => a + b, 0) / k);
  }

  function candleChart(rows) {
    const list = rows.filter(r => r && r.close !== null && r.close !== undefined);
    if (list.length < 2) return '<div class="dim">K 线数据不足</div>';

    const W = 860, H = 350, PAD = 12, PRICE_H = 240, VOL_TOP = 250, VOL_H = 82;
    const closes = list.map(r => Number(r.close));
    const highs = list.map(r => Number(r.high) || Number(r.close));
    const lows = list.map(r => Number(r.low) || Number(r.close));
    const max = Math.max(...highs), min = Math.min(...lows), span = (max - min) || 1;
    const n = list.length, cw = (W - 2 * PAD) / n;
    const y = v => PAD + (max - v) / span * (PRICE_H - 2 * PAD);
    const vols = list.map(r => Number(r.volume) || 0);
    const maxVol = Math.max(1, ...vols);

    function poly(series, color) {
      const pts = series.map((v, i) => v === null ? null
        : `${(PAD + cw * (i + 0.5)).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean);
      return pts.length > 1
        ? `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="1.2" opacity=".9"/>`
        : '';
    }

    let body = '';
    list.forEach((r, i) => {
      const o = Number(r.open) || Number(r.close), c = Number(r.close);
      const hi = highs[i], lo = lows[i], rising = c >= o;
      const color = rising ? UP_COLOR : DOWN_COLOR;
      const x = PAD + cw * (i + 0.5), bw = Math.max(1.5, cw * 0.62);
      const yo = y(o), yc = y(c);
      const top = Math.min(yo, yc), height = Math.max(1.2, Math.abs(yo - yc));
      const vh = vols[i] / maxVol * VOL_H;
      body += `<g class="candle" data-i="${i}">
        <line x1="${x}" y1="${y(hi)}" x2="${x}" y2="${y(lo)}" stroke="${color}" stroke-width="1"/>
        <rect x="${(x - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}"
          height="${height.toFixed(1)}" fill="${color}"/>
        <rect x="${(x - bw / 2).toFixed(1)}" y="${(VOL_TOP + VOL_H - vh).toFixed(1)}"
          width="${bw.toFixed(1)}" height="${vh.toFixed(1)}" fill="${color}" opacity=".55"/>
        <rect x="${(PAD + cw * i).toFixed(1)}" y="${PAD}" width="${cw.toFixed(1)}"
          height="${PRICE_H + VOL_H}" fill="transparent"/>
      </g>`;
    });

    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="candle-svg">
      <line x1="${PAD}" y1="${PAD}" x2="${W - PAD}" y2="${PAD}" stroke="var(--line)"/>
      <line x1="${PAD}" y1="${PRICE_H}" x2="${W - PAD}" y2="${PRICE_H}" stroke="var(--line)"/>
      <line x1="${PAD}" y1="${VOL_TOP + VOL_H}" x2="${W - PAD}" y2="${VOL_TOP + VOL_H}" stroke="var(--line)"/>
      ${body}
      ${poly(maSeries(closes, 5), '#f5a524')}
      ${poly(maSeries(closes, 10), '#5b9dff')}
      ${poly(maSeries(closes, 20), '#a78bfa')}
      <text x="${PAD}" y="${PAD + 12}" fill="#8b95a5" font-size="11">最高 ${fmt(max)}</text>
      <text x="${PAD}" y="${PRICE_H - 4}" fill="#8b95a5" font-size="11">最低 ${fmt(min)}</text>
    </svg>
    <div class="kline-legend">
      <span style="color:#f5a524">■ MA5</span><span style="color:#5b9dff">■ MA10</span>
      <span style="color:#a78bfa">■ MA20</span>
      <span class="dim">下方柱为成交量 · 红涨绿跌</span>
    </div>`;
  }

  function klineStats(rows) {
    const closes = rows.map(r => Number(r.close)).filter(Number.isFinite);
    const vols = rows.map(r => Number(r.volume) || 0);
    if (!closes.length) return '';
    const last = closes[closes.length - 1], first = closes[0];
    const hi = Math.max(...rows.map(r => Number(r.high) || Number(r.close)));
    const lo = Math.min(...rows.map(r => Number(r.low) || Number(r.close)));
    const ma = k => maSeries(closes, k)[closes.length - 1];
    const avgVol = vols.reduce((a, b) => a + b, 0) / (vols.length || 1);
    return kv([
      ['区间涨跌', pctCell(first ? (last / first - 1) * 100 : null)],
      ['区间最高 / 最低', `${num(hi)} / ${num(lo)}`],
      ['MA5 / MA10 / MA20', `${num(ma(5), 3)} / ${num(ma(10), 3)} / ${num(ma(20), 3)}`],
      ['平均成交量', cap(avgVol)],
      ['振幅', hi > lo ? num((hi - lo) / lo * 100) + '%' : null],
    ]);
  }

  function bindCandleHover() {
    const chart = $('kline-chart');
    const hover = $('kline-hover');
    if (!chart || !hover) return;
    chart.querySelectorAll('.candle').forEach(g => {
      g.addEventListener('mouseenter', () => {
        const i = Number(g.dataset.i);
        const r = lastKlineRows[i];
        if (!r) return;
        const prev = i > 0 ? Number(lastKlineRows[i - 1].close) : null;
        const chg = prev ? (Number(r.close) / prev - 1) * 100 : null;
        hover.innerHTML = `<strong>${esc(String(r.date || ''))}</strong>　开 ${num(r.open)}　高 ${num(r.high)}`
          + `　低 ${num(r.low)}　收 <span class="${cls(chg)}">${num(r.close)}</span>`
          + `　涨跌 ${chg === null ? '-' : `<span class="${cls(chg)}">${signed(chg)}%</span>`}`
          + `　量 ${cap(r.volume)}`;
      });
    });
  }

  async function fetchKline() {
    const period = $('kline-period').value;
    const count = $('kline-count').value;
    const adjust = $('kline-adjust').value;
    const chart = $('kline-chart');
    if (!chart) return;
    chart.innerHTML = '<div class="detail-loading"><span class="spinner"></span> 加载 K 线…</div>';
    $('kline-hint').textContent = '加载中…';
    try {
      const d = await api('/api/kline?code=' + encodeURIComponent(currentCode)
        + '&count=' + count + '&period=' + period + '&adjust=' + adjust);
      lastKlineRows = d.rows || [];
      chart.innerHTML = candleChart(lastKlineRows);
      $('kline-stats').innerHTML = klineStats(lastKlineRows);
      const label = (PERIODS.find(p => p[0] === period) || [period, period])[1];
      $('kline-hint').textContent = `${lastKlineRows.length} 根 · ${label}`
        + (adjust === 'qfq' ? ' · 前复权' : adjust === 'hfq' ? ' · 后复权' : ' · 不复权');
      bindCandleHover();
      paneLoaded.kline = true;
    } catch (e) {
      chart.innerHTML = '<div class="quality-warn">K 线加载失败：'
        + esc(String(e.message || e)) + '</div>';
      $('kline-hint').textContent = '';
    }
  }

  function loadKline() {
    const el = pane('kline');
    if (!el) return;
    el.innerHTML = `<div class="kline-tools">
      <select id="kline-period">${PERIODS.map(([v, label]) =>
        `<option value="${v}">${label}</option>`).join('')}</select>
      <select id="kline-count"><option value="60">60 根</option><option value="120">120 根</option></select>
      <select id="kline-adjust">
        <option value="qfq">前复权</option><option value="hfq">后复权</option>
        <option value="">不复权</option>
      </select>
      <span id="kline-hint" class="dim"></span>
    </div>
    <div id="kline-hover" class="kline-hover dim">悬停任意一根蜡烛查看当日开高低收与成交量</div>
    <div id="kline-chart" class="detail-chart"></div>
    <div id="kline-stats"></div>`;
    ['kline-period', 'kline-count', 'kline-adjust'].forEach(id =>
      $(id).addEventListener('change', fetchKline));
    fetchKline();
  }

  const paneLoaders = {
    kline: loadKline, fund: loadFund, news: loadNews, profile: () => loadProfile(),
  };

  async function open(code) {
    code = String(code || '').trim();
    if (!code) return;
    currentCode = code;
    currentData = null;
    $('stock-detail').classList.remove('hidden');
    $('detail-title').textContent = code;
    $('detail-sub').textContent = '加载中…';
    $('detail-body').innerHTML = '<div class="detail-loading"><span class="spinner"></span>'
      + ' 正在获取行情、走势与本股状态（首次加载 K 线可能需要几秒）…</div>';
    try {
      location.hash = 'stock=' + encodeURIComponent(code);
    } catch (e) { /* 某些宿主不允许改 hash */ }
    try {
      const d = await api('/api/stock/detail?code=' + encodeURIComponent(code));
      if (currentCode !== code) return;  // 期间又打开了别的股票
      render(d);
    } catch (e) {
      $('detail-body').innerHTML = '<div class="quality-warn">详情加载失败：'
        + esc(String(e.message || e)) + '</div>';
    }
  }

  function close() {
    $('stock-detail').classList.add('hidden');
    currentCode = '';
    try {
      if (location.hash.indexOf('#stock=') === 0) {
        history.replaceState(null, '', location.pathname);
      }
    } catch (e) { /* ignore */ }
  }

  function section(title, pairs) {
    const rows = pairs.filter(([, v]) => v !== null && v !== undefined && String(v).trim())
      .map(([k, v]) => `<div><span>${esc(k)}</span><span>${esc(String(v))}</span></div>`)
      .join('');
    return rows ? `<h3>${esc(title)}</h3><div class="detail-kv">${rows}</div>` : '';
  }

  function renderProfile(p) {
    /* stock-data 返回的是拼音缩写嵌套结构，这里挑有信息价值的字段翻译 */
    const gs = p.gsjj || {};
    const zy = (p.zyzb && p.zyzb.detail) || {};
    const gb = p.gdgb || {};
    let html = '';

    html += section('公司简介', [
      ['公司名称', gs.gsmz], ['主营业务', gs.yw], ['地域', gs.dy],
      ['发行价', gs.jg], ['上市日期', gs.riqi],
    ]);
    html += section('最新主要指标' + (p.zyzb && p.zyzb.date ? ' · ' + p.zyzb.date : ''), [
      ['每股收益', zy.mgsy], ['净利润', zy.jlr], ['净利润增长', zy.jlrzzl],
      ['营业收入', zy.yyzsr], ['营收增长', zy.zsrzzl],
      ['每股净资产', zy.mgjzc], ['净资产收益率', zy.jzcsyl],
      ['资产负债率', zy.zcfzl],
    ]);
    html += section('股本与股东', [
      ['总股本', gb.zgb], ['流通股本', gb.ltgb],
      ['股东人数', gb.gdrs], ['人均持股', gb.rjcg],
    ]);

    const plates = (gs.plate || []).map(x => x && x.name).filter(Boolean);
    const concepts = (gs.concept || []).map(x => x && x.name).filter(Boolean).slice(0, 10);
    if (plates.length || concepts.length) {
      html += '<h3>所属板块 / 概念</h3><div class="detail-tags">'
        + plates.concat(concepts).map(x => `<span class="tag">${esc(x)}</span>`).join('')
        + '</div>';
    }

    const sr = Array.isArray(p.zysr) ? p.zysr[0] : null;
    if (sr && Array.isArray(sr.detail)) {
      const items = [];
      sr.detail.forEach(d => {
        if (Array.isArray(d.detail)) d.detail.forEach(x => items.push(x));
      });
      html += section('主营构成' + (sr.date ? ' · ' + sr.date : ''),
        items.slice(0, 6).map(x => [x.name, `${x.income || ''} ${x.zb ? '(' + x.zb + '%)' : ''}`]));
    }

    /* 兼容扁平英文字段（未来数据源或测试桩） */
    const generic = Object.keys(p)
      .filter(k => !['gsjj', 'zyzb', 'gdgb', 'zysr', 'ggzjc', 'ggjj', 'error', 'raw_output'].includes(k))
      .filter(k => typeof p[k] === 'string' || typeof p[k] === 'number')
      .map(k => [k, p[k]]);
    if (generic.length) html += section('其他资料', generic.slice(0, 12));

    return html || '<div class="dim">暂无可展示的公司资料</div>';
  }

  async function loadProfile() {
    if (!currentCode) return;
    const box = pane('profile');
    if (!box) return;
    box.innerHTML = '<div class="detail-loading"><span class="spinner"></span> 正在加载公司资料…</div>';
    try {
      const d = await api('/api/stock/profile?code=' + encodeURIComponent(currentCode));
      const p = d.profile || {};
      if (p.error) { box.innerHTML = '<div class="quality-warn">公司资料获取失败：' + esc(p.error) + '</div>'; return; }
      box.innerHTML = renderProfile(p);
      paneLoaded.profile = true;
    } catch (e) {
      box.innerHTML = '<div class="quality-warn">公司资料加载失败：'
        + esc(String(e.message || e)) + '</div>';
    }
  }

  function goto(tab, inputIds) {
    const code = currentCode;
    if (!code) return;
    inputIds.forEach(id => { const el = $(id); if (el) el.value = code; });
    close();
    ST.goTab(tab);
  }

  ST.openStockDetail = open;
  ST.closeStockDetail = close;
  ST.currentStockDetail = () => currentData;
  ST.detailVolumeRatio = detailVolumeRatio;
  ST.detailOverviewHtml = overviewHtml;
  ST.recentVolumeHtml = recentVolumeHtml;

  $('detail-close').addEventListener('click', close);
  $('stock-detail').addEventListener('click', e => {
    if (e.target.id === 'stock-detail') close();
  });
  $('detail-refresh').addEventListener('click', () => open(currentCode));
  $('detail-profile').addEventListener('click', () => switchPane('profile'));
  $('detail-goto-market').addEventListener('click', () => goto('market', ['codes', 'kline-code']));
  $('detail-goto-predict').addEventListener('click', () => goto('predict', ['predict-code']));
  $('detail-goto-write').addEventListener('click', () => goto('write', ['w-code']));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('stock-detail').classList.contains('hidden')) close();
  });

  try {
    const hash = location.hash || '';
    if (hash.indexOf('#stock=') === 0) open(decodeURIComponent(hash.slice(7)));
  } catch (e) { /* ignore */ }
})();
