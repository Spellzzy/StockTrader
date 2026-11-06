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
const reportFiles = [
  { name: htmlName, size: 2048, updated_at: "2026-11-06T09:30:00", kind: "html" },
  { name: digestName, size: digestBody.length, updated_at: "2026-11-06T09:30:00", kind: "markdown" },
];
const seenReportUrls = [];
const origFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const u = String(url);
  seenReportUrls.push(u);
  if (u.includes("/api/reports/") && u.endsWith("/content")) {
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
globalThis.fetch = origFetch;
console.log("  报告页 Markdown 原文 / HTML 新标签行为断言 OK");

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
console.log("  个股详情量比展示行为断言 OK");

await new Promise((r) => setTimeout(r, 120));
if (asyncFailures > 0) {
  console.error(`发现 ${asyncFailures} 个未处理的异步错误`);
  process.exit(1);
}
console.log("JS 冒烟测试通过：六个脚本顶层与关键交互行为均正常");
