#!/bin/bash
# v1.7.4 发布监视器：轮询流水线 → 完成后 promote latest → 复验健康与四源
TOKEN=$(grep -oP 'ghp_[A-Za-z0-9]+' /root/.git-credentials | head -1)
RID=$(curl -s "https://api.github.com/repos/bit-cook/AgentBoot/actions/runs?per_page=3" | python3 -c "
import json,sys
for r in json.load(sys.stdin)['workflow_runs']:
    if r['head_branch']=='v1.7.4': print(r['id']); break
")
echo "WATCH run=$RID"
for i in $(seq 1 60); do
  S=$(curl -s "https://api.github.com/repos/bit-cook/AgentBoot/actions/runs/$RID" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['conclusion'] or '-')")
  echo "[$i] $S"
  case "$S" in
    completed/success) echo "PIPELINE_OK"; break;;
    completed/*) echo "PIPELINE_FAILED: $S"; exit 1;;
  esac
  sleep 30
done
echo "=== promote latest ==="
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/bit-cook/AgentBoot/releases/tags/v1.7.4" \
  -d '{"prerelease":false,"make_latest":true}' | python3 -c "import json,sys; d=json.load(sys.stdin); print('tag:', d.get('tag_name'), '| latest:', d.get('make_latest'), '| assets:', len(d.get('assets',[])))"
echo "=== 复验四源 TAG ==="
for u in "https://boot.ide.pub/install.sh" "https://bit-cook.github.io/AgentBoot/install.sh" "https://cdn.jsdelivr.net/gh/bit-cook/AgentBoot@gh-pages/install.sh"; do
  T=$(curl -fsSL "$u" 2>/dev/null | grep -m1 'TAG=' | cut -d'"' -f2)
  echo " $u → $T"
done
curl -s https://boot.ide.pub/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('health:', d['tag'], '| ok:', d['ok'])"
echo "DONE: v1.7.4 发布链完成"
