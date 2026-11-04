/**
 * Web 前端冒烟测试：在 Node 里用最小 DOM mock 依序执行
 * app.js / p1.js / p2.js，任一脚本顶层抛错即失败。
 *
 * 背景：三个文件是经典 script，共享全局词法环境；曾因顶层 const 重名
 * 和 $() 选择器用法不一致导致整个脚本静默失效，纯接口测试发现不了。
 *
 * 运行：node scripts/js_smoke.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function makeElement(id) {
  return {
    id,
    innerHTML: "",
    textContent: "",
    className: "",
    value: "",
    checked: false,
    dataset: {},
    classList: { add() {}, remove() {}, contains: () => false },
    addEventListener() {},
    scrollIntoView() {},
    querySelector: () => makeElement(id + "::child"),
    querySelectorAll: () => [],
  };
}

const elements = new Map();
globalThis.document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  },
  querySelectorAll: () => [],
};
globalThis.window = globalThis;
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({ ok: true, data: { version: "0.0.0-smoke" } }),
});
if (!globalThis.crypto) globalThis.crypto = (await import("node:crypto")).webcrypto;

let asyncFailures = 0;
process.on("unhandledRejection", () => { asyncFailures += 1; });

for (const name of ["app.js", "p1.js", "p2.js"]) {
  const code = readFileSync(join(root, "app/web/static", name), "utf-8");
  // 三个脚本必须能在同一全局词法环境中依序执行（经典 script 语义）
  // eslint-disable-next-line no-eval
  (0, eval)(code);
  console.log(`  ${name} 顶层执行 OK`);
}

// 等待 refresh() 等异步收尾，捕获未处理的 rejection
await new Promise((r) => setTimeout(r, 120));
if (asyncFailures > 0) {
  console.error(`发现 ${asyncFailures} 个未处理的异步错误`);
  process.exit(1);
}
console.log("JS 冒烟测试通过：三个脚本顶层均无异常");
