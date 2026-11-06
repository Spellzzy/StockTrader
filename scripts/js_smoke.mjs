/**
 * Web 前端冒烟 + 行为测试：在 Node 里用增强 DOM mock 依序执行
 * app.js / ux.js / p1.js / p2.js / detail.js / scan.js，任一脚本顶层抛错即失败，
 * 并验证缓存策略、确认门禁、密度偏好、回车提交等关键交互。
 *
 * 背景：这些文件是经典 script，共享全局词法环境；曾因顶层 const 重名
 * 和 $() 选择器用法不一致导致整个脚本静默失效，纯接口测试发现不了。
 *
 * 运行：node scripts/js_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function makeParent() {
  return {
    insertBefore() {}, appendChild() {},
    querySelector: () => null, querySelectorAll: () => [],
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  };
}

function makeElement(id) {
  const handlers = {};
  const classes = new Set();
  const el = {
    id, tagName: "DIV", innerHTML: "", textContent: "", className: "",
    value: "", checked: false, type: "", title: "", placeholder: "",
    disabled: false, href: "", download: "", hidden: false,
    scrollLeft: 0, clientWidth: 1000, offsetLeft: 0, offsetWidth: 80,
    dataset: {}, style: {}, children: [], parentNode: makeParent(),
    nextElementSibling: null, _handlers: handlers, _classes: classes,
    classList: {
      add(c) { classes.add(c); },
      remove(c) { classes.delete(c); },
      toggle(c, force) {
        const on = force === undefined ? !classes.has(c) : !!force;
        if (on) classes.add(c); else classes.delete(c);
        return on;
      },
      contains(c) { return classes.has(c); },
    },
    addEventListener(type, fn) { (handlers[type] ||= []).push(fn); },
    removeEventListener() {},
    dispatchEvent(evt) {
      if (!evt) return true;
      (handlers[evt.type] || []).forEach(fn => fn(evt));
      return true;
    },
    appendChild(child) {
      this.children.push(child); child.parentNode = this; return child;
    },
    insertBefore(child) {
      this.children.push(child); child.parentNode = this; return child;
    },
    replaceChildren(...nodes) { this.children = nodes; },
    querySelector(sel) {
      if (sel === ".toast.free") {
        return this.children.find(c => c.classList.contains("free")) || null;
      }
      return makeElement(id + "::" + sel);
    },
    querySelectorAll(sel) {
      if (sel === ".picker-item") {
        return this.children.filter(c => c.classList.contains("picker-item"));
      }
      return [];
    },
    remove() {}, focus() {}, click() {}, scrollIntoView() {},
    closest: () => null,
  };
  return el;
}

const elements = new Map();
const docHandlers = {};
const gateLabels = [];
globalThis.document = {
  hidden: false,
  readyState: undefined,
  body: makeElement("body"),
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  },
  createElement: (tag) => makeElement("created::" + tag),
  querySelector: () => null,
  querySelectorAll(sel) {
    if (sel === ".confirm[data-gate]") return gateLabels;
    return [];
  },
  addEventListener(type, fn) { (docHandlers[type] ||= []).push(fn); },
  dispatchEvent(evt) {
    (docHandlers[evt.type] || []).forEach(fn => fn(evt));
    return true;
  },
};
globalThis.window = globalThis;
const winHandlers = {};
globalThis.addEventListener = (type, fn) => { (winHandlers[type] ||= []).push(fn); };
globalThis.location = { hash: "", pathname: "/" };
globalThis.history = { replaceState() {} };
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.setInterval = () => 0;      // 不真的起定时器，避免测试进程不退出
globalThis.clearInterval = () => {};
const forecastMock = {
  code: "sh600892", name: "大晟文化", phase: "intraday", progress: 0.3,
  price: 16.39, prev_close: 16.66, day_high: 16.76, as_of: "20261106103000",
  targets: { p50: 16.80, p75: 16.92, p90: 17.13 },
  band: { low: 16.80, high: 17.13 },
  probabilities: { p50: 0.31, p75: 0.15, p90: 0.06 },
  upside_pct: { p50: 2.5, p75: 3.26, p90: 4.52 },
  basis: {
    sample_days: 120, up_quantiles_pct: { p50: 0.99, p75: 2.30, p90: 4.22 },
    amplitude_p75_pct: 4.02, decay: 0.8, limit_price: 18.33,
  },
  quality: {
    samples: 60, touch_p75: 0.12, coverage: 0.37, mae_pct: 1.97,
    baseline_mae_pct: 1.30, better_than_baseline: false,
  },
  note: "测试用数据",
};
globalThis.fetch = async (url) => ({
  ok: true,
  json: async () => String(url).includes("/api/forecast/high")
    ? { ok: true, data: forecastMock }
    : { ok: true, data: { version: "0.0.0-smoke" } },
});
if (!globalThis.crypto) globalThis.crypto = (await import("node:crypto")).webcrypto;
if (!globalThis.Event) {
  globalThis.Event = class {
    constructor(type, opts) { this.type = type; Object.assign(this, opts || {}); }
  };
}

let asyncFailures = 0;
process.on("unhandledRejection", () => { asyncFailures += 1; });

const names = ["app.js", "ux.js", "p1.js", "p2.js", "detail.js", "scan.js"];
const combined = names
  .map((name) => readFileSync(join(root, "app/web/static", name), "utf-8"))
  .join("\n;\n");

try {
  // eslint-disable-next-line no-eval
  (0, eval)(combined);
} catch (e) {
  console.error("脚本顶层执行失败:", e && e.message);
  throw e;
}
console.log(`  ${names.join(" / ")} 同全局环境顶层执行 OK`);

const ST = globalThis.ST;

/* 缓存策略：轮询 / 状态 / 配置类接口绝不能进慢任务缓存 */
const policy = ST && ST.cachePolicy;
if (!policy) throw new Error("ux.js 未暴露 cachePolicy 探针");
const mustNotCache = [
  "/api/predict/train/status?task_id=abc",
  "/api/predict/model-status?code=sh600892",
  "/api/predict/train",
  "/api/scan/status?task_id=abc",
  "/api/scan/config",
  "/api/stock/detail?code=sh600519",
];
const mustCache = [
  "/api/backtest/run", "/api/backtest/compare",
  "/api/lab/signals?code=sh600519", "/api/lab/optimize",
  "/api/predict?code=sh600519",
];
for (const p of mustNotCache) {
  if (policy.isCacheable(p)) throw new Error(`不该缓存却被缓存: ${p}`);
}
for (const p of mustCache) {
  if (!policy.isCacheable(p)) throw new Error(`慢任务未被缓存: ${p}`);
}
if (typeof ST.invalidate !== "function") {
  throw new Error("ux.js 缺少 ST.invalidate（训练完成后需失效预测缓存）");
}
console.log("  缓存白名单 / 失效接口行为断言 OK");

