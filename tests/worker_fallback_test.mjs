// Worker 双源兜底的功能测试：mock 全局 fetch，驱动 worker 的 fetch handler。
// 由 tests/test_worker_fallback.py 通过 node 调用；断言失败时以非零退出。
// 覆盖：GitHub 618 -> Pages CDN 兜底；两源全败 -> 502；Range 透传；health 同逻辑。
import { mkdtempSync, copyFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

// fileURLToPath 而不是 URL.pathname：Windows 上 pathname 是 "/C:/..."，
// 直接 join 会拼出 "C:\C:\..." 双盘符路径（ENOENT）
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "ab-worker-test-"));
copyFileSync(join(ROOT, "cloudflare/worker.js"), join(dir, "worker.mjs"));
copyFileSync(join(ROOT, "cloudflare/web-assets.js"), join(dir, "web-assets.mjs"));
writeFileSync(join(dir, "worker.mjs"),
  (await import("node:fs")).readFileSync(join(dir, "worker.mjs"), "utf8")
    .replace('"./web-assets.js"', '"./web-assets.mjs"'));

const state = { ghStatus: 206, jsdStatus: 206, calls: [] };
globalThis.fetch = async (url, opts) => {
  const u = String(url);
  state.calls.push({ url: u, range: opts?.headers?.get?.("Range") || null });
  if (u.includes("github.com/bit-cook/AgentBoot/releases")) {
    if (state.ghStatus >= 400) return new Response("gh-down", { status: state.ghStatus });
    return new Response("GH-BODY", { status: state.ghStatus, headers: { "Content-Type": "application/gzip" } });
  }
  if (u.includes("cdn.jsdelivr.net")) {
    if (state.jsdStatus >= 400) return new Response("jsd-down", { status: state.jsdStatus });
    return new Response("JSD-BODY", { status: state.jsdStatus, headers: { "Content-Type": "application/gzip" } });
  }
  if (u.includes("codeload.github.com")) {
    return new Response("CODELOAD", { status: 200 });
  }
  return new Response("other", { status: 404 });
};

const mod = await import(pathToFileURL(join(dir, "worker.mjs")).href);
const worker = mod.default;

let failures = 0;
function check(name, cond, detail = "") {
  console.log((cond ? "PASS " : "FAIL ") + name + (cond ? "" : " | " + detail));
  if (!cond) failures++;
}

async function get(path, headers = {}) {
  return worker.fetch(new Request("https://boot.ide.pub" + path, { headers }));
}

// 1) GitHub 618 -> Pages CDN 兜底
state.ghStatus = 618; state.jsdStatus = 206; state.calls = [];
let resp = await get("/rel/agentboot-online-v1.4.4.tar.gz", { Range: "bytes=0-0" });
check("rel: GH 618 时兜底 jsDelivr", resp.status === 206, "status=" + resp.status);
check("rel: 兜底返回 jsDelivr 内容", (await resp.text()) === "JSD-BODY");
check("rel: Range 透传给上游", state.calls.some(c => c.range === "bytes=0-0"),
  JSON.stringify(state.calls));
check("rel: 先试 Release 再试 jsDelivr",
  state.calls[0].url.includes("/releases/") && state.calls[1].url.includes("jsdelivr"),
  JSON.stringify(state.calls.map(c => c.url)));

// 2) 两源全败 -> 502 且消息带状态码
state.ghStatus = 618; state.jsdStatus = 404; state.calls = [];
resp = await get("/rel/agentboot-online-v1.4.4.zip");
const body = await resp.text();
check("rel: 两源全败返回 502", resp.status === 502, "status=" + resp.status);
check("rel: 502 消息含最后状态码", body.includes("404"), body.slice(0, 80));

// 3) GitHub 正常时不再打扰 jsDelivr
state.ghStatus = 206; state.jsdStatus = 206; state.calls = [];
resp = await get("/rel/install.sh");
check("rel: GH 正常时直取", resp.status === 206 && (await resp.text()) === "GH-BODY");
check("rel: GH 正常时不调 jsDelivr", !state.calls.some(c => c.url.includes("jsdelivr")));

// 4) /install.sh 入口同样双源
state.ghStatus = 618; state.jsdStatus = 206; state.calls = [];
resp = await get("/install.sh");
check("install.sh: 双源兜底", resp.status === 206 && (await resp.text()) === "JSD-BODY");

// 5) health：GH 挂 -> jsDelivr 顶上 -> ok
state.ghStatus = 618; state.jsdStatus = 206; state.calls = [];
resp = await get("/health");
const health = await resp.json();
check("health: GH 618 时仍 ok", health.ok === true && resp.status === 200,
  JSON.stringify(health.assets));
check("health: 每个资产都探测过两个源",
  state.calls.filter(c => c.url.includes("jsdelivr")).length >= 5,
  "jsd calls=" + state.calls.filter(c => c.url.includes("jsdelivr")).length);

// 6) health：两源全挂 -> 503 + ok:false
state.ghStatus = 618; state.jsdStatus = 404; state.calls = [];
resp = await get("/health");
check("health: 两源全挂返回 503", resp.status === 503 && (await resp.json()).ok === false);

// 7) codeload 路径不受影响
state.ghStatus = 206; state.jsdStatus = 206; state.calls = [];
resp = await get("/gh/main.tar.gz", { Range: "bytes=0-0" });
check("gh/main.tar.gz: 仍走 codeload", resp.status === 200 &&
  state.calls.some(c => c.url.includes("codeload.github.com")));

// 8) 坏资产名仍 400
resp = await get("/rel/bad%20name");
check("rel: 非法资产名 400", resp.status === 400);

rmSync(dir, { recursive: true, force: true });
console.log(failures === 0 ? "WORKER-FALLBACK-ALL-PASS" : "WORKER-FALLBACK-FAILED=" + failures);
process.exit(failures === 0 ? 0 : 1);
