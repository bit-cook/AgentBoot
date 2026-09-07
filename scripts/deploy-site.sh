#!/bin/sh
# 将 pages/ 最新内容同步到个人站仓库（osome.work/AgentBoot/ 的实际服务源）。
# 前置：本机 git 凭据可推送 bit-cook/bit-cook.github.io；USERSITE_DIR 指向其本地克隆。
# 用法：sh scripts/deploy-site.sh [USERSITE_DIR]   （缺省为 ../bit-cook.github.io）
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SITE_DIR="${1:-$ROOT/../bit-cook.github.io}"

if [ ! -d "$SITE_DIR/.git" ]; then
  echo "未找到个人站仓库：$SITE_DIR" >&2
  echo "先克隆：git clone https://github.com/bit-cook/bit-cook.github.io.git" >&2
  exit 1
fi

echo "==> 同步 pages/ -> $SITE_DIR/AgentBoot/"
TARGET="$SITE_DIR/AgentBoot"
mkdir -p "$TARGET"
find "$TARGET" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -R pages/. "$TARGET/"

cd "$SITE_DIR"
git add -A
if git diff --cached --quiet; then
  echo "==> 内容无变化，无需部署"
  exit 0
fi
git commit -m "AgentBoot: 同步站点内容 $(date +%F)"
git push origin master
echo "==> 已推送，self-hosted runner 将在约 1 分钟内完成发布"
