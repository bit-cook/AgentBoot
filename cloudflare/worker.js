/**
 * AgentBoot distribution Worker.
 * Pages are generated from pages/ by scripts/sync-web-assets.py.
 */

import { WEB_ASSETS } from "./web-assets.js";

const REPO = "bit-cook/AgentBoot";
const TAG = "v1.7.1";
const GH_REL = `https://github.com/${REPO}/releases/download/${TAG}`;
// 在线包/安装器在 Pages CDN（jsDelivr 镜像 gh-pages 分支）有同一份。
// GitHub Release CDN 对 Cloudflare Worker 间歇返回 618（直连却正常），
// 因此 Release 为主、Pages CDN 兜底；两源都不可用才报错。
const PAGES_CDN = `https://cdn.jsdelivr.net/gh/${REPO}@gh-pages`;
const UA = "AgentBoot-Worker/1.2";
const PROBE_HEADERS = { "User-Agent": UA, "Range": "bytes=0-0" };
const ASSET_CACHE = "public, max-age=31536000, immutable";
const PAGE_CACHE = "public, max-age=300, stale-while-revalidate=3600";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (path === "/health") {
      const required = ["install.sh", `agentboot-online-${TAG}.tar.gz`,
        `agentboot-online-${TAG}.tar.gz.sha256`, `agentboot-online-${TAG}.zip`,
        `agentboot-online-${TAG}.zip.sha256`];
      const assets = {};
      // 与 /rel/ 同一套取源逻辑：GitHub Release CDN 对 Worker 间歇返回 618，
      // Pages CDN（jsDelivr 镜像 gh-pages）有同一份在线资产，作为兜底
      await Promise.all(required.map(async (name) => {
        const hit = await fetchAsset(name, PROBE_HEADERS);
        assets[name] = hit.resp ? hit.resp.status : hit.status;
      }));
      const ok = required.every((name) => assets[name] >= 200 && assets[name] < 400);
      return json({ ok, repo: REPO, tag: TAG, assets, time: new Date().toISOString() }, ok ? 200 : 503);
    }
    if (path === "/install.sh") {
      return proxyRelease("install.sh", "text/x-shellscript; charset=utf-8", 300);
    }
    if (path === "/install.ps1") {
      return proxyRelease("install.ps1", "text/plain; charset=utf-8", 300);
    }
    if (path.startsWith("/rel/")) {
      const name = decodeURIComponent(path.slice("/rel/".length));
      if (!/^[\w.-]+$/.test(name)) return text("bad asset name", 400);
      return proxyRelease(name, null, 21600, request);
    }
    if (path === "/gh/main.tar.gz" || path === "/gh/main.zip") {
      const ext = path.endsWith(".zip") ? "zip" : "tar.gz";
      const target = ext === "zip"
        ? `https://codeload.github.com/${REPO}/zip/refs/heads/main`
        : `https://codeload.github.com/${REPO}/tar.gz/refs/heads/main`;
      return proxy(target, ext === "zip" ? "application/zip" : "application/x-gzip", 300);
    }
    if (/^\/(agentboot|AgentBoot)(\/|$)/.test(path)) {
      const sub = path.replace(/^\/(agentboot|AgentBoot)/, "");
      const target = sub === "/en" || sub.startsWith("/en/") ? "/en" : "/";
      return Response.redirect(new URL(target, request.url).toString(), 301);
    }
    if (path === "/") return webResponse(request, "/index.html", PAGE_CACHE);
    if (path === "/en") return webResponse(request, "/en/index.html", PAGE_CACHE);
    if (path.startsWith("/assets/") && WEB_ASSETS[path]) {
      return webResponse(request, path, ASSET_CACHE);
    }
    return webResponse(request, "/404.html", "no-store", 404);
  },
};

async function proxy(target, contentType, cacheTtl, incoming = null) {
  const requestHeaders = new Headers({ "User-Agent": UA });
  if (incoming) {
    for (const name of ["Range", "If-Range", "If-None-Match", "If-Modified-Since"]) {
      const value = incoming.headers.get(name);
      if (value) requestHeaders.set(name, value);
    }
  }
  const resp = await fetch(target, {
    cf: { cacheEverything: !requestHeaders.has("Range"), cacheTtl },
    headers: requestHeaders,
  });
  if (!resp.ok && resp.status !== 304) {
    return text(`上游不可用（${resp.status}）：${target}\n请稍后重试或使用 GitHub 直链。\n`, 502);
  }
  const headers = new Headers(resp.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("X-AgentBoot-Proxy", target);
  return new Response(resp.body, { status: resp.status, headers });
}

/**
 * 取发布资产：先 GitHub Release，失败再试 Pages CDN（jsDelivr 镜像 gh-pages）。
 * 返回 { resp, status }：resp 非空即取到；否则 status 是最后一个个源状态码。
 */
async function fetchAsset(name, probeHeaders = null, incoming = null) {
  const headers = new Headers(probeHeaders || { "User-Agent": UA });
  if (incoming) {
    for (const n of ["Range", "If-Range", "If-None-Match", "If-Modified-Since"]) {
      const value = incoming.headers.get(n);
      if (value) headers.set(n, value);
    }
  }
  let status = 0;
  for (const base of [GH_REL, PAGES_CDN]) {
    try {
      const resp = await fetch(`${base}/${name}`, {
        cf: { cacheEverything: !headers.has("Range"), cacheTtl: 21600 },
        headers,
      });
      if (resp.ok || resp.status === 304) return { resp, status: resp.status };
      status = resp.status;
    } catch (_) { /* 换下一个源 */ }
  }
  return { resp: null, status };
}

/** /rel/ 与安装器入口：经 fetchAsset 双源取资产后代理给客户端。 */
async function proxyRelease(name, contentType, cacheTtl, incoming = null) {
  const hit = await fetchAsset(name, null, incoming);
  if (!hit.resp) {
    return text(`上游不可用（${hit.status}）：${name}\n请稍后重试或使用 GitHub 直链。\n`, 502);
  }
  const headers = new Headers(hit.resp.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("X-AgentBoot-Proxy", hit.resp.url || name);
  return new Response(hit.resp.body, { status: hit.resp.status, headers });
}

function webResponse(request, route, cacheControl, status = 200) {
  const asset = WEB_ASSETS[route];
  if (request.headers.get("If-None-Match") === asset.etag) {
    return new Response(null, { status: 304, headers: webHeaders(asset, cacheControl) });
  }
  let body = asset.body;
  if (asset.b64) {
    const bin = atob(body);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    body = bytes;
  }
  return new Response(request.method === "HEAD" ? null : body, {
    status,
    headers: webHeaders(asset, cacheControl),
  });
}

function webHeaders(asset, cacheControl) {
  return {
    "Cache-Control": cacheControl,
    "Content-Type": asset.type,
    "ETag": asset.etag,
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
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
