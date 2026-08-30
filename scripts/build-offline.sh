#!/bin/sh
# =============================================================
#  AgentBoot 离线安装包构建脚本（Linux / macOS 构建机）
#  产物（dist/）：
#    AgentBoot-offline-vX.Y.Z.tar.gz / .zip   —— 全平台离线包
#    AgentBoot-offline-vX.Y.Z-sfx.sh          —— POSIX 自解压安装器
#  依赖：node+npm（或允许脚本自动下载便携 Node）、tar、curl 或 wget、python3
#  用法：
#    sh scripts/build-offline.sh
#    AGENTS="claude-code,codex" PLATFORMS="linux-x64,win-x64" sh scripts/build-offline.sh
# =============================================================
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${TAG:-v$(cat "$ROOT/VERSION")}"
NODE_VERSION="${NODE_VERSION:-v22.23.2}"
AGENTS_ENV="${AGENTS:-}"
NPM_MIRROR="https://registry.npmmirror.com"
DIST="$ROOT/dist"
STAGE="$DIST/offline/AgentBoot"

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
err()  { printf '✗ %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

fetch_file() { # fetch_file <url> <destination>
    rm -f "$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --connect-timeout 15 --retry 2 -o "$2" "$1" >/dev/null 2>&1 || true
        [ -s "$2" ] && return 0
        rm -f "$2"
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -q -T 60 -t 2 -O "$2" "$1" >/dev/null 2>&1 || true
        [ -s "$2" ] && return 0
        rm -f "$2"
    fi
    return 1
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
    else return 1
    fi
}

verify_node_archive() { # verify_node_archive <archive> <version> <filename>
    sums="$DIST/SHASUMS256-$2.txt"
    if [ ! -s "$sums" ]; then
        fetch_file "https://nodejs.org/dist/$2/SHASUMS256.txt" "$sums" || return 1
    fi
    expected="$(awk -v name="$3" '$2 == name {print $1; exit}' "$sums")"
    [ -n "$expected" ] || return 1
    actual="$(sha256_file "$1")" || return 1
    [ "$actual" = "$expected" ]
}

step "AgentBoot 离线包构建 $TAG · 平台：$PLATFORMS"

case "$(uname -s)-$(uname -m)" in
    Darwin-arm*) HOST_PLAT="darwin-arm64" ;;
    Darwin-*) HOST_PLAT="darwin-x64" ;;
    Linux-aarch*|Linux-arm64) HOST_PLAT="linux-arm64" ;;
    *) HOST_PLAT="linux-x64" ;;
esac
PLATFORMS="${PLATFORMS:-$HOST_PLAT}"

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
    fetch_file "https://registry.npmmirror.com/-/binary/node/$NODE_VERSION/$NF" "$DIST/$NF" \
        || fetch_file "https://nodejs.org/dist/$NODE_VERSION/$NF" "$DIST/$NF" \
        || { err "Node 下载失败：$NF"; exit 1; }
    verify_node_archive "$DIST/$NF" "$NODE_VERSION" "$NF" \
        || { err "Node SHA-256 校验失败：$NF"; exit 1; }
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
    if [ ! -s "$ARC" ] || ! verify_node_archive "$ARC" "$NODE_VERSION" "$NF"; then
        rm -f "$ARC"
        fetch_file "https://registry.npmmirror.com/-/binary/node/$NODE_VERSION/$NF" "$ARC" \
            || fetch_file "https://nodejs.org/dist/$NODE_VERSION/$NF" "$ARC" \
            || { err "Node 下载失败：$NF"; exit 1; }
        verify_node_archive "$ARC" "$NODE_VERSION" "$NF" \
            || { rm -f "$ARC"; err "Node SHA-256 校验失败：$NF"; exit 1; }
    fi
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
    WANT="$(python3 - "$ROOT/agents/registry.json" "$HOST_PLAT" <<'PYEOF'
import json,sys
platform_id=sys.argv[2]
os_id={'win-x64':'windows','linux-x64':'linux','linux-arm64':'linux','darwin-x64':'darwin','darwin-arm64':'darwin'}[platform_id]
agents=json.load(open(sys.argv[1]))['agents']
print(' '.join(a['id'] for a in agents if a.get('offline') and (not a.get('os') or os_id in a['os'])))
PYEOF
)"
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
[ -s "$STAGE/payloads/python/win-embed.zip" ] || \
    fetch_file "https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip" \
        "$STAGE/payloads/python/win-embed.zip" \
    || fetch_file "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip" \
        "$STAGE/payloads/python/win-embed.zip" \
    || { err "Windows Python 便携包下载失败"; exit 1; }
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
            [ -s "$F" ] || fetch_file "https://gh-proxy.com/$U" "$F" \
                || fetch_file "https://ghfast.top/$U" "$F" \
                || fetch_file "$U" "$F" \
                || { err "CoCo 载荷下载失败：$(basename "$U")"; exit 1; }
        done
        case "$PLAT" in
            linux-x64) NF="node-v22.23.2-linux-x64.tar.gz" ;;
            linux-arm64) NF="node-v22.23.2-linux-arm64.tar.gz" ;;
            darwin-x64) NF="node-v22.23.2-darwin-x64.tar.gz" ;;
            darwin-arm64) NF="node-v22.23.2-darwin-arm64.tar.gz" ;;
        esac
        if [ ! -s "$CDIR/$NF" ] || ! verify_node_archive "$CDIR/$NF" "v22.23.2" "$NF"; then
            fetch_file "https://registry.npmmirror.com/-/binary/node/v22.23.2/$NF" "$CDIR/$NF" \
                || fetch_file "https://nodejs.org/dist/v22.23.2/$NF" "$CDIR/$NF" \
                || { err "CoCo Node 下载失败：$NF"; exit 1; }
            verify_node_archive "$CDIR/$NF" "v22.23.2" "$NF" \
                || { rm -f "$CDIR/$NF"; err "CoCo Node SHA-256 校验失败：$NF"; exit 1; }
        fi
        ok "CoCo 离线载荷 [$PLAT] 就绪"
    done
;; esac

# ---------- 5. 离线安装脚本 + 清单 ----------
python3 "$ROOT/scripts/tools/validate_offline_payload.py" "$STAGE" "$PLATFORMS" "$(echo "$WANT" | tr ' ' ',')" \
    || { err "离线载荷闭包校验失败，拒绝打包"; exit 1; }
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
        python3 "$ROOT/scripts/tools/zip_tree.py" "$OUT" "$DIST/offline/AgentBoot" AgentBoot
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
