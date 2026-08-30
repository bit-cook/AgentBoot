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
NODE_VERSION="${NODE_VERSION:-v22.23.2}"
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

case "$(uname -s)-$(uname -m)" in
    Darwin-arm*) HOST_PLAT="darwin-arm64" ;;
    Darwin-*) HOST_PLAT="darwin-x64" ;;
    Linux-aarch*|Linux-arm64) HOST_PLAT="linux-arm64" ;;
    *) HOST_PLAT="linux-x64" ;;
esac

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
            win-x64)      OSV=win32;  CPUV=x64;   LIBCV="" ;;
            linux-x64)    OSV=linux;  CPUV=x64;   LIBCV=glibc ;;
            linux-arm64)  OSV=linux;  CPUV=arm64; LIBCV=glibc ;;
            darwin-x64)   OSV=darwin; CPUV=x64;   LIBCV="" ;;
            darwin-arm64) OSV=darwin; CPUV=arm64; LIBCV="" ;;
        esac
        case "$AID" in
            opencode) EXTRA="--ignore-scripts" ;;
            *)        EXTRA="" ;;
        esac
        step "载荷 $AID [$PLAT] ← $PKG"
        PREFIX="$STAGE/payloads/agents/$AID/$PLAT"
        mkdir -p "$PREFIX"
        if npm install --global-style --prefix "$PREFIX" --os "$OSV" --cpu "$CPUV" ${LIBCV:+--libc "$LIBCV"} \
               $EXTRA "$PKG" --registry "$NPM_MIRROR" --no-audit --no-fund --loglevel=error; then
            ok "$AID [$PLAT] 完成"
        else
            err "载荷安装失败：$AID@$PLAT（继续其他载荷）"
        fi
        # hermes 特殊：完整运行时（uv 预置 + postinstall）+ PACK_ROOT 标记
        if [ "$AID" = "hermes" ] && [ -d "$PREFIX/node_modules/hermes-agent" ]; then
            if [ "$PLAT" != "$HOST_PLAT" ]; then
                err "Hermes 完整运行时必须在目标平台构建：当前 $HOST_PLAT，目标 $PLAT；已移除半成品载荷"
                rm -rf "$PREFIX"
                continue
            fi
            python3 "$ROOT/scripts/tools/seed_uv_generic.py" "$PREFIX/node_modules/hermes-agent" "$PLAT"
            GIT_CONFIG_COUNT=1 \
            GIT_CONFIG_KEY_0="url.https://gh-proxy.com/https://github.com/.insteadOf" \
            GIT_CONFIG_VALUE_0="https://github.com/" \
            UV_PYTHON_INSTALL_MIRROR="https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download" \
            UV_HTTP_TIMEOUT=300 \
                node "$PREFIX/node_modules/hermes-agent/scripts/postinstall.js"
            printf '%s' "$PREFIX/node_modules/hermes-agent" > "$PREFIX/PACK_ROOT.txt"
            ok "hermes 完整运行时就绪 [$PLAT]"
        fi
    done
done

# ---------- 4. 内置 Python（Windows 便携版）+ CoCo 离线载荷 ----------
step '内置 Python（win-embed）…'
mkdir -p "$STAGE/payloads/python"
[ -f "$STAGE/payloads/python/win-embed.zip" ] || \
    curl -fL -o "$STAGE/payloads/python/win-embed.zip" \
        "https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip" \
    || curl -fL -o "$STAGE/payloads/python/win-embed.zip" \
        "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
ok 'win-embed.zip 就绪'

