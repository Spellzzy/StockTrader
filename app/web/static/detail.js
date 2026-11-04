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

  function render(d) {
    currentData = d;
    const q = d.quote || {}, tech = d.tech || {}, s = d.stock || {}, h = d.holding;
    $('detail-title').textContent = (d.name || d.code) + ' · ' + d.code;
    $('detail-sub').textContent = '更新于 '
      + String(d.generated_at || '').replace('T', ' ') + ' · 数据仅供参考';

    const price = q.price || 0;
    const chg = q.change_percent || 0;
    const cards = [
      card('现价', num(price), cls(chg)),
      card('涨跌额', signed(q.change || 0), cls(q.change || 0)),
      card('涨跌幅', signed(chg) + '%', cls(chg)),
      card('今开 / 最高 / 最低', `${num(q.open)} / ${num(q.high)} / ${num(q.low)}`, 'neutral'),
      card('成交量', num(q.volume, 0), 'neutral'),
      card('换手率 / PE', `${num(q.turnover)} / ${num(q.pe_ratio)}`, 'neutral'),
    ].join('');

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

    $('detail-body').innerHTML = `
      <h3>实时报价</h3><div class="cards">${cards}</div>
      <h3>近 ${closes.length} 个交易日收盘走势</h3>${chart}
      <h3>技术指标（基于上述收盘价）</h3>${kv([
        ['MA5', num(tech.ma5, 3)], ['MA20', num(tech.ma20, 3)],
        ['20 日涨跌', tech.change_20d === null || tech.change_20d === undefined ? null
          : `<span class="${cls(tech.change_20d)}">${signed(tech.change_20d)}%</span>`],
        ['20 日波动率', tech.volatility_20d === null || tech.volatility_20d === undefined
          ? null : num(tech.volatility_20d) + '%'],
        ['区间最高 / 最低', `${num(tech.high_60d)} / ${num(tech.low_60d)}`],
        ['区间位置', tech.range_position === null || tech.range_position === undefined
          ? null : num(tech.range_position, 1) + '%'],
      ])}
      <h3>本股状态</h3><div class="detail-tags">${tags}</div>
      ${s.industry || s.sector || s.watch_note ? kv([
        ['市场', esc(s.market || '')], ['行业', esc(s.industry || '')],
        ['板块', esc(s.sector || '')], ['自选备注', esc(s.watch_note || '')],
      ]) : ''}
      ${holdingBlock}
      <h3>最近 5 笔交易</h3>${tradeTable}
      <h3>公司资料</h3><div id="detail-profile-box" class="dim">点底部「公司资料」按需加载</div>`;
  }

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
    const box = $('detail-profile-box');
    if (!box) return;
    box.innerHTML = '<span class="spinner"></span> 正在加载公司资料…';
    try {
      const d = await api('/api/stock/profile?code=' + encodeURIComponent(currentCode));
      const p = d.profile || {};
      if (p.error) { box.textContent = '公司资料获取失败：' + p.error; return; }
      box.className = '';
      box.innerHTML = renderProfile(p);
    } catch (e) {
      box.textContent = '公司资料加载失败：' + String(e.message || e);
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

  $('detail-close').addEventListener('click', close);
  $('stock-detail').addEventListener('click', e => {
    if (e.target.id === 'stock-detail') close();
  });
  $('detail-refresh').addEventListener('click', () => open(currentCode));
  $('detail-profile').addEventListener('click', loadProfile);
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
