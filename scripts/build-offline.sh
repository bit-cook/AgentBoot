#!/bin/sh
# =============================================================
#  AgentBoot 离线安装包构建脚本（Linux / macOS 构建机）
#  产物（dist/）：
#    AgentBoot-offline-vX.Y.Z.tar.gz / .zip   —— 全平台离线包
#    AgentBoot-offline-vX.Y.Z-sfx.sh          —— POSIX 自解压安装器
#  依赖：node+npm（或允许脚本自动下载便携 Node）、tar、curl、python3（可选，打 zip/sfx 用）
#  用法：
#    sh scripts/build-offline.sh
#    AGENTS="claude-code,codex" PLATFORMS="linux-x64,win-x64" sh scripts/build-offline.sh
# =============================================================
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${TAG:-v1.0.0}"
NODE_VERSION="${NODE_VERSION:-v22.14.0}"
PLATFORMS="${PLATFORMS:-linux-x64,win-x64,darwin-arm64}"
AGENTS_ENV="${AGENTS:-}"
NPM_MIRROR="https://registry.npmmirror.com"
DIST="$ROOT/dist"
STAGE="$DIST/offline/AgentBoot"

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
err()  { printf '✗ %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

step "AgentBoot 离线包构建 $TAG · 平台：$PLATFORMS"

# ---------- 0. 确保 npm ----------
if ! command -v npm >/dev/null 2>&1; then
    step "npm 不可用，下载便携 Node …"
    mkdir -p "$DIST/build-node"
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm*) NF="node-$NODE_VERSION-darwin-arm64.tar.gz" ;;
        Darwin-*)    NF="node-$NODE_VERSION-darwin-x64.tar.gz" ;;
        Linux-aarch*|Linux-arm64) NF="node-$NODE_VERSION-linux-arm64.tar.gz" ;;
        *)           NF="node-$NODE_VERSION-linux-x64.tar.gz" ;;
    esac
    curl -fL -o "$DIST/$NF" "https://registry.npmmirror.com/-/binary/node/$NODE_VERSION/$NF"
    tar -xzf "$DIST/$NF" -C "$DIST/build-node"
    NODE_HOME="$DIST/build-node/node-$NODE_VERSION-${NF#node-$NODE_VERSION-}"
    NODE_HOME="${NODE_HOME%.tar.gz}"
    export PATH="$NODE_HOME/bin:$PATH"
fi
ok "npm：$(command -v npm)"

# ---------- 1. 复制项目 ----------
step '复制项目文件 …'
rm -rf "$STAGE"
mkdir -p "$STAGE"
(cd "$ROOT" && tar -cf - \
    --exclude='./.git' --exclude='./dist' --exclude='./payloads' \
    --exclude='./node_modules' --exclude='./__pycache__' --exclude='*.pyc' \
    .) | tar -xf - -C "$STAGE"

# ---------- 2. 各平台 Node 运行时 ----------
mkdir -p "$STAGE/payloads/node"
for PLAT in $(echo "$PLATFORMS" | tr ',' ' '); do
    step "Node 运行时 [$PLAT] …"
    case "$PLAT" in
        win-x64)      NF="node-$NODE_VERSION-win-x64.zip";      INNER="node-$NODE_VERSION-win-x64" ;;
        linux-x64)    NF="node-$NODE_VERSION-linux-x64.tar.gz";  INNER="node-$NODE_VERSION-linux-x64" ;;
        linux-arm64)  NF="node-$NODE_VERSION-linux-arm64.tar.gz"; INNER="node-$NODE_VERSION-linux-arm64" ;;
        darwin-x64)   NF="node-$NODE_VERSION-darwin-x64.tar.gz"; INNER="node-$NODE_VERSION-darwin-x64" ;;
        darwin-arm64) NF="node-$NODE_VERSION-darwin-arm64.tar.gz"; INNER="node-$NODE_VERSION-darwin-arm64" ;;
        *) err "未知平台：$PLAT"; exit 1 ;;
    esac
    ARC="$DIST/$NF"
    [ -f "$ARC" ] || curl -fL -o "$ARC" "https://registry.npmmirror.com/-/binary/node/$NODE_VERSION/$NF" \
        || curl -fL -o "$ARC" "https://nodejs.org/dist/$NODE_VERSION/$NF"
    rm -rf "$DIST/x"
    mkdir -p "$DIST/x"
    tar -xf "$ARC" -C "$DIST/x"
    mkdir -p "$STAGE/payloads/node/$PLAT"
    cp -R "$DIST/x/$INNER/." "$STAGE/payloads/node/$PLAT/"
    chmod +x "$STAGE/payloads/node/$PLAT/bin/"* 2>/dev/null || true
    ok "Node [$PLAT] 就绪"
done

# ---------- 3. Agent 载荷（npm --os/--cpu 跨平台拉取） ----------
if [ -n "$AGENTS_ENV" ]; then
    WANT="$(echo "$AGENTS_ENV" | tr ',' ' ')"
