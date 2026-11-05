/* P1 页面：统计 / 回测 / 策略实验室 / AI 预测 / 交易持仓
   依赖 app.js 暴露的 window.ST 公共能力，无框架、无构建。

   注意：三个脚本都是经典 script，共享全局词法环境；顶层 const 重名会抛
   "Identifier has already been declared"，所以每个文件都包在 IIFE 里。 */

(() => {
const ST = window.ST;
const { $, api, post, fmt, signed, cls, esc, card, sparkline,
        showError, clearError, register, finite, tableRows } = ST;

function busy(el, text, fn) {
  const original = el.textContent;
  el.disabled = true; el.textContent = text;
  return Promise.resolve().then(fn).catch(e => {
    showError(String(e.message || e));
  }).finally(() => { el.disabled = false; el.textContent = original; });
}

/* ---------------- 策略下拉 ---------------- */
let strategyCache = null;
async function fillStrategies() {
  if (!strategyCache) strategyCache = (await api('/api/strategies')).items || [];
  const options = strategyCache.map(s =>
    `<option value="${esc(s.name)}">${esc(s.name)} — ${esc(s.description)}</option>`).join('');
  ['bt-strategy', 'lab-strategy'].forEach(id => {
    const el = $(id);
    if (!el.dataset.filled) { el.innerHTML = options; el.dataset.filled = '1'; }
  });
}

/* ---------------- 统计 ---------------- */
async function loadAnalysis() {
  const [s, m, r, d] = await Promise.all([
    api('/api/analysis/summary'),
    api('/api/analysis/monthly'),
    api('/api/analysis/ranking'),
    api('/api/analysis/drawdown'),
  ]);
  $('#analysis-cards').innerHTML = [
    card('总交易笔数', finite(s.total_trades, 0)),
    card('胜率', finite(s.win_rate, 1) + '%'),
    card('盈亏比', finite(s.profit_loss_ratio, 2)),
    card('最大回撤', finite(d.max_drawdown_rate, 1) + '%', 'down'),
  ].join('');

  tableRows($('#monthly'), (m.rows || []).map(x =>
    `<tr><td>${esc(x.month)}</td><td class="num">${finite(x.trade_count, 0)}</td>
     <td class="num ${cls(x.total_profit)}">${signed(x.total_profit)}</td>
     <td class="num">${finite(x.win_rate, 1)}%</td></tr>`).join(''), 4, '暂无卖出记录');

  tableRows($('#ranking'), (r.rows || []).map(x =>
    `<tr><td>${esc(x.stock_code || x.code || '')}</td>
     <td class="num">${finite(x.trades ?? x.trade_count, 0)}</td>
     <td class="num ${cls(x.profit)}">${signed(x.profit)}</td>
     <td class="num">${finite(x.win_rate, 1)}%</td></tr>`).join(''), 4, '暂无排名数据');
}

/* ---------------- 回测 ---------------- */
async function loadBacktest() { await fillStrategies(); }

function btPayload() {
  return {
    code: $('#bt-code').value.trim(),
    strategy: $('#bt-strategy').value,
    days: Number($('#bt-days').value) || 180,
    initial_capital: Number($('#bt-capital').value) || 100000,
    fill_mode: $('#bt-fill').value,
  };
}

async function runBacktest() {
  const btn = $('#bt-run');
  await busy(btn, '回测中…', async () => {
    clearError();
    const d = await post('/api/backtest/run', btPayload());
    const curve = d.equity_curve || [];
    const trades = d.trades || [];
    $('#bt-result').innerHTML = `
      <div class="cards">
        ${card('总收益', signed(d.total_return) + '%', cls(d.total_return))}
        ${card('净利润', signed(d.net_profit) + ' 元', cls(d.net_profit))}
        ${card('最大回撤', finite(d.max_drawdown, 1) + '%', 'down')}
        ${card('夏普', finite(d.sharpe_ratio, 2))}
        ${card('胜率', finite(d.win_rate, 1) + '%')}
        ${card('交易笔数', finite(d.total_trades, 0))}
      </div>
      ${d.total_trades === 0 ? '<div class="quality-warn">⚠️ 本次回测无成交：可能是资金买不起 1 手，或该区间策略没有信号</div>' : ''}
      <div class="result-box"><h3>权益曲线 · ${esc(d.code)} / ${esc(d.strategy_name)}</h3>
        <div class="chart">${sparkline(curve.map(x => x.equity), '权益')}</div></div>
      <div class="result-box"><h3>交易明细</h3><div class="table-wrap"><table>
        <thead><tr><th>买入日</th><th class="num">买入价</th><th>卖出日</th>
          <th class="num">卖出价</th><th class="num">数量</th><th class="num">收益%</th></tr></thead>
        <tbody>${trades.length ? trades.map(t => `<tr>
          <td>${esc(t.entry_date)}</td><td class="num">${finite(t.entry_price)}</td>
          <td>${esc(t.exit_date || '')}</td><td class="num">${finite(t.exit_price)}</td>
          <td class="num">${finite(t.quantity, 0)}</td>
          <td class="num ${cls(t.profit_rate)}">${signed(t.profit_rate)}%</td></tr>`).join('')
          : '<tr><td class="empty" colspan="6">无成交记录</td></tr>'}</tbody></table></div></div>`;
  });
}

async function compareBacktest() {
  const btn = $('#bt-compare-btn');
  await busy(btn, '对比中…', async () => {
    clearError();
    const p = btPayload();
    const d = await post('/api/backtest/compare', {
      code: p.code, days: p.days, initial_capital: p.initial_capital,
    });
    tableRows($('#bt-compare'), (d.rows || []).map(x => `<tr>
      <td>${esc(x.strategy_name)}</td>
      <td class="num ${cls(x.total_return)}">${signed(x.total_return)}%</td>
      <td class="num">${finite(x.max_drawdown, 1)}%</td>
      <td class="num">${finite(x.sharpe_ratio, 2)}</td>
      <td class="num">${finite(x.win_rate, 1)}%</td>
      <td class="num">${finite(x.total_trades, 0)}</td></tr>`).join(''), 6, '无可用结果');
  });
}

/* ---------------- 策略实验室 ---------------- */
async function loadLab() { await fillStrategies(); }

async function loadSignals() {
  const btn = $('#lab-signals-btn');
  await busy(btn, '评估中…', async () => {
    clearError();
    const code = $('#lab-code').value.trim();
    const d = await api('/api/lab/signals?code=' + encodeURIComponent(code));
    tableRows($('#lab-signals'), (d.rows || []).map(x => {
      const hit = x.hit_rate || 0, decay = x.decay || 0;
      return `<tr><td>${esc(x.strategy)}</td>
        <td class="num">${finite(x.total_signals, 0)}</td>
        <td class="num ${hit >= 55 ? 'up' : hit < 45 ? 'down' : ''}">${finite(hit, 1)}%</td>
        <td class="num">${finite(x.in_sample_hit_rate, 1)}%</td>
        <td class="num">${finite(x.out_of_sample_hit_rate, 1)}%</td>
        <td class="num ${decay > 15 ? 'down' : ''}">${signed(decay, 1)}</td>
        <td class="num">${finite(x.win_rate, 1)}%</td></tr>`;
    }).join(''), 7, '无可用信号');
  });
}

async function runOptimize() {
  const btn = $('#lab-optimize-btn');
  await busy(btn, '寻优中…', async () => {
    clearError();
    const d = await post('/api/lab/optimize', {
      code: $('#lab-code').value.trim(),
      strategy: $('#lab-strategy').value,
      max_combos: Number($('#lab-combos').value) || 8,
      folds: Number($('#lab-folds').value) || 3,
    });
    const grid = d.grid || {}, wf = d.walk_forward || {};
    $('#lab-optimize-result').innerHTML = `
      <div class="result-box"><h3>参数网格 · ${esc(grid.strategy || '')}（${finite(grid.combos, 0)} 组）</h3>
        <div class="table-wrap"><table><thead><tr><th>参数</th><th class="num">总收益</th>
          <th class="num">最大回撤</th><th class="num">夏普</th><th class="num">交易</th></tr></thead>
          <tbody>${(grid.rows || []).slice(0, 8).map(x => `<tr>
            <td>${esc(Object.entries(x.params || {}).map(([k, v]) => k + '=' + v).join(', ') || '默认')}</td>
            <td class="num ${cls(x.total_return)}">${signed(x.total_return)}%</td>
            <td class="num">${finite(x.max_drawdown, 1)}%</td>
            <td class="num">${finite(x.sharpe_ratio, 2)}</td>
            <td class="num">${finite(x.total_trades, 0)}</td></tr>`).join('')}</tbody></table></div></div>
      <div class="result-box"><h3>Rolling Walk-Forward</h3>
        ${wf.conclusion ? `<div class="quality-warn">${esc(wf.conclusion)}（有效折数 ${finite(wf.reliable_folds, 0)}/${finite(wf.total_folds, 0)}）</div>` : ''}
        <div class="table-wrap"><table><thead><tr><th>折</th><th class="num">训练命中率</th>
          <th class="num">样本外命中率</th><th>本折最优参数</th><th>可靠性</th></tr></thead>
          <tbody>${(wf.folds || []).map(f => `<tr><td>${finite(f.fold, 0)}</td>
            <td class="num">${finite(f.train_hit_rate, 1)}%</td>
            <td class="num">${finite(f.test_hit_rate, 1)}%</td>
            <td>${esc(Object.entries(f.best_params || {}).map(([k, v]) => k + '=' + v).join(', ') || '默认')}</td>
            <td>${f.reliable ? '<span class="tag good">可用</span>' : '<span class="tag bad">样本不足</span>'}</td></tr>`).join('')}</tbody></table></div></div>`;
  });
}

/* ---------------- AI 预测 ---------------- */
let pickerLoaded = false;
async function loadCodePicker() {
  const sel = $('#predict-picker');
  if (pickerLoaded) return;
  try {
    const d = await api('/api/code-picker');
    const watched = d.watchlist || [], held = d.holdings || [];
    const group = (label, rows) => rows.length
      ? `<optgroup label="${label} (${rows.length})">` + rows.map(x =>
          `<option value="${esc(x.code)}">${esc(x.code)} ${esc(x.name || '')}</option>`
        ).join('') + '</optgroup>'
      : '';
    sel.innerHTML = '<option value="">快捷选择…</option>'
      + group('我的自选', watched) + group('当前持仓', held);
    $('#predict-hint').textContent = (watched.length + held.length)
      ? '可从下拉挑选已收藏 / 持仓，选完点「开始预测」'
      : '暂无自选或持仓，可直接输入代码';
    pickerLoaded = true;
  } catch (e) {
    sel.innerHTML = '<option value="">快捷选择（加载失败）</option>';
  }
}

let modelStatus = null;
let trainTaskId = null;
let trainPollTimer = null;

function predictCode() { return $('#predict-code').value.trim(); }

function trainClientId() {
  return (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : 'train-' + Date.now() + '-' + Math.random().toString(36).slice(2);
}

async function checkModelStatus() {
  const code = predictCode();
  if (!code) return;
  try {
    const s = await api('/api/predict/model-status?code=' + encodeURIComponent(code));
    modelStatus = s;
    $('#predict-hint').textContent = s.ready
      ? '模型就绪 · 可点「开始预测」'
      : (s.can_train ? '尚无预测模型 · 可点「准备模型」' : '指数不参与模型训练');
    if (!s.ready) renderModelMissing(s.code, s);
  } catch (e) {
    // 预检查失败不阻断预测
  }
}

function renderModelMissing(code, status) {
  const canTrain = !status || status.can_train !== false;
  const training = status && status.training;
  $('#predict-result').innerHTML = `
    <div class="result-box model-missing">
      <h3>⚠️ ${esc(code)} 还没有预测模型</h3>
      <div class="dim">预测前需要先训练该股票的 XGBoost / RandomForest 模型。
        训练在后台执行，首次要拉取历史行情，可能需要几分钟；完成后会自动重新预测。</div>
      ${canTrain ? `<div class="toolbar">
        <button id="predict-train-btn" class="btn primary">准备模型</button>
        <span id="predict-train-hint" class="dim"></span>
      </div>` : '<div class="quality-warn">指数不参与模型训练，请改用个股代码。</div>'}
      <div id="predict-train-progress" class="detail-loading hidden">
        <span class="spinner"></span><span id="predict-train-msg"></span>
      </div>
      <div class="dim">也可以命令行执行：<code>stock-ai train-ai ${esc(code)}</code></div>
    </div>`;
  const btn = $('#predict-train-btn');
  if (btn) btn.addEventListener('click', () => startTraining(code));
  if (training && status.task_id) beginTraining(status.task_id);
}

function stopTraining() {
  if (trainPollTimer) clearInterval(trainPollTimer);
  trainPollTimer = null;
  trainTaskId = null;
}

function beginTraining(taskId) {
  trainTaskId = taskId;
  const box = $('#predict-train-progress');
  if (box) box.classList.remove('hidden');
  const btn = $('#predict-train-btn');
  if (btn) btn.disabled = true;
  const msg = $('#predict-train-msg');
  if (msg) msg.textContent = '训练任务已启动…';
  stopTrainingPoll();
  trainPollTimer = setInterval(pollTraining, 1500);
  pollTraining();
}

function stopTrainingPoll() {
  if (trainPollTimer) clearInterval(trainPollTimer);
  trainPollTimer = null;
}

async function pollTraining() {
  if (!trainTaskId) return;
  try {
    const d = await api('/api/predict/train/status?task_id=' + encodeURIComponent(trainTaskId));
    const t = d.task;
    if (!t) return;
    const msg = $('#predict-train-msg');
    if (msg) msg.textContent = t.message || '训练中…';
    if (t.status === 'done') {
      stopTraining();
      window.ST.toast('模型训练完成，正在重新预测', 'ok');
      await runPredict();
    } else if (t.status === 'failed') {
      stopTraining();
      showError('模型训练失败：' + (t.error || t.message || '未知错误'));
      const btn = $('#predict-train-btn');
      if (btn) { btn.disabled = false; btn.textContent = '重试准备模型'; }
    }
  } catch (e) {
    // 单次轮询失败等下一次
  }
}

async function startTraining(code) {
  if (!window.confirm(
    `确定训练 ${code} 的预测模型吗？\n训练会读取历史行情并写入模型文件，首次可能需要几分钟。`
  )) return;
  const btn = $('#predict-train-btn');
  if (btn) { btn.disabled = true; btn.textContent = '提交中…'; }
  try {
    const d = await post('/api/predict/train', {
      confirm: true, client_id: trainClientId(), code, use_dl: false,
    });
    const payload = d.result || {};
    if (!payload.task_id) throw new Error('未返回任务 ID');
    if (payload.already_running) {
      window.ST.toast(`已有训练任务在运行（${payload.running_code || ''}）`, 'info');
    }
    beginTraining(payload.task_id);
  } catch (e) {
    showError(String(e.message || e));
    if (btn) { btn.disabled = false; btn.textContent = '准备模型'; }
  }
}

async function loadPredict() {
  const el = $('#predict-result');
  if (!el.innerHTML) el.innerHTML = '<div class="result-box dim">输入股票代码后点击「开始预测」。预测不会自动训练模型；缺模型时可点「准备模型」。</div>';
  await loadCodePicker();
  await checkModelStatus();
}

async function runPredict() {
  const btn = $('#predict-btn');
  await busy(btn, '预测中…', async () => {
    clearError();
    const code = predictCode();
    const d = await api('/api/predict?code=' + encodeURIComponent(code));
    if (d.error) { renderModelMissing(code, modelStatus); return; }
    const c = d.combined || {};
    const q = c.quality || {};
    const stars = '⭐'.repeat(c.stars || 0) + '☆'.repeat(5 - (c.stars || 0));
    const models = [];
    [['ml_xgb', 'XGBoost'], ['ml_rf', 'RandomForest'], ['dl', 'LSTM']].forEach(([key, label]) => {
      const m = d[key];
      if (m) {
        const acc = m.model_accuracy || 0;
        models.push(`<tr><td>${label}</td><td>${esc(m.signal)}</td>
          <td class="num">${finite(m.confidence, 1)}%</td>
          <td class="num">${finite(acc * 100, 1)}%
            ${acc && acc < (q.baseline || 0.3333) ? '<span class="tag bad">低于基线</span>' : ''}</td></tr>`);
      }
    });
    const factors = (c.key_factors || []).map(x => `<span class="tag">${esc(x)}</span>`).join('');
    const ind = ((d.ml_xgb || {}).indicators) || {};
    const snapshot = Object.entries(ind).slice(0, 12)
      .map(([k, v]) => `<span class="tag">${esc(k)}=${finite(v)}</span>`).join('');

    $('#predict-result').innerHTML = `
      ${q.below_baseline ? `<div class="quality-warn">⚠️ 模型无预测能力：${esc(q.note || '')} 已自动降权并限制为最多 2 星，请勿据此下单</div>` : ''}
      <div class="cards">
        ${card('综合信号', esc(c.signal || '-') + ' ' + stars, cls(c.score))}
        ${card('综合评分', signed(c.score, 1), cls(c.score))}
        ${card('置信度', finite(c.confidence, 1) + '%')}
        ${card('模型平均准确率', q.mean_accuracy ? finite(q.mean_accuracy * 100, 1) + '%' : '-')}
      </div>
      <div class="result-box"><h3>模型明细</h3><div class="table-wrap"><table>
        <thead><tr><th>模型</th><th>信号</th><th class="num">置信度</th><th class="num">准确率</th></tr></thead>
        <tbody>${models.join('') || '<tr><td class="empty" colspan="4">无模型输出</td></tr>'}</tbody></table></div></div>
      ${factors ? `<div class="result-box"><h3>关键因子</h3>${factors}</div>` : ''}
      ${snapshot ? `<div class="result-box"><h3>技术指标快照</h3>${snapshot}</div>` : ''}`;
  });
}

/* ---------------- 交易持仓 ---------------- */
async function loadTrades() {
  const [p, t] = await Promise.all([api('/api/portfolio'), api('/api/trades?limit=30')]);
  const holdings = p.holdings || [];
  tableRows($('#trades-holdings'), holdings.map(h => `<tr>
    <td>${esc(h.stock_code)}</td><td>${esc(h.stock_name || '')}</td>
    <td class="num">${finite(h.quantity, 0)}</td><td class="num">${finite(h.avg_cost)}</td>
    <td class="num">${finite(h.current_price)}</td>
    <td class="num ${cls(h.unrealized_profit)}">${signed(h.unrealized_profit)}</td></tr>`).join(''), 6, '当前无持仓');

  tableRows($('#trades-list'), (t.rows || []).map(x => `<tr>
    <td>${esc(String(x.trade_time || '').slice(0, 16))}</td>
    <td>${esc(x.stock_code)}</td>
    <td>${x.action === 'buy' ? '<span class="up">买入</span>' : '<span class="down">卖出</span>'}</td>
    <td class="num">${finite(x.price)}</td><td class="num">${finite(x.quantity, 0)}</td>
    <td class="num ${cls(x.profit)}">${x.profit === null || x.profit === undefined ? '-' : signed(x.profit)}</td>
    <td>${esc(x.strategy || '')}</td></tr>`).join(''), 7, '暂无交易记录');
}

/* ---------------- 注册与事件 ---------------- */
register('analysis', loadAnalysis);
register('backtest', loadBacktest);
register('lab', loadLab);
register('predict', loadPredict);
register('trades', loadTrades);

$('#bt-run').addEventListener('click', runBacktest);
$('#bt-compare-btn').addEventListener('click', compareBacktest);
$('#lab-signals-btn').addEventListener('click', loadSignals);
$('#lab-optimize-btn').addEventListener('click', runOptimize);
$('#predict-btn').addEventListener('click', runPredict);
$('#predict-code').addEventListener('keydown', e => { if (e.key === 'Enter') runPredict(); });
$('#predict-code').addEventListener('change', checkModelStatus);
$('#predict-picker').addEventListener('change', e => {
  if (e.target.value) $('#predict-code').value = e.target.value;
  checkModelStatus();
});
})();