/* 确认门禁：未勾选时禁用提交，勾选后放行 */
const gateBox = document.getElementById("w-confirm");
const gateBtn = document.getElementById("w-submit");
const gateLabel = makeElement("gate-label");
gateLabel.dataset.gate = "w-submit";
gateLabel.querySelector = () => gateBox;
gateLabels.push(gateLabel);
gateBox.checked = false;
ST.syncConfirmGates();
if (!gateBtn.disabled) throw new Error("未勾选确认时提交按钮应禁用");
gateBox.checked = true;
ST.syncConfirmGates();
if (gateBtn.disabled) throw new Error("勾选确认后提交按钮应可用");
console.log("  确认勾选门禁行为断言 OK");

/* 紧凑密度：切换后 body class 与 localStorage 都要更新 */
const density = document.getElementById("density-compact");
density.checked = true;
density.dispatchEvent({ type: "change" });
if (!document.body.classList.contains("density-compact")) {
  throw new Error("紧凑密度未应用到 body");
}
if (localStorage.getItem("st.density") !== "compact") {
  throw new Error("紧凑密度偏好未持久化");
}
console.log("  紧凑密度偏好行为断言 OK");

/* 表单回车：Enter 触发 data-enter 指向的按钮 */
const host = makeElement("form-host");
host.dataset.enter = "w-submit";
const field = makeElement("field");
field.tagName = "INPUT";
field.closest = (sel) => (sel === "[data-enter]" ? host : null);
let clicked = 0;
gateBtn.click = () => { clicked += 1; };
gateBtn.disabled = false;
document.dispatchEvent({
  type: "keydown", key: "Enter", target: field,
  ctrlKey: false, metaKey: false, shiftKey: false, altKey: false,
  preventDefault() {},
});
if (clicked !== 1) throw new Error("表单 Enter 未触发默认提交按钮");
console.log("  表单回车提交行为断言 OK");

/* 常驻下拉切换股票：目标高点卡片必须跟着刷新
   （曾出现 change 未派发，卡片一直停在进页面时的默认股票） */
const picker = document.getElementById("predict-picker");
const codeInput = document.getElementById("predict-code");
const cardBox = document.getElementById("high-forecast");
codeInput.value = "sz002555";
cardBox.dataset.code = "sz002555";
picker.value = "sh600892";
picker.dispatchEvent({ type: "change", target: picker });
if (codeInput.value !== "sh600892") {
  throw new Error("常驻下拉没有把代码写入输入框");
}
await new Promise((r) => setTimeout(r, 80));
if (cardBox.dataset.code !== "sh600892") {
  throw new Error("切换股票后目标高点卡片未刷新");
}
console.log("  切换股票联动刷新目标高点行为断言 OK");

