/* 市场摘选页面：启动后台任务 → 轮询进度 → 展示 Top N → 历史回看
   最后加载；复用 ux.js 的 toast / 表格增强 / 代码详情链接。 */

(() => {
  const ST = window.ST;
  const { $, api, post, fmt, esc, card, tableRows, toast,
          showError, clearError, register } = ST;
  let currentTaskId = null;
  let pollTimer = null;

  function newId() {
    return (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : 'scan-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  }

  function setBusy(on) {
    $('scan-start').disabled = on;
    $('scan-cancel').disabled = !on;
  }

  function showProgress(on) {
    $('scan-progress').classList.toggle('hidden', !on);
  }

  function renderProgress(t) {
    const pct = Math.max(0, Math.min(100, Number(t.progress) || 0));
    $('scan-bar-fill').style.width = pct + '%';
    $('scan-progress-text').textContent = `${t.message || ''} · ${pct}%`;
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    setBusy(false);
  }

  function startPolling(taskId) {
    stopPolling();
    currentTaskId = taskId;
    setBusy(true);
    showProgress(true);
    poll();
    pollTimer = setInterval(poll, 1200);
  }

  async function poll() {
    if (!currentTaskId) return;
    try {
      const d = await api('/api/scan/status?task_id=' + encodeURIComponent(currentTaskId));
      const t = d.task;
      if (!t) { stopPolling(); return; }
      renderProgress(t);
      if (t.status !== 'running') {
        stopPolling();
        await onEnd(t);
      }
    } catch (e) {
      // 单次轮询失败不中断，等下一次
    }
  }

  async function onEnd(t) {
    if (t.status === 'done' && t.result) {
      loadResult(t.result);
      toast('扫描完成：命中 ' + (t.result.hit_count || 0) + ' 只', 'ok');
      $('scan-hint').textContent = t.message || '扫描完成';
    } else if (t.status === 'cancelled') {
      toast('扫描已取消', 'info');
      $('scan-hint').textContent = t.message || '已取消';
    } else {
      showError('扫描失败：' + (t.error || t.message || '未知错误'));
      $('scan-hint').textContent = '扫描失败';
    }
    await loadHistory();
  }

  async function start() {
    clearError();
    if (!$('scan-confirm').checked) {
      showError('请先勾选「确认执行扫描」');
      return;
    }
    const btn = $('scan-start');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '提交中…';
    try {
      const d = await post('/api/scan/start', {
        confirm: true,
        client_id: newId(),
        pool: $('scan-pool').value,
        force: false,
        top: Number($('scan-top').value) || 0,
        exclude_star: $('scan-exclude-star').checked,
      });
      const payload = d.result || {};
      if (!payload.task_id) throw new Error('未返回任务 ID');
      $('scan-confirm').checked = false;
      if (payload.already_running) {
        toast('已有扫描任务在运行，已接入其进度', 'info');
      }
      $('scan-hint').textContent = '任务已启动，后台执行中';
      startPolling(payload.task_id);
    } catch (e) {
      showError(String(e.message || e));
      btn.disabled = false;
    } finally {
      btn.textContent = original;
    }
  }

  async function cancel() {
    if (!currentTaskId) return;
    try {
      await post('/api/scan/cancel?task_id=' + encodeURIComponent(currentTaskId), {});
      $('scan-hint').textContent = '已请求取消（等待当前批次结束）…';
      toast('已请求取消', 'info');
    } catch (e) {
      showError(String(e.message || e));
    }
  }

  /* 自选代码集合：用于把命中表里已收藏的行标成「已自选」，避免重复添加。
     10 秒短缓存，加自选成功后强制刷新。 */
  let watchedCache = { at: 0, codes: new Set() };

  async function refreshWatched(force) {
    if (!force && Date.now() - watchedCache.at < 10000) return;
    try {
      const d = await api('/api/code-picker');
      watchedCache = {
        at: Date.now(),
        codes: new Set((d.watchlist || []).map(x => x.code)),
      };
    } catch (e) {
      watchedCache.at = Date.now();   // 失败也缓存，避免每次渲染都重试
    }
  }

  async function addWatchFromScan(btn) {
    const code = btn.dataset.watch;
    if (!code || btn.disabled) return;
    if (window.confirm && !window.confirm(`把 ${code} 加入自选？`)) return;
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '提交中…';
    try {
      await post('/api/write/watchlist', {
        confirm: true, client_id: newId(), op: 'add', code,
        note: '市场摘选命中',
      });
      btn.textContent = '已自选 ✓';
      toast('已加入自选：' + code, 'ok');
      await refreshWatched(true);
    } catch (e) {
      btn.disabled = false;
      btn.textContent = original;
      showError(String(e.message || e));
    }
  }

  async function loadResult(run) {
    if (!run) return;
    await refreshWatched();
    const cards = [
      card('股票池', esc(String(run.pool || '-'))),
      card('池规模', fmt(run.universe_count || 0, 0)),
      card('预筛候选', fmt(run.candidate_count || 0, 0)),
      card('条件命中', fmt(run.hit_count || 0, 0)),
      card('耗时', fmt(run.duration_seconds || 0, 1) + ' s'),
    ];
    if (run.star_excluded) {
      cards.push(card('跳过科创板', fmt(run.star_excluded, 0) + ' 只'));
    }
    $('scan-cards').innerHTML = cards.join('');
    $('scan-result-time').textContent = '生成于 '
      + String(run.generated_at || '').replace('T', ' ');

    const hits = run.hits || [];
    tableRows($('#scan-hits'), hits.map(h => {
      const owned = watchedCache.codes.has(h.code);
      return `<tr>
        <td>${esc(h.code)}</td><td>${esc(h.name || '')}</td>
        <td class="num">${fmt(h.price)}</td>
        <td class="num">${fmt(h.matched_count, 0)}/${fmt(h.total_rules, 0)}</td>
        <td>${(h.matched || []).map(m => esc(String(m[0]))).join('、')}</td>
        <td><div class="row-actions">
          <button type="button" class="btn ghost" data-watch="${esc(h.code)}"
            ${owned ? 'disabled' : ''} title="${owned ? '已在自选中' : '加入自选'}">
            ${owned ? '已自选' : '+ 自选'}</button>
        </div></td>
      </tr>`;
    }).join(''), 6, '本次没有股票满足当前条件组合');
  }

  async function loadLatest() {
    const d = await api('/api/scan/latest');
    if (d.run) {
      loadResult(d.run);
    } else {
      $('scan-cards').innerHTML =
        '<div class="result-box dim">暂无扫描结果，勾选确认后点「开始扫描」</div>';
    }
  }

  async function loadHistory() {
    const d = await api('/api/scan/runs?limit=10');
    tableRows($('#scan-history'), (d.rows || []).map(r => `<tr>
      <td>${r.id}</td><td>${esc(r.run_date)}</td><td>${esc(r.pool)}</td>
      <td class="num">${fmt(r.candidate_count, 0)}</td>
      <td class="num">${fmt(r.hit_count, 0)}</td>
      <td class="num">${fmt(r.duration_seconds, 1)}</td>
      <td><button class="btn ghost" data-run="${r.id}">查看</button></td>
    </tr>`).join(''), 7, '暂无扫描记录');
  }

  async function restoreTask() {
    const d = await api('/api/scan/status');
    const t = d.task;
    if (t && t.status === 'running') {
      renderProgress(t);
      startPolling(t.id);
    }
  }

  async function restoreConfig() {
    try {
      const cfg = await api('/api/scan/config');
      $('scan-exclude-star').checked = !!cfg.exclude_star;
    } catch (e) {
      // 配置读取失败时保持默认，不影响扫描
    }
  }

  async function loadScan() {
    await Promise.all([
      loadLatest(), loadHistory(), restoreTask(), restoreConfig(),
    ]);
  }

  /* 命中表的代码列：全局 linkifyCodes 的捕获委托会 stopPropagation，
     这里只作为兜底，避免表格重渲染后委托时序差异导致点不开详情。 */
  $('#scan-hits').querySelector('tbody').addEventListener('click', async e => {
    const btn = e.target.closest && e.target.closest('button[data-watch]');
    if (btn) {
      // 别让「加自选」冒泡成「打开个股详情」
      if (e.stopPropagation) e.stopPropagation();
      await addWatchFromScan(btn);
      return;
    }
    const td = e.target.closest && e.target.closest('td.stock-link');
    if (td && td.dataset.code && ST.openStockDetail) {
      ST.openStockDetail(td.dataset.code);
    }
  });

  register('scan', loadScan);
  $('scan-start').addEventListener('click', start);
  $('scan-cancel').addEventListener('click', cancel);
  $('#scan-history').querySelector('tbody').addEventListener('click', async e => {
    const btn = e.target.closest('button[data-run]');
    if (!btn) return;
    try {
      const d = await api('/api/scan/run/' + encodeURIComponent(btn.dataset.run));
      loadResult(d.run);
      toast('已加载该次扫描结果', 'ok', 1800);
    } catch (err) {
      showError(String(err.message || err));
    }
  });
})();
