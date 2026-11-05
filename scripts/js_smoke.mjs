/**
 * Web 前端冒烟测试：在 Node 里用最小 DOM mock 依序执行
 * app.js / ux.js / p1.js / p2.js / detail.js / scan.js，任一脚本顶层抛错即失败。
 *
 * 背景：这些文件是经典 script，共享全局词法环境；曾因顶层 const 重名
 * 和 $() 选择器用法不一致导致整个脚本静默失效，纯接口测试发现不了。
 * 这里把四个脚本拼进同一次 eval，以复现「顶层 let/const 跨文件共享」。
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
    querySelector: () => null,
    querySelectorAll: () => [],
    classList: { add() {}, remove() {} },
  };
}

function makeElement(id) {
  return {
    id, tagName: "DIV", innerHTML: "", textContent: "", className: "",
    value: "", checked: false, type: "", title: "", placeholder: "",
    disabled: false, href: "", download: "", hidden: false,
    dataset: {}, style: {}, children: [], parentNode: makeParent(),
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {}, removeEventListener() {},
    appendChild(child) { this.children.push(child); child.parentNode = this; return child; },
    insertBefore(child) { this.children.push(child); child.parentNode = this; return child; },
    replaceChildren(...nodes) { this.children = nodes; },
    querySelector: (sel) => makeElement(id + "::" + sel),
    querySelectorAll: () => [],
    remove() {}, focus() {}, click() {}, scrollIntoView() {},
    dispatchEvent() {}, closest: () => null,
  };
}

const elements = new Map();
globalThis.document = {
  hidden: false,
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  },
  createElement: (tag) => makeElement("created::" + tag),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
};
globalThis.window = globalThis;
globalThis.location = { hash: "", pathname: "/" };
globalThis.history = { replaceState() {} };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
if (!globalThis.Event) {
  globalThis.Event = class {
    constructor(type, opts) { this.type = type; Object.assign(this, opts || {}); }
  };
}
globalThis.setInterval = () => 0;      // 不真的起定时器，避免测试进程不退出
globalThis.clearInterval = () => {};
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({ ok: true, data: { version: "0.0.0-smoke" } }),
});
if (!globalThis.crypto) globalThis.crypto = (await import("node:crypto")).webcrypto;

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

/* 缓存策略行为断言：轮询 / 状态 / 配置类接口绝不能进慢任务缓存，
   否则训练轮询每 1.5s 都会命中缓存并弹提示，状态也永远停在 running。 */
const policy = globalThis.ST && globalThis.ST.cachePolicy;
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
if (typeof globalThis.ST.invalidate !== "function") {
  throw new Error("ux.js 缺少 ST.invalidate（训练完成后需失效预测缓存）");
}
console.log("  缓存白名单 / 失效接口行为断言 OK");

await new Promise((r) => setTimeout(r, 120));
if (asyncFailures > 0) {
  console.error(`发现 ${asyncFailures} 个未处理的异步错误`);
  process.exit(1);
}
console.log("JS 冒烟测试通过：六个脚本顶层均无异常");