/* 报告页：Markdown 在面板内展示原文（含可信度卡片）；HTML 仍新标签打开 */
const digestName = "digest_20261106_am.md";
const htmlName = "daily_20261106_am.html";
const credibility = [
  "## 可信度",
  "- 行情截止: 2026-11-06 09:25:00",
  "- 置信度: 72.5%（样本 120 日）",
].join("\n");
const digestBody = `# 智能日报 2026-11-06 09:30 (am)\n\n${credibility}\n\n贵州茅台 看涨\n`;
const jsonName = "digest_20261106_am.json";
const digestJson = {
  date: "2026-11-06 09:30",
  slot: "am",
  total: 1,
  bullish: [{
    code: "sh600519", name: "茅台", signal: "看涨", score: 12.5,
    quality: {
      mean_accuracy: 0.273, baseline: 0.333, factor: 0.4,
      below_baseline: true, note: "样本偏弱",
    },
  }],
  bearish: [],
  neutral: [{ code: "sz000001", name: "平安", signal: "震荡", score: 0.2 }],
};
const reportFiles = [
  { name: htmlName, size: 2048, updated_at: "2026-11-06T09:30:00", kind: "html" },
  { name: digestName, size: digestBody.length, updated_at: "2026-11-06T09:30:00", kind: "markdown" },
  { name: jsonName, size: 320, updated_at: "2026-11-06T09:30:00", kind: "json" },
];
const seenReportUrls = [];
const origFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const u = String(url);
  seenReportUrls.push(u);
  if (u.includes("/api/reports/") && u.endsWith("/content")) {
    if (u.includes(".json")) {
      return { ok: true, json: async () => ({ ok: true, data: digestJson }) };
    }
    return { ok: true, json: async () => ({ ok: true, data: { name: digestName, content: digestBody } }) };
  }
  if (u.includes("/api/reports")) {
    return { ok: true, json: async () => ({ ok: true, data: { files: reportFiles } }) };
  }
  return origFetch(url);
};
const loadReportsFn = globalThis.loadReports;
const openMarkdownReportFn = globalThis.openMarkdownReport;
if (typeof loadReportsFn !== "function" || typeof openMarkdownReportFn !== "function") {
  throw new Error("app.js 未暴露 loadReports / openMarkdownReport");
}
await loadReportsFn();
const listHtml = document.getElementById("report-list").innerHTML;
const htmlItem = listHtml.match(new RegExp(`<a\\b[^>]*>[\\s\\S]*?${htmlName}[\\s\\S]*?</a>`));
const mdItem = listHtml.match(new RegExp(`<button\\b[^>]*>[\\s\\S]*?${digestName}[\\s\\S]*?</button>`));
if (!htmlItem || !mdItem) throw new Error("报告列表未同时渲染 HTML 与 Markdown");
if (!htmlItem[0].includes('target="_blank"') || !htmlItem[0].includes(`/reports/${htmlName}`)) {
  throw new Error("HTML 报告应新标签打开 /reports/{name}");
}
if (mdItem[0].includes('target="_blank"') || mdItem[0].includes("/reports/")) {
  throw new Error("Markdown 不应走 HTML 新标签打开");
}
if (!mdItem[0].includes("openMarkdownReport")) {
  throw new Error("Markdown 条目未绑定打开正文的点击");
}
await openMarkdownReportFn(digestName);
const contentUrl = seenReportUrls.find((u) => u.includes("/content"));
if (!contentUrl || !contentUrl.includes(encodeURIComponent(digestName))) {
  throw new Error("打开 Markdown 未请求 /api/reports/{name}/content");
}
const reportBody = document.getElementById("report-body");
if (!reportBody || reportBody.classList.contains("hidden")) {
  throw new Error("Markdown 正文未显示在 #panel-reports 内");
}
const shown = (reportBody.children[0] && reportBody.children[0].textContent) || reportBody.textContent || "";
for (const line of credibility.split("\n")) {
  if (!shown.includes(line)) throw new Error("可信度卡片原文丢失: " + line);
}
if (shown !== digestBody) throw new Error("Markdown 正文被改写，未按原文展示");
if (String(shown).includes("digest-evidence-row") || String(shown).includes("可信证据")) {
  throw new Error("Markdown 报告不应新增点行进可信证据的入口");
}

