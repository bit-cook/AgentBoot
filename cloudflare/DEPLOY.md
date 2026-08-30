# Cloudflare 部署说明（AgentBoot 分发 Worker）

本目录的 `worker.js` 承担 `https://boot.ide.pub` 的安装脚本分发：

```
curl -fsSL https://boot.ide.pub/install.sh | sh
```

Worker 名称固定为 **boot**（对应"域名前缀用 boot"的要求）。`*.workers.dev`
在中国大陆通常被阻断，因此同时把自定义域 `boot.ide.pub` 绑定到该 Worker。

## 手动部署（Cloudflare 控制台）

1. Workers & Pages → Create Worker → 名称填 `boot` → 粘贴 `worker.js` → Deploy。
2. Worker 详情 → Settings → Domains & Routes → Add → Custom domain → `boot.ide.pub`
   （Cloudflare 会自动创建 DNS 记录与路由）。

## 脚本部署（Cloudflare API，无需 wrangler）

先准备环境变量（全局 API Key 在 Cloudflare 控制台 My Profile → API Tokens 页获取）：

```sh
export CF_EMAIL="你的账号邮箱"
export CF_KEY="你的 Global API Key"
export CF_ACCOUNT_ID="账户 ID（域名为 ide.pub 的那个账户）"
export CF_ZONE_ID="ide.pub 这个 zone 的 ID"
```

然后：

```sh
# 1) 部署/更新 Worker（模块语法上传）
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/boot" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_KEY" \
  -F 'metadata={"main_module":"worker.js","compatibility_date":"2024-09-23"};type=application/json' \
  -F 'worker.js=@worker.js;type=application/javascript+module'

# 2) 启用 workers.dev 预览地址（可选）
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/boot/subdomain" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_KEY" \
  -H "Content-Type: application/json" -d '{"enabled":true}'

# 3) DNS：创建 boot 子域（AAAA 100:: + 代理，把流量交给 Cloudflare）
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_KEY" \
  -H "Content-Type: application/json" \
  -d '{"type":"AAAA","name":"boot","content":"100::","proxied":true}'

# 4) 路由：boot.ide.pub/* 全部交给 Worker boot 处理
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/workers/routes" \
  -H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pattern":"boot.ide.pub/*","script":"boot"}'
```

## 验证

```sh
curl -fsSL https://boot.ide.pub/health
curl -fsSL https://boot.ide.pub/install.sh | head -n 5
```

## 版本升级

`worker.js` 顶部的 `REPO` / `TAG` 与各安装脚本中的 `TAG` 保持一致；发新版本时同步修改。

当前推荐使用已登录的 Wrangler OAuth 会话部署，配置位于 `wrangler.jsonc`：

```sh
cd cloudflare
npx wrangler deploy --config wrangler.jsonc
python3 ../scripts/verify-live-release.py
```

`verify-live-release.py` 会同时检查 `boot.ide.pub` 与 GitHub Pages：版本、安装器、在线 tar/zip 及 SHA-256 必须一致。
