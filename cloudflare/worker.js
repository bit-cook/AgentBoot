/**
 * AgentBoot 分发 Worker（Cloudflare Workers 免费版）
 * =================================================
 * 绑定：Workers 名称为 boot；自定义域 boot.ide.pub（路由 boot.ide.pub/*）
 * 端点：
 *   GET /                      中文说明页
 *   GET /install.sh            → 转发 GitHub Release 的 install.sh（curl|sh 入口）
 *   GET /install.ps1           → 转发 GitHub Release 的 install.ps1
 *   GET /rel/<文件名>          → 转发 GitHub Release 资产（在线/离线安装包）
 *   GET /gh/main.tar.gz        → 转发 codeload 主分支源码包
 *   GET /health                → 健康检查
 * 说明：*.workers.dev 在中国大陆通常不可直接访问，生产入口请使用
 *       绑定的自定义域 boot.ide.pub（Cloudflare 任播网络）。
 */

const REPO = "bit-cook/AgentBoot";
const TAG = "v1.0.0";
const GH_REL = `https://github.com/${REPO}/releases/download/${TAG}`;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (path === "/health") {
      return json({ ok: true, repo: REPO, tag: TAG, time: new Date().toISOString() });
    }
    if (path === "/install.sh") {
      return proxy(`${GH_REL}/install.sh`, "text/x-shellscript; charset=utf-8", 300);
    }
    if (path === "/install.ps1") {
      return proxy(`${GH_REL}/install.ps1`, "text/plain; charset=utf-8", 300);
    }
    if (path.startsWith("/rel/")) {
      const name = decodeURIComponent(path.slice("/rel/".length));
      if (!/^[\w.-]+$/.test(name)) return text("bad asset name", 400);
      return proxy(`${GH_REL}/${name}`, null, 21600);
    }
    if (path === "/gh/main.tar.gz" || path === "/gh/main.zip") {
      const ext = path.endsWith(".zip") ? "zip" : "tar.gz";
      const target = ext === "zip"
        ? `https://codeload.github.com/${REPO}/zip/refs/heads/main`
        : `https://codeload.github.com/${REPO}/tar.gz/refs/heads/main`;
      return proxy(target, ext === "zip" ? "application/zip" : "application/x-gzip", 300);
    }
    if (path === "/") return page();

    return text("AgentBoot Worker · 404 Not Found\n试：/install.sh 或 /rel/<release资产名>\n", 404);
  },
};

async function proxy(target, contentType, cacheTtl) {
  const resp = await fetch(target, {
    cf: { cacheEverything: true, cacheTtl },
    headers: { "User-Agent": "AgentBoot-Worker/1.0" },
  });
  if (!resp.ok) {
    return text(`上游不可用（${resp.status}）：${target}\n请稍后重试或使用 GitHub 直链。\n`, 502);
  }
  const headers = new Headers(resp.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("X-AgentBoot-Proxy", target);
  return new Response(resp.body, { status: resp.status, headers });
}

function text(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Access-Control-Allow-Origin": "*" },
  });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj, null, 2), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" },
  });
}

function page() {
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentBoot · 一键安装 AI Agent 启动器</title>
<style>
  body{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
       max-width:820px;margin:40px auto;padding:0 20px;line-height:1.7;color:#222}
  code,pre{background:#f4f4f5;border-radius:6px;font-size:14px}
  pre{padding:14px;overflow-x:auto;border:1px solid #e4e4e7}
  h1{border-bottom:2px solid #111;padding-bottom:8px}
  .tip{background:#fffbeb;border:1px solid #fde68a;padding:10px 14px;border-radius:6px}
  a{color:#0969da}
</style>
</head>
<body>
<h1>AgentBoot</h1>
<p>极简 · 极速 · 开箱即用的 AI Agent 启动器（Linux / macOS / Windows）。内置最小 Agent（默认 Agnes 免费模型），可从菜单一键安装 Claude Code、Codex、Qwen Code、OpenCode、CodeBuddy、MiMo Code、Cline、Hermes Agent、OpenClaw、Pi 等。</p>

<h2>一键在线安装</h2>
<h3>Linux / macOS</h3>
<pre>curl -fsSL https://boot.ide.pub/install.sh | sh
# 备用入口（GitHub Pages）：
curl -fsSL https://bit-cook.github.io/AgentBoot/install.sh | sh</pre>
<h3>Windows（PowerShell）</h3>
<pre>powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"</pre>

<h2>安装后</h2>
<pre>agentboot   # 控制台菜单（安装其他 Agent / 模型配置 / 镜像代理）
ab          # 内置最小 Agent（默认 Agnes 免费模型，开箱即用）</pre>

<h2>离线安装</h2>
<p>到 GitHub Releases 下载 <code>AgentBoot-offline-*.zip / .tar.gz / *-sfx.sh</code>，
拷到无网机器解压后运行 <code>install-offline.ps1</code>（Windows）或
<code>sh install-offline.sh</code>（Linux/macOS）。详见项目《安装指南.md》。</p>

<p class="tip">中国大陆网络环境会自动切换 npm/Node 镜像源；如需代理，菜单 [5] 可配置。
<a href="https://github.com/${REPO}">GitHub 仓库</a> ·
<a href="/health">健康检查</a></p>
</body>
</html>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