# CoCo（script 类）离线载荷：发行包 + sha256 + Agnes 密钥 + Node 22.23 运行时
case " $WANT " in *" coco "*)
    COCO_VER="0.8.0"
    for PLAT in $(echo "$PLATFORMS" | tr ',' ' '); do
        [ "$PLAT" = "win-x64" ] && continue
        CDIR="$STAGE/payloads/agents/coco/$PLAT"
        mkdir -p "$CDIR"
        for U in \
            "https://github.com/bit-cook/coco/releases/download/v$COCO_VER/coco-$COCO_VER.tgz" \
            "https://github.com/bit-cook/coco/releases/download/v$COCO_VER/coco-$COCO_VER.tgz.sha256" \
            "https://github.com/bit-cook/coco/releases/download/installer-v0.1.1.1/agnes.key"
        do
            F="$CDIR/$(basename "$U")"
            [ -f "$F" ] || curl -fL -o "$F" "https://gh-proxy.com/$U" || curl -fL -o "$F" "https://ghfast.top/$U" || err "CoCo 载荷下载失败：$(basename "$U")"
        done
        case "$PLAT" in
            linux-x64) NF="node-v22.23.2-linux-x64.tar.gz" ;;
            linux-arm64) NF="node-v22.23.2-linux-arm64.tar.gz" ;;
            darwin-x64) NF="node-v22.23.2-darwin-x64.tar.gz" ;;
            darwin-arm64) NF="node-v22.23.2-darwin-arm64.tar.gz" ;;
        esac
        [ -f "$CDIR/$NF" ] || curl -fL -o "$CDIR/$NF" "https://registry.npmmirror.com/-/binary/node/v22.23.2/$NF"
        ok "CoCo 离线载荷 [$PLAT] 就绪"
    done
;; esac

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

# ---------- 6. 按平台打包 ----------
step '按平台打包 …'
mkdir -p "$DIST"
for PLAT in $(echo "$PLATFORMS" | tr ',' ' '); do
    EX=""
    for OTHER in $(echo "$PLATFORMS" | tr ',' ' '); do
        [ "$OTHER" = "$PLAT" ] && continue
        EX="$EX --exclude=AgentBoot/payloads/agents/*/$OTHER --exclude=AgentBoot/payloads/node/$OTHER"
    done
    [ "$PLAT" != "win-x64" ] && EX="$EX --exclude=AgentBoot/payloads/python"
    if [ "$PLAT" = "win-x64" ]; then
        OUT="$DIST/AgentBoot-offline-$TAG-$PLAT.zip"
        (cd "$DIST/offline" && tar $EX -cf "$OUT" --zip AgentBoot) 2>/dev/null || \
        (cd "$DIST/offline" && python3 -c "import zipfile,os,sys;[zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED).write(os.path.join(r,f),os.path.relpath(os.path.join(r,f),sys.argv[2])) for r,ds,fs in os.walk(sys.argv[2]) for f in fs]" "$OUT" "$DIST/offline/AgentBoot")
    else
        OUT="$DIST/AgentBoot-offline-$TAG-$PLAT.tar.gz"
        (cd "$DIST/offline" && tar $EX -czf "$OUT" AgentBoot)
    fi
    ok "$(basename "$OUT")：$(du -h "$OUT" | cut -f1)"
done

# ---------- 7. POSIX 自解压安装器（非 Windows 平台） ----------
if command -v python3 >/dev/null 2>&1; then
    for PLAT in $(echo "$PLATFORMS" | tr ',' ' '); do
        [ "$PLAT" = "win-x64" ] && continue
        GZ="$DIST/AgentBoot-offline-$TAG-$PLAT.tar.gz"
        [ -f "$GZ" ] || continue
        step "生成自解压安装器 [$PLAT] …"
        SFX="$DIST/AgentBoot-offline-$TAG-$PLAT-sfx.sh"
        cat > "$SFX" <<'HF'
#!/bin/sh
# AgentBoot 离线自解压安装器：目标机器无需任何解压软件，直接运行
#   sh AgentBoot-offline-vX.Y.Z-<平台>-sfx.sh
set -eu
SKIP=$(awk '/^__AGENTBOOT_PAYLOAD_BELOW__$/{print NR+1; exit}' "$0")
tmp="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-sfx-$$)"
mkdir -p "$tmp"
echo "==> AgentBoot 离线自解压安装：解压中，请稍候 …"
tail -n +"$SKIP" "$0" | { base64 -d 2>/dev/null || base64 -D 2>/dev/null || openssl base64 -d -A; } | tar -xzf - -C "$tmp"
exec sh "$tmp/AgentBoot/install-offline.sh" "$@"
__AGENTBOOT_PAYLOAD_BELOW__
HF
        python3 - "$GZ" "$SFX" <<'PYEOF'
import base64, sys
with open(sys.argv[1], 'rb') as src:
    with open(sys.argv[2], 'ab') as dst:
        dst.write(base64.b64encode(src.read()))
        dst.write(b'\n')
PYEOF
        chmod +x "$SFX"
        ok "sfx.sh [$PLAT]：$(du -h "$SFX" | cut -f1)"
    done
fi

step '构建完成'
ls -lh "$DIST" | grep AgentBoot-offline || true