else
    WANT="$(python3 -c "import json,sys;print(' '.join(a['id'] for a in json.load(open(sys.argv[1]))['agents'] if a.get('offline')))" "$ROOT/agents/registry.json" 2>/dev/null || true)"
fi
step "Agent 载荷：$WANT"
for AID in $WANT; do
    PKG="$(python3 - "$AID" <<'PYEOF'
import json,sys
rid=sys.argv[1]
for a in json.load(open('agents/registry.json'))['agents']:
    if a['id']==rid:
        print(a.get('npm') or '')
        break
PYEOF
)"
    [ -n "$PKG" ] || { err "注册表中无 Agent：$AID"; continue; }
    for PLAT in $(echo "$PLATFORMS" | tr ',' ' '); do
        case "$PLAT" in
            win-x64)      OSV=win32;  CPUV=x64 ;;
            linux-x64)    OSV=linux;  CPUV=x64 ;;
            linux-arm64)  OSV=linux;  CPUV=arm64 ;;
            darwin-x64)   OSV=darwin; CPUV=x64 ;;
            darwin-arm64) OSV=darwin; CPUV=arm64 ;;
        esac
        step "载荷 $AID [$PLAT] ← $PKG"
        PREFIX="$STAGE/payloads/agents/$AID/$PLAT"
        mkdir -p "$PREFIX"
        if npm install --global-style --prefix "$PREFIX" --os "$OSV" --cpu "$CPUV" \
               "$PKG" --registry "$NPM_MIRROR" --no-audit --no-fund --loglevel=error; then
            ok "$AID [$PLAT] 完成"
        else
            err "载荷安装失败：$AID@$PLAT（继续其他载荷）"
        fi
    done
done

# ---------- 4. 内置 Python（Windows 便携版） ----------
step '内置 Python（win-embed）…'
mkdir -p "$STAGE/payloads/python"
[ -f "$STAGE/payloads/python/win-embed.zip" ] || \
    curl -fL -o "$STAGE/payloads/python/win-embed.zip" \
        "https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip" \
    || curl -fL -o "$STAGE/payloads/python/win-embed.zip" \
        "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
ok 'win-embed.zip 就绪'

# ---------- 5. 离线安装脚本 + 清单 ----------
cp "$ROOT/scripts/install-offline.sh" "$STAGE/"
cp "$ROOT/scripts/install-offline.ps1" "$STAGE/"
{
    echo "AgentBoot Offline Bundle"
    echo "version   : $TAG"
    echo "built     : $(date '+%Y-%m-%d %H:%M')"
    echo "node      : $NODE_VERSION"
    echo "platforms : $PLATFORMS"
    echo "agents    : $(echo $WANT | tr ' ' ',')"
    echo "python    : 3.12.10 embed (windows)"
    echo
    echo "用法见《安装指南.md》：解压后运行 install-offline.sh / install-offline.ps1"
} > "$STAGE/MANIFEST.txt"

# ---------- 6. 打包 ----------
step '打包 tar.gz / zip …'
mkdir -p "$DIST"
tar -czf "$DIST/AgentBoot-offline-$TAG.tar.gz" -C "$DIST/offline" AgentBoot
if command -v python3 >/dev/null 2>&1; then
    python3 -c "import shutil,sys;shutil.make_archive(sys.argv[1],'zip',root_dir=sys.argv[2],base_dir=sys.argv[3])" \
        "$DIST/AgentBoot-offline-$TAG" "$DIST/offline" AgentBoot
fi
ls -lh "$DIST" | grep AgentBoot-offline || true

# ---------- 7. POSIX 自解压安装器 ----------
if command -v python3 >/dev/null 2>&1; then
    step '生成自解压安装器（sfx.sh）…'
    SFX="$DIST/AgentBoot-offline-$TAG-sfx.sh"
    cat > "$SFX" <<'HF'
#!/bin/sh
# AgentBoot 离线自解压安装器：目标机器无需任何解压软件，直接运行
#   sh AgentBoot-offline-vX.Y.Z-sfx.sh
set -eu
SKIP=$(awk '/^__AGENTBOOT_PAYLOAD_BELOW__$/{print NR+1; exit}' "$0")
tmp="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-sfx-$$)"
mkdir -p "$tmp"
echo "==> AgentBoot 离线自解压安装：解压中，请稍候 …"
tail -n +"$SKIP" "$0" | { base64 -d 2>/dev/null || base64 -D 2>/dev/null || openssl base64 -d -A; } | tar -xzf - -C "$tmp"
exec sh "$tmp/AgentBoot/install-offline.sh" "$@"
__AGENTBOOT_PAYLOAD_BELOW__
HF
    python3 - "$DIST/AgentBoot-offline-$TAG.tar.gz" "$SFX" <<'PYEOF'
import base64, sys
with open(sys.argv[1], 'rb') as src:
    with open(sys.argv[2], 'ab') as dst:
        dst.write(base64.b64encode(src.read()))
        dst.write(b'\n')
PYEOF
    chmod +x "$SFX"
    ok "sfx.sh：$(du -h "$SFX" | cut -f1)"
fi

step '构建完成'
ls -lh "$DIST" | grep AgentBoot-offline || true