const jsonItem = listHtml.match(new RegExp(`<button\\b[^>]*>[\\s\\S]*?${jsonName}[\\s\\S]*?</button>`));
if (!jsonItem) throw new Error("报告列表未渲染 JSON");
if (jsonItem[0].includes('target="_blank"') || !jsonItem[0].includes("openJsonReport")) {
  throw new Error("JSON 应在页内只读预览，而不是新标签打开");
}
if (typeof globalThis.openJsonReport !== "function") {
  throw new Error("app.js 未暴露 openJsonReport");
}
await globalThis.openJsonReport(jsonName);
const jsonView = reportBody.children[0];
const jsonMarkup = (jsonView && jsonView.innerHTML) || "";
if (!jsonView || jsonView.className !== "report-json") {
  throw new Error("JSON 未按结构化预览展示");
}
for (const piece of ["茅台", "平安", "27.3%", "33.3%", "0.40", "样本偏弱", "只读预览"]) {
  if (!jsonMarkup.includes(piece)) throw new Error("结构化预览缺少: " + piece);
}
if (jsonMarkup.includes("<textarea") || jsonMarkup.includes("contenteditable") || jsonMarkup.includes("<input")) {
  throw new Error("JSON 预览不应是可编辑编辑器");
}
globalThis.fetch = origFetch;
console.log("  报告页 Markdown 原文 / JSON 结构化预览 / HTML 新标签行为断言 OK");

/* 日报 JSON 行绑定快照，点击 / 回车 / 空格打开抽屉「可信证据」。
   有 quality 时数字与该行一致；无 quality 只显示占位，且不请求预测/质量接口。 */
function snapshotsFromMarkup(html) {
  const found = [];
  const re = /data-evidence="([^"]*)"/g;
  let match;
  while ((match = re.exec(html))) found.push(JSON.parse(decodeURIComponent(match[1])));
  return found;
}
if (typeof globalThis.renderDigestPreview !== "function") {
  throw new Error("app.js 未暴露 renderDigestPreview");
}
if (typeof ST.renderDigestEvidence !== "function") {
  throw new Error("未暴露 renderDigestEvidence");
}
if (typeof ST.activateDigestEvidenceRow !== "function") {
  throw new Error("未暴露 activateDigestEvidenceRow");
}

const richDigest = {
  date: "2026-11-06 09:30",
  slot: "am",
  total: 3,
  bullish: [{
    code: "sh600519",
    name: "茅台",
    signal: "看涨",
    score: 12.5,
    stars: 2,
    confidence: 80,
    models_used: 9,
    key_factors: ["动量", "放量", "北向", "第四条不应出现"],
    quality: {
      below_baseline: true,
      mean_accuracy: 0.273,
      baseline: 0.333,
      factor: 0.4,
      note: "样本偏弱",
      confidence: 12.5,
      models_used: 3,
    },
  }],
  bearish: [{
    code: "sz000001",
    name: "平安",
    signal: "看跌",
    score: -1.5,
    stars: 1,
    confidence: 40,
    key_factors: ["破位"],
  }],
  neutral: [{
    code: "sz000002",
    name: "坏质量",
    signal: "震荡",
    score: 0.2,
    quality: "nope",
  }],
};
const richHtml = globalThis.renderDigestPreview("digest.json", richDigest).innerHTML;
const richSnaps = snapshotsFromMarkup(richHtml);
if (richSnaps.length !== 3) {
  throw new Error("看涨/看跌/震荡行都应绑定快照，实际 " + richSnaps.length);
}
const bullSnap = richSnaps[0];
if (bullSnap.code !== "sh600519" || bullSnap.signal !== "看涨" || bullSnap.score !== 12.5
    || bullSnap.stars !== 2 || bullSnap.confidence !== 80 || bullSnap.models_used !== 9) {
  throw new Error("行快照未带上信号、评分、星级、置信度或模型数");
}
if (!Array.isArray(bullSnap.key_factors) || bullSnap.key_factors[0] !== "动量") {
  throw new Error("行快照未带上 key_factors");
}
if (!bullSnap.quality || bullSnap.quality.mean_accuracy !== 0.273
    || bullSnap.quality.baseline !== 0.333 || bullSnap.quality.factor !== 0.4
    || bullSnap.quality.below_baseline !== true || bullSnap.quality.note !== "样本偏弱"
    || bullSnap.quality.confidence !== 12.5 || bullSnap.quality.models_used !== 3) {
  throw new Error("行快照的 quality 与该行不一致");
}
if (richSnaps[1].quality !== undefined) {
  throw new Error("无 quality 的行不应编造质量对象");
}
if (richSnaps[2].quality !== "nope") {
  throw new Error("非对象 quality 应原样绑在快照上，而不是当成合法质量");
}
if (!richHtml.includes('class="clickable digest-evidence-row"')
    || !richHtml.includes('role="button"') || !richHtml.includes('tabindex="0"')) {
  throw new Error("结构化行应可点击且可聚焦");
}
for (const hint of ["查看 sh600519 茅台 的可信证据", "回车或空格"]) {
  if (!richHtml.includes(hint)) throw new Error("行缺少可访问提示: " + hint);
}
const previewSnaps = snapshotsFromMarkup(jsonMarkup);
const previewBull = previewSnaps.find((item) => item.code === "sh600519");
const previewNeutral = previewSnaps.find((item) => item.code === "sz000001");
if (!previewBull || previewBull.quality.factor !== 0.4 || previewBull.quality.mean_accuracy !== 0.273) {
  throw new Error("已打开的 JSON 预览没有把该行 quality 绑到行上");
}
if (!previewNeutral || previewNeutral.quality !== undefined) {
  throw new Error("已打开的 JSON 预览里，无质量行仍应可点且不编造 quality");
}
if ((jsonMarkup.match(/digest-evidence-row/g) || []).length !== 2) {
  throw new Error("空的看跌区不应生成可点行");
}

