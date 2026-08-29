#!/bin/sh
# AgentBoot Cloudflare Worker 一键部署脚本（API 方式）
# 用法：
#   export CF_EMAIL=... CF_KEY=... CF_ACCOUNT_ID=... CF_ZONE_ID=...
#   sh deploy.sh
set -eu

cd "$(dirname "$0")"
: "${CF_EMAIL:?请设置 CF_EMAIL}"
: "${CF_KEY:?请设置 CF_KEY（Global API Key）}"
: "${CF_ACCOUNT_ID:?请设置 CF_ACCOUNT_ID}"
: "${CF_ZONE_ID:?请设置 CF_ZONE_ID（ide.pub）}"

API="https://api.cloudflare.com/client/v4"
H1="X-Auth-Email: $CF_EMAIL"
H2="X-Auth-Key: $CF_KEY"

echo "==> 上传 Worker boot …"
curl -sS -X PUT "$API/accounts/$CF_ACCOUNT_ID/workers/scripts/boot" \
    -H "$H1" -H "$H2" \
    -F 'metadata={"main_module":"worker.js","compatibility_date":"2024-09-23"};type=application/json' \
    -F 'worker.js=@worker.js;type=application/javascript+module' | head -c 400; echo

echo "==> 启用 workers.dev 预览 …"
curl -sS -X POST "$API/accounts/$CF_ACCOUNT_ID/workers/scripts/boot/subdomain" \
    -H "$H1" -H "$H2" -H "Content-Type: application/json" \
    -d '{"enabled":true}' | head -c 300; echo

echo "==> 创建 DNS 记录 boot（若已存在会报 already exist，可忽略）…"
curl -sS -X POST "$API/zones/$CF_ZONE_ID/dns_records" \
    -H "$H1" -H "$H2" -H "Content-Type: application/json" \
    -d '{"type":"AAAA","name":"boot","content":"100::","proxied":true}' | head -c 300; echo

echo "==> 创建路由 boot.ide.pub/* → boot …"
curl -sS -X POST "$API/zones/$CF_ZONE_ID/workers/routes" \
    -H "$H1" -H "$H2" -H "Content-Type: application/json" \
    -d '{"pattern":"boot.ide.pub/*","script":"boot"}' | head -c 300; echo

echo "==> 验证 …"
curl -fsSL https://boot.ide.pub/health || echo "（DNS 生效可能需要 1-2 分钟）"
echo "部署脚本执行完毕。"
