/**
 * AgentBoot distribution Worker.
 * Pages are generated from pages/ by scripts/sync-web-assets.py.
 */

import { WEB_ASSETS } from "./web-assets.js";

const REPO = "bit-cook/AgentBoot";
const TAG = "v1.1.0";
const GH_REL = `https://github.com/${REPO}/releases/download/${TAG}`;
const ASSET_CACHE = "public, max-age=86400, stale-while-revalidate=604800";
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
      await Promise.all(required.map(async (name) => {
        try {
          const response = await fetch(`${GH_REL}/${name}`, {
            method: "HEAD", headers: { "User-Agent": "AgentBoot-Worker/1.1" },
            cf: { cacheEverything: false },
          });
          assets[name] = response.status;
        } catch (_) { assets[name] = 0; }
      }));
      const ok = required.every((name) => assets[name] >= 200 && assets[name] < 400);
      return json({ ok, repo: REPO, tag: TAG, assets, time: new Date().toISOString() }, ok ? 200 : 503);
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
      return proxy(`${GH_REL}/${name}`, null, 21600, request);
    }
    if (path === "/gh/main.tar.gz" || path === "/gh/main.zip") {
      const ext = path.endsWith(".zip") ? "zip" : "tar.gz";
      const target = ext === "zip"
        ? `https://codeload.github.com/${REPO}/zip/refs/heads/main`
        : `https://codeload.github.com/${REPO}/tar.gz/refs/heads/main`;
      return proxy(target, ext === "zip" ? "application/zip" : "application/x-gzip", 300);
    }
    if (path === "/") return webResponse(request, "/index.html", PAGE_CACHE);
    if (path === "/en") return webResponse(request, "/en/index.html", PAGE_CACHE);
    if (path === "/assets/site.css" || path === "/assets/site.js" || path === "/assets/favicon.svg") {
      return webResponse(request, path, ASSET_CACHE);
    }
    return webResponse(request, "/404.html", "no-store", 404);
  },
};

async function proxy(target, contentType, cacheTtl, incoming = null) {
  const requestHeaders = new Headers({ "User-Agent": "AgentBoot-Worker/1.1" });
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

function webResponse(request, route, cacheControl, status = 200) {
  const asset = WEB_ASSETS[route];
  if (request.headers.get("If-None-Match") === asset.etag) {
    return new Response(null, { status: 304, headers: webHeaders(asset, cacheControl) });
  }
  return new Response(request.method === "HEAD" ? null : asset.body, {
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