const withQuality = ST.renderDigestEvidence(bullSnap);
for (const piece of ["可信证据", "质量", "弱于基线", "说明", "样本偏弱", "准确率", "27.3%", "33.3%",
  "降权", "0.40", "置信度", "12.5%", "模型数", "3", "依据", "动量", "放量", "北向", "quality-warn",
  "看涨", "+12.5"]) {
  if (!withQuality.includes(piece)) throw new Error("有质量证据缺少: " + piece);
}
if (withQuality.includes("80.0%") || withQuality.includes(">9<") || withQuality.includes("第四条")) {
  throw new Error("有质量证据用了条目上的置信度/模型数，或依据超过 3 条");
}
if (withQuality.includes("模型无预测能力") || withQuality.includes("请勿据此下单")) {
  throw new Error("证据区不应新增恐吓文案");
}

const noQuality = ST.renderDigestEvidence(richSnaps[1]);
if (!noQuality.includes("可信证据") || !noQuality.includes("本条无质量字段")) {
  throw new Error("无 quality 时应显示占位文案");
}
if (noQuality.includes("quality-warn") || noQuality.includes("优于基线") || noQuality.includes("准确率")) {
  throw new Error("无 quality 时不应渲染质量数字");
}
const badQuality = ST.renderDigestEvidence(richSnaps[2]);
if (!badQuality.includes("本条无质量字段")) throw new Error("非对象 quality 应走占位分支");
if (!ST.renderDigestEvidence(null).includes("本条无质量字段")) {
  throw new Error("空快照不应抛错，且应走占位分支");
}

const strong = ST.renderDigestEvidence({
  code: "sh600000",
  signal: "看涨",
  score: 8.5,
  stars: 4,
  confidence: 61,
  key_factors: ["均线多头", "  ", "放量"],
  quality: { below_baseline: false, note: "  ", mean_accuracy: 0.5 },
});
for (const piece of ["优于基线", "质量正常", "50.0%", "61.0%", "均线多头", "放量"]) {
  if (!strong.includes(piece)) throw new Error("强质量证据缺少: " + piece);
}
if (strong.includes("quality-warn") || strong.includes("降权") || strong.includes("模型数")
    || strong.includes("勿当强信号") || strong.includes("% ·")) {
  throw new Error("缺字段被填了数字，或强卡片用了弱提示/恐吓语");
}
const onlyBase = ST.renderDigestEvidence({
  signal: "看跌",
  quality: { below_baseline: true, baseline: 0.333, note: "" },
});
if (!onlyBase.includes("33.3%") || onlyBase.includes("准确率") || !onlyBase.includes("弱于基线，勿当强信号")) {
  throw new Error("只有基线时不应出现准确率，空说明应使用既有弱默认文案");
}
if (!onlyBase.includes("quality-warn")) throw new Error("弱于基线应使用 quality-warn");
const junk = ST.renderDigestEvidence({
  confidence: 70,
  quality: {
    below_baseline: false,
    mean_accuracy: "高",
    baseline: null,
    factor: true,
    note: "质量正常",
    models_used: "两只",
    confidence: "高",
  },
});
if (junk.includes("准确率") || junk.includes("降权") || junk.includes("模型数") || junk.includes("70.0%")) {
  throw new Error("非法数字不应回落成编造值");
}
if (!junk.includes("质量正常") || !junk.includes("优于基线")) {
  throw new Error("合法的质量判断和说明仍应保留");
}

