#!/bin/sh
# AgentBoot Cloudflare Worker 一键部署脚本（Wrangler OAuth）
set -eu

cd "$(dirname "$0")"
command -v npx >/dev/null 2>&1 || { echo "需要 Node.js/npm 提供 npx" >&2; exit 1; }
python3 ../scripts/sync-web-assets.py --check
echo "==> 使用 Wrangler 部署 Worker boot …"
npx --yes wrangler deploy --config wrangler.jsonc
echo "==> 验证主入口与镜像 …"
python3 ../scripts/verify-live-release.py
echo "部署与线上验证完成。"
