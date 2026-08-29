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
<meta name="description" content="极简 · 极速 · 开箱即用的 AI Agent 启动器。一条命令装好，14 个主流 Agent 菜单自选，内置 Agnes 免费模型保底，全量离线安装，中国网络自适应。">
<style>
:root{
  --bg:#fafafa;--fg:#18181b;--muted:#71717a;--card:#ffffff;--line:#e4e4e7;
  --brand:#4f46e5;--brand2:#f97316;--code-bg:#18181b;--code-fg:#f4f4f5;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f0f11;--fg:#f4f4f5;--muted:#a1a1aa;--card:#17171a;--line:#27272a;
        --brand:#818cf8;--brand2:#fb923c;--code-bg:#000;--code-fg:#e4e4e7;}
}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
     background:var(--bg);color:var(--fg);margin:0;line-height:1.75;}
.wrap{max-width:980px;margin:0 auto;padding:0 22px}
header{padding:64px 0 30px;border-bottom:1px solid var(--line)}
h1{font-size:44px;margin:0 0 6px;letter-spacing:-.5px}
h1 .g{background:linear-gradient(90deg,var(--brand),var(--brand2));
     -webkit-background-clip:text;background-clip:text;color:transparent}
.tag{color:var(--muted);font-size:19px;margin:0 0 18px}
.badges span{display:inline-block;background:var(--card);border:1px solid var(--line);
  border-radius:99px;padding:2px 12px;font-size:13px;margin:0 6px 6px 0;color:var(--muted)}
h2{font-size:26px;margin:54px 0 14px;padding-top:14px;border-top:1px solid var(--line)}
h3{font-size:18px;margin:22px 0 8px}
.cmd{position:relative;background:var(--code-bg);color:var(--code-fg);border-radius:10px;
     padding:14px 16px;font-size:14.5px;overflow-x:auto;margin:10px 0 6px;font-family:ui-monospace,Consolas,monospace}