let activated = null;
const realOpen = ST.openStockDetail;
ST.openStockDetail = (code, opts) => { activated = { code, opts }; };
function evidenceRow(snap) {
  const row = makeElement("digest-row");
  row.classList.add("digest-evidence-row");
  row.dataset.code = snap.code || "";
  row.dataset.evidence = encodeURIComponent(JSON.stringify(snap));
  row.getAttribute = (name) => {
    if (name === "data-evidence") return row.dataset.evidence;
    if (name === "data-code") return row.dataset.code;
    return null;
  };
  row.closest = (sel) => (sel === "tr.digest-evidence-row" ? row : null);
  return row;
}
const bullRow = evidenceRow(bullSnap);
let keyPrevented = 0;
document.dispatchEvent({
  type: "keydown",
  key: "Enter",
  target: bullRow,
  preventDefault() { keyPrevented += 1; },
});
if (!activated || activated.code !== "sh600519" || !activated.opts
    || activated.opts.evidence.quality.mean_accuracy !== 0.273) {
  throw new Error("回车未带该行快照打开个股详情");
}
activated = null;
document.dispatchEvent({
  type: "keydown",
  key: " ",
  target: bullRow,
  preventDefault() { keyPrevented += 1; },
});
if (!activated || activated.opts.evidence.code !== "sh600519" || keyPrevented !== 2) {
  throw new Error("空格未带快照打开，或没有阻止页面滚动");
}
activated = null;
document.dispatchEvent({ type: "click", target: bullRow, preventDefault() {}, stopPropagation() {} });
if (!activated || activated.opts.evidence.quality.factor !== 0.4) {
  throw new Error("点击行未带该行快照打开个股详情");
}
const plainRow = evidenceRow(richSnaps[1]);
activated = null;
document.dispatchEvent({ type: "click", target: plainRow, preventDefault() {}, stopPropagation() {} });
if (!activated || activated.code !== "sz000001" || activated.opts.evidence.quality !== undefined) {
  throw new Error("无质量行点击后不应编造 quality");
}
const linkedCell = makeElement("linked-code");
linkedCell.classList.add("stock-link");
linkedCell.dataset.code = "sh600519";
linkedCell.closest = (sel) => {
  if (sel === "td.stock-link") return linkedCell;
  if (sel === "tr.digest-evidence-row") return bullRow;
  return null;
};
activated = null;
document.dispatchEvent({
  type: "click",
  target: linkedCell,
  preventDefault() {},
  stopPropagation() {},
});
if (!activated || !activated.opts || activated.opts.evidence.quality.factor !== 0.4) {
  throw new Error("日报行里的代码格也应带上本条快照，而不是普通详情入口");
}
ST.openStockDetail = realOpen;
console.log("  日报行快照绑定与有/无质量证据渲染断言 OK");

const seenDetailUrls = [];
globalThis.fetch = async (url) => {
  const u = String(url);
  seenDetailUrls.push(u);
  const code = (u.split("code=")[1] || "").split("&")[0];
  return {
    ok: true,
    json: async () => ({
      ok: true,
      data: {
        code: decodeURIComponent(code || ""),
        name: "详情",
        generated_at: "2026-11-06T09:30:00",
        quote: {},
        kline: [],
        tech: {},
        stock: {},
        holding: null,
        alert_count: 0,
        recent_trades: [],
      },
    }),
  };
};
await ST.openStockDetail("sh600519", { evidence: bullSnap });
const evidenceBox = document.getElementById("detail-evidence");
if (!evidenceBox || evidenceBox.classList.contains("hidden")) {
  throw new Error("打开带证据的行后，抽屉证据区不可见");
}
if (!document.getElementById("stock-detail") || document.getElementById("stock-detail").classList.contains("hidden")) {
  throw new Error("点击行后个股抽屉未打开");
}
for (const piece of ["可信证据", "27.3%", "33.3%", "0.40", "12.5%", "样本偏弱", "quality-warn"]) {
  if (!evidenceBox.innerHTML.includes(piece)) throw new Error("抽屉证据区与该行质量不一致: " + piece);
}
if (seenDetailUrls.some((u) => u.includes("/api/predict") || u.includes("quality"))) {
  throw new Error("打开证据不应新增预测或质量请求");
}
if (!seenDetailUrls.some((u) => u.includes("/api/stock/detail"))) {
  throw new Error("抽屉仍应加载该代码的既有详情");
}
const footIds = ["detail-goto-market", "detail-goto-predict", "detail-goto-write", "detail-refresh"];
for (const id of footIds) {
  const btn = document.getElementById(id);
  if (!btn || !btn._handlers.click || !btn._handlers.click.length) {
    throw new Error("抽屉脚部按钮不可用: " + id);
  }
}
document.getElementById("detail-refresh").dispatchEvent({ type: "click" });
await new Promise((r) => setTimeout(r, 40));
if (!evidenceBox.innerHTML.includes("27.3%") || evidenceBox.innerHTML.includes("本条无质量字段")) {
  throw new Error("刷新同一只股票不应清掉本条可信证据");
}
await ST.openStockDetail("sz000001", { evidence: richSnaps[1] });
if (!evidenceBox.innerHTML.includes("本条无质量字段") || evidenceBox.innerHTML.includes("27.3%")) {
  throw new Error("换一条无质量行时，证据区应换成占位且不残留上一只的数字");
}
await ST.openStockDetail("sh600000");
if (evidenceBox.innerHTML.trim() || !evidenceBox.classList.contains("hidden")) {
  throw new Error("从其它入口打开股票时不应留下日报证据");
}
await ST.openStockDetail("sh600519", { evidence: bullSnap });
ST.closeStockDetail();
if (evidenceBox.innerHTML.trim() || !evidenceBox.classList.contains("hidden")) {
  throw new Error("关闭抽屉后应清空可信证据");
}
if (!document.getElementById("stock-detail").classList.contains("hidden")) {
  throw new Error("关闭抽屉失败");
}
globalThis.fetch = origFetch;
console.log("  抽屉可信证据展示、清空与不新增质量请求断言 OK");

/* 个股详情量比：源字段 / 回退值 / 全缺显示「—」，且不顶替 60 日均量倍数 */
if (typeof ST.detailVolumeRatio !== "function") {
  throw new Error("detail.js 未暴露 detailVolumeRatio");
}
if (typeof ST.detailOverviewHtml !== "function") {
  throw new Error("detail.js 未暴露 detailOverviewHtml");
}

function assertRatio(input, expect) {
  const view = ST.detailVolumeRatio(input);
  if (view.text !== expect.text) {
    throw new Error(`量比文案应为 ${expect.text}，实际 ${view.text}`);
  }
  if ((view.label || "") !== (expect.label || "")) {
    throw new Error(`量比标签应为「${expect.label || ""}」，实际「${view.label || ""}」`);
  }
  if (view.cls !== expect.cls) {
    throw new Error(`量比着色应为 ${expect.cls}，实际 ${view.cls}`);
  }
}

assertRatio({ quote: { volume_ratio: 3 }, volume_ratio: 1 }, { text: "3.00", label: "放量", cls: "up" });
assertRatio({ quote: { volume_ratio: 1.5, vol_ratio: 0.2 } }, { text: "1.50", label: "放量", cls: "warn" });
assertRatio({ quote: { volume_ratio: 0, vol_ratio: 1.2 } }, { text: "1.20", label: "平量", cls: "down" });
assertRatio({ quote: {}, volume_ratio: 0.8 }, { text: "0.80", label: "平量", cls: "down" });
assertRatio({ quote: { volume_ratio: 0.79 } }, { text: "0.79", label: "缩量", cls: "dim" });
assertRatio({ quote: {}, volume_ratio: null }, { text: "—", label: "", cls: "dim" });
assertRatio({}, { text: "—", label: "", cls: "dim" });

const emptyOverview = ST.detailOverviewHtml({
  code: "sh600519",
  quote: { volume: 12345, turnover_rate: 1.25, turnover: 99, price: 10, change_percent: 0.2 },
  volume_ratio: null,
  kline: [
    { close: 10, volume: 1000 },
    { close: 11, volume: 2000 },
  ],
  tech: {},
  stock: {},
  holding: null,
  alert_count: 0,
  recent_trades: [],
});
if (!emptyOverview.includes("量比") || !emptyOverview.includes("—")) {
  throw new Error("无量比时概览应显示「量比 —」");
}
if (emptyOverview.includes("放量") || emptyOverview.includes("平量") || emptyOverview.includes("缩量")) {
  throw new Error("无量比时不应出现放量/平量/缩量标签");
}
if (!emptyOverview.includes("最新量 / 均量")) {
  throw new Error("60 日「最新量 / 均量」被量比顶替或删掉了");
}
if (!emptyOverview.includes("手")) {
  throw new Error("成交量应继续以「手」展示");
}
if (!emptyOverview.includes("1.25%") || emptyOverview.includes("99")) {
  throw new Error("换手应使用 turnover_rate，而不是 turnover");
}