.cmd .c{color:#7dd3fc}
.copy{position:absolute;top:8px;right:8px;background:#3f3f46;color:#d4d4d8;border:0;
      border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer}
.copy:hover{background:#52525b}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.card b{display:block;margin-bottom:6px;font-size:15.5px}
.card p{margin:0;font-size:14px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px;margin:14px 0;background:var(--card);
      border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}
th{background:var(--card);color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}
.ok{color:#16a34a;font-weight:600}.no{color:var(--muted)}
.steps{counter-reset:s;list-style:none;padding:0;margin:16px 0}
.steps li{counter-increment:s;position:relative;padding:0 0 14px 46px}
.steps li:before{content:counter(s);position:absolute;left:0;top:0;width:30px;height:30px;
  border-radius:50%;background:var(--brand);color:#fff;display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:15px}
.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--brand2);
  border-radius:8px;padding:10px 14px;font-size:14px;color:var(--muted);margin:14px 0}
footer{border-top:1px solid var(--line);margin-top:60px;padding:26px 0 40px;
       color:var(--muted);font-size:13.5px}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
code{background:var(--card);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:.9em}
pre{background:var(--code-bg);color:var(--code-fg);border-radius:10px;padding:14px 16px;overflow-x:auto;font-size:13.5px}
@media(max-width:640px){h1{font-size:32px}.tag{font-size:16px}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1><span class="g">AgentBoot</span></h1>
  <p class="tag">极简 · 极速 · 开箱即用的 AI Agent 启动器 —— 一条命令装好，主流 Agent 菜单自选</p>
  <div class="badges">
    <span>v1.0.0</span><span>Linux · macOS · Windows</span><span>界面中文</span>
    <span>14 个 Agent 自选</span><span>离线安装</span><span>中国镜像自适应</span><span>MIT</span>
  </div>
</header>

<h2>⚡ 一键安装</h2>
<h3>Linux / macOS</h3>
<div class="cmd"><span class="c">curl -fsSL https://boot.ide.pub/install.sh | sh</span>
  <button class="copy" data-c="curl -fsSL https://boot.ide.pub/install.sh | sh">复制</button></div>
<h3>Windows（PowerShell）</h3>
<div class="cmd"><span class="c">powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))"</span>
  <button class="copy" data-c="powershell -NoProfile -ExecutionPolicy Bypass -Command &quot;iex ((New-Object Net.WebClient).DownloadString('https://boot.ide.pub/install.ps1'))&quot;">复制</button></div>
<div class="note">备用入口：GitHub Pages（<a href="https://bit-cook.github.io/AgentBoot/">bit-cook.github.io/AgentBoot</a>）/ GitHub Releases / 国内加速镜像 —— 安装脚本内自动按序多源重试。</div>

<h2>🚀 三步上手</h2>
<ol class="steps">
  <li><b>安装 AgentBoot</b><br>上面一条命令，10 秒完成；只会装 AgentBoot 本体与内置 Agent。</li>
  <li><b>打开控制台菜单</b><br><code>agentboot</code> —— 环境体检 / 自选安装 Agent / 模型配置 / 镜像代理 / 自定义离线包。</li>
  <li><b>或直接对话</b><br><code>ab</code> —— 内置保底 Agent，默认 <b>Agnes 免费模型</b>，零配置开箱即用。</li>
</ol>

<h2>✨ 特性</h2>
<div class="grid">
  <div class="card"><b>📦 菜单自选安装（不是全家桶）</b><p>14 个主流 Agent 按需勾选：Claude Code、Codex、Qwen Code、OpenCode、CodeBuddy、MiMo、Cline、Pi、CoCo…</p></div>
  <div class="card"><b>🛟 内置保底 Agent（ab）</b><p>其他都装不上时它一定能用：单文件零依赖、Agnes 免费模型、离线 Linux 知识库、会话持久化、/bench 基准。</p></div>
  <div class="card"><b>🧠 模型提供商管理器</b><p>Agnes 零配置开箱；自定义提供商命名管理；Ollama / LM Studio 本地模型；故障切换顺序。</p></div>
  <div class="card"><b>🇨🇳 中国网络自适应</b><p>自动探测并切换 npmmirror / Node 镜像 / 清华 PyPI；四源下载容错；代理一键配置。</p></div>
  <div class="card"><b>📴 全量离线 & 瘦身定制</b><p>离线包内置各平台运行时与 Agent 载荷，目标机免联网免解压软件；菜单 [7] 自选平台与 Agent 构建瘦身包。</p></div>
  <div class="card"><b>⚡ 极致性能</b><p>TLS 连接复用（实测每轮省约 440ms 首字延迟）、知识库预建索引（热查询 &lt;1ms）、上下文自动瘦身、流式中断保护。</p></div>
</div>

<h2>🤖 支持的 Agent（14 个）</h2>
<table>
<tr><th>#</th><th>Agent</th><th>命令</th><th>厂商</th><th>离线</th></tr>
<tr><td>1</td><td>CoCo Agent</td><td><code>coco</code></td><td>BitCook</td><td class="ok">Linux/macOS</td></tr>
<tr><td>2</td><td>OpenCode</td><td><code>opencode</code></td><td>opencode.ai</td><td class="ok">✓</td></tr>
<tr><td>3</td><td>Hermes Agent</td><td><code>hermes</code></td><td>Hermes</td><td class="ok">✓（需 Git）</td></tr>
<tr><td>4</td><td>Cline CLI</td><td><code>cline</code></td><td>Cline</td><td class="ok">✓</td></tr>
<tr><td>5</td><td>CodeBuddy CLI</td><td><code>codebuddy</code></td><td>Tencent</td><td class="ok">✓</td></tr>
<tr><td>6</td><td>Pi Coding Agent</td><td><code>pi</code></td><td>Earendil Works</td><td class="ok">✓</td></tr>
<tr><td>7</td><td>Claude Code</td><td><code>claude</code></td><td>Anthropic</td><td class="ok">✓</td></tr>
<tr><td>8</td><td>OpenAI Codex CLI</td><td><code>codex</code></td><td>OpenAI</td><td class="ok">✓（Agnes 预置）</td></tr>
<tr><td>9</td><td>Qwen Code</td><td><code>qwen</code></td><td>Alibaba</td><td class="ok">✓（Agnes 预置）</td></tr>
<tr><td>10</td><td>MiMo Code</td><td><code>mimo</code></td><td>Xiaomi</td><td class="ok">✓</td></tr>
<tr><td>11</td><td>OpenClaw</td><td><code>openclaw</code></td><td>OpenClaw</td><td class="ok">✓</td></tr>
<tr><td>12</td><td>Gemini CLI</td><td><code>gemini</code></td><td>Google</td><td class="ok">✓</td></tr>
<tr><td>13</td><td>iFlow CLI</td><td><code>iflow</code></td><td>iFlow 心流</td><td class="ok">✓</td></tr>
<tr><td>14</td><td>Aider</td><td><code>aider</code></td><td>Aider AI</td><td class="no">仅在线（pip）</td></tr>
</table>
<div class="note">✓ = 支持离线安装（离线包内置完整依赖与运行时）。Codex / Qwen 安装后<b>自动预置 Agnes 免费模型</b>；自定义 Agent 可通过菜单 <code>+</code> 或 <code>add-agent</code> 命令添加。</div>

<h2>📴 离线安装</h2>
<p>无网机器？两条路：</p>
<ul>
  <li><b>全量离线包</b>：Releases 下载对应平台包（约 0.8–1.6GB），拷贝解压即装，内含全部 13 个 Agent 载荷 + Node / Python 运行时；</li>
  <li><b>瘦身离线包</b>：菜单 <code>[7]</code> 或 <code>build-offline</code> 自选平台与 Agent 定制构建（如 win-x64 仅 Pi ≈ 89MB）。</li>
</ul>
<p>目标机无需联网、无需解压软件（Windows 资源管理器 / 系统自带 tar / 自解压脚本三选一），运行包内 <code>install-offline.ps1</code> 或 <code>sh install-offline.sh</code> 即可。</p>

<h2>🧠 模型：开箱即用 + 完全自定义</h2>
<ul>
  <li><b>Agnes 免费模型</b>（官方预设）：ab 零配置直接用；Codex / Qwen 安装后自动接线；</li>
  <li><b>自定义提供商</b>：任意 OpenAI 兼容接口，命名管理、随时增删切换；</li>
  <li><b>本地模型</b>：Ollama / LM Studio / vLLM 预设，完全离线场景；</li>
  <li><b>故障切换</b>：设置备用顺序，主模型失败自动降级。</li>
</ul>

<h2>📚 文档</h2>
<ul>
  <li><a href="https://github.com/${REPO}/blob/main/安装指南.md">安装指南（一键安装 / 离线部署 / 故障排查）</a></li>
  <li><a href="https://github.com/${REPO}/blob/main/README.md">README（功能总览 / 架构 / 自定义 Agent / 自定义离线包）</a></li>
  <li><a href="https://github.com/${REPO}/releases">Releases（在线包 / 三平台离线包 / 自解压包）</a></li>
</ul>

<footer>
  MIT License · <a href="https://github.com/${REPO}">github.com/${REPO}</a>
  · 主入口 <a href="https://boot.ide.pub">boot.ide.pub</a>（本页，Cloudflare）
  · 镜像 <a href="https://bit-cook.github.io/AgentBoot/">GitHub Pages</a>
  · <a href="/health">健康检查</a>
  <br>ab 内置 Agent 默认使用 Agnes 免费模型；执行命令类操作默认拦截高危行为。
</footer>
</div>
<script>
document.querySelectorAll('.copy').forEach(function(b){
  b.addEventListener('click',function(){
    navigator.clipboard.writeText(b.dataset.c).then(function(){
      var t=b.textContent;b.textContent='已复制 ✓';
      setTimeout(function(){b.textContent='复制'},1600);
    });
  });
});
</script>
</body>
</html>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