const hotOverview = ST.detailOverviewHtml({
  code: "sh600519",
  quote: { volume_ratio: 3.2, volume: 100, turnover_rate: 2.5, price: 10, change_percent: 1 },
  kline: [
    { close: 10, volume: 1000 },
    { close: 12, volume: 4000 },
  ],
  tech: {},
  stock: {},
  holding: null,
  alert_count: 0,
  recent_trades: [],
});
if (!hotOverview.includes("3.20") || !hotOverview.includes("放量")) {
  throw new Error("有源量比时概览应醒目展示「量比 3.20」和放量标签");
}
if (!hotOverview.includes("最新量 / 均量")) {
  throw new Error("有量比时仍要单独保留「最新量 / 均量」");
}
if (!emptyOverview.includes("vol-mini") || !emptyOverview.includes("连放")) {
  throw new Error("近端放量应在概览显示迷你量柱和连放");
}
if (typeof ST.recentVolumeHtml !== "function") {
  throw new Error("detail.js 未暴露 recentVolumeHtml");
}
const shrinking = ST.recentVolumeHtml([
  { date: "2026-11-04", volume: 300 },
  { date: "2026-11-05", volume: 200 },
  { date: "2026-11-06", volume: 100 },
]);
if (!shrinking.includes("连缩 3 日") || !shrinking.includes("vol-mini")) {
  throw new Error("连缩未提示");
}
const flatVol = ST.recentVolumeHtml([
  { date: "2026-11-04", volume: 10 },
  { date: "2026-11-05", volume: 10 },
  { date: "2026-11-06", volume: 10 },
]);
if (flatVol.includes("连放") || flatVol.includes("连缩")) {
  throw new Error("量能持平不应提示连放/连缩");
}
if ((flatVol.match(/class="vol-bar/g) || []).length !== 3) {
  throw new Error("持平仍应画出量柱");
}
const manyVols = [];
for (let i = 0; i < 8; i++) {
  manyVols.push({ date: `2026-11-0${i + 1}`, volume: 100 * (i + 1) });
}
const recent = ST.recentVolumeHtml(manyVols);
if ((recent.match(/class="vol-bar/g) || []).length !== 5) {
  throw new Error("量柱应只取近 5 日");
}
if (!recent.includes("连放 5 日") || recent.includes("11-01") || !recent.includes("11-08")) {
  throw new Error("近 5 日窗口或连放天数不对");
}
if (ST.recentVolumeHtml([]) !== "" || ST.recentVolumeHtml(null) !== "") {
  throw new Error("没有 K 线时不应渲染量能块");
}
console.log("  个股详情量比与近 5 日量能行为断言 OK");

/* 侧栏：展开态与组折叠写入 localStorage，且不改当前页、不改紧凑密度 */
if (!ST.nav || typeof ST.nav.setExpanded !== "function"
    || typeof ST.nav.setGroupCollapsed !== "function"
    || typeof ST.nav.restore !== "function") {
  throw new Error("ux.js 未暴露侧栏导航状态 ST.nav");
}
localStorage.setItem("st.tab", "market");
ST.nav.setExpanded(false);
if (!document.body.classList.contains("side-rail")
    || document.body.classList.contains("side-expanded")) {
  throw new Error("收起侧栏未切到图标轨");
}
if (localStorage.getItem("st.side") !== "rail") {
  throw new Error("侧栏收起态未写入 localStorage");
}
if (localStorage.getItem("st.tab") !== "market") {
  throw new Error("收起侧栏丢掉了当前页");
}
ST.nav.setExpanded(true);
if (localStorage.getItem("st.side") !== "expanded"
    || !document.body.classList.contains("side-expanded")
    || document.body.classList.contains("side-rail")) {
  throw new Error("展开侧栏未持久化");
}
ST.nav.setGroupCollapsed("analysis", true);
if (!document.getElementById("nav-group-analysis").classList.contains("is-collapsed")) {
  throw new Error("组折叠未反映到导航组");
}
let storedGroups;
try {
  storedGroups = JSON.parse(localStorage.getItem("st.nav.groups") || "{}");
} catch (e) {
  throw new Error("组折叠状态不是 JSON");
}
if (storedGroups.analysis !== true) throw new Error("组折叠未写入 localStorage");
if (localStorage.getItem("st.density") !== "compact") {
  throw new Error("侧栏状态不应改写紧凑密度");
}
localStorage.setItem("st.nav.groups", JSON.stringify({ trade: true }));
localStorage.setItem("st.side", "rail");
document.body.classList.remove("side-rail");
document.body.classList.remove("side-expanded");
ST.nav.restore();
if (!document.body.classList.contains("side-rail")) {
  throw new Error("刷新后未恢复图标轨");
}
if (!document.getElementById("nav-group-trade").classList.contains("is-collapsed")) {
  throw new Error("刷新后未恢复组折叠");
}
if (document.getElementById("nav-group-analysis").classList.contains("is-collapsed")) {
  throw new Error("未保存的组不应保持折叠");
}
if (localStorage.getItem("st.tab") !== "market") {
  throw new Error("恢复侧栏偏好时丢掉了当前页");
}
console.log("  侧栏展开态与组折叠持久化行为断言 OK");

await new Promise((r) => setTimeout(r, 120));
if (asyncFailures > 0) {
  console.error(`发现 ${asyncFailures} 个未处理的异步错误`);
  process.exit(1);
}
console.log("JS 冒烟测试通过：六个脚本顶层与关键交互行为均正常");
