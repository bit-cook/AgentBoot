#!/bin/sh
# =============================================================
#  AgentBoot 在线一键安装（Linux / macOS）
#  用法：
#    curl -fsSL https://boot.ide.pub/install.sh | sh
#    或：sh install.sh
#  行为：下载在线包 → 安装到 ~/.agentboot → 生成 agentboot / ab 命令
# =============================================================
set -eu

REPO="bit-cook/AgentBoot"
TAG="v1.1.0"
TARBALL="agentboot-online-${TAG}.tar.gz"
BOOT_BASE="https://boot.ide.pub"
GH="https://github.com/${REPO}/releases/download/${TAG}"
AB_ROOT="${HOME}/.agentboot"
APP_DIR="${AB_ROOT}/app"
BIN_DIR="${HOME}/.local/bin"

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
err()  { printf '✗ %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

# ---------- 下载器：curl 优先，wget 兜底 ----------
fetch() { # fetch <url> <outfile>
    rm -f "$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --connect-timeout 10 --retry 2 -o "$2" "$1" >/dev/null 2>&1 || true
        [ -s "$2" ] && return 0
        rm -f "$2"
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -q -T 30 -t 2 -O "$2" "$1" >/dev/null 2>&1 || true
        [ -s "$2" ] && return 0
        rm -f "$2"
    fi
    return 1
}

verify_sha256() { # verify_sha256 <file> <sidecar>
    expected="$(awk 'NR==1 {print $1}' "$2" 2>/dev/null | tr 'A-F' 'a-f')"
    case "$expected" in
        *[!0-9a-f]*|"") return 1 ;;
    esac
    [ "${#expected}" -eq 64 ] || return 1
    if command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$1" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$1" | awk '{print $1}')"
    elif command -v openssl >/dev/null 2>&1; then
        actual="$(openssl dgst -sha256 "$1" | awk '{print $NF}')"
    else
        err "系统缺少 SHA-256 校验工具（sha256sum / shasum / openssl）"
        return 1
    fi
    [ "$(printf '%s' "$actual" | tr 'A-F' 'a-f')" = "$expected" ]
}

step "AgentBoot 在线安装 ${TAG} · $(uname -s) $(uname -m)"

# 在替换 app 前先保护用户已有的同名命令，避免应用已升级但 launcher 更新失败。
for launcher in "${BIN_DIR}/agentboot" "${BIN_DIR}/ab"; do
    if [ -L "$launcher" ]; then
        err "拒绝覆盖符号链接命令：$launcher"
        exit 1
    fi
    if [ -e "$launcher" ] && ! grep -q '^# AgentBoot ' "$launcher" 2>/dev/null; then
        err "拒绝覆盖不属于 AgentBoot 的命令：$launcher"
        exit 1
    fi
done

# ---------- 1. 下载在线包（多源容错：Cloudflare → GitHub → 国内加速镜像） ----------
TMP="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-install-$$)"
mkdir -p "$TMP"
STAGE="${TMP}/src"
mkdir -p "$STAGE"

dl_ok=""
for url in \
    "${BOOT_BASE}/rel/${TARBALL}" \
    "https://bit-cook.github.io/AgentBoot/${TARBALL}" \
    "${GH}/${TARBALL}" \
    "https://ghfast.top/${GH}/${TARBALL}" \
    "https://gh-proxy.com/${GH}/${TARBALL}"
do
    say "下载：${url}"
    if fetch "$url" "${TMP}/${TARBALL}" && fetch "${url}.sha256" "${TMP}/${TARBALL}.sha256"; then
        if [ -s "${TMP}/${TARBALL}" ] && verify_sha256 "${TMP}/${TARBALL}" "${TMP}/${TARBALL}.sha256"; then
            dl_ok="1"
            ok "SHA-256 校验通过"
            break
        fi
        err "SHA-256 校验失败"
    fi
    err "该源不可用，尝试下一个 …"
done
if [ -z "$dl_ok" ]; then
    err "所有下载源均失败。请检查网络，或使用离线安装包（见项目文档《安装指南.md》）。"
    exit 1
fi

# ---------- 2. 解压（系统自带 tar，无需安装解压软件） ----------
step "解压安装包"
if ! tar -xzf "${TMP}/${TARBALL}" -C "$STAGE"; then
    err "解压失败：下载文件可能不完整。"
    exit 1
fi
SRC_DIR="$STAGE"
if [ "$(ls -A "$STAGE" | wc -l)" = "1" ] && [ -d "$STAGE/$(ls -A "$STAGE")" ]; then
    SRC_DIR="$STAGE/$(ls -A "$STAGE")"
fi

step "安装程序到 ${APP_DIR}"
mkdir -p "$AB_ROOT"
NEW_APP="${AB_ROOT}/app.new.$$"
OLD_APP="${AB_ROOT}/app.old.$$"
rm -rf "$NEW_APP" "$OLD_APP"
mkdir -p "$NEW_APP"
cp -R "${SRC_DIR}/." "$NEW_APP/"
if [ ! -f "$NEW_APP/core/menu.py" ] || [ ! -f "$NEW_APP/core/agent.py" ]; then
    err "安装包结构无效，保留现有版本"
    rm -rf "$NEW_APP"
    exit 1
fi
if [ -d "$APP_DIR" ]; then mv "$APP_DIR" "$OLD_APP"; fi
if mv "$NEW_APP" "$APP_DIR"; then
    rm -rf "$OLD_APP"
else
    err "切换新版本失败，正在恢复旧版本"
    [ -d "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR"
    rm -rf "$NEW_APP"
    exit 1
fi
chmod +x "${APP_DIR}/install.sh" 2>/dev/null || true

# ---------- 3. 生成命令行入口 ----------
step "创建命令：agentboot（控制台） / ab（内置 Agent）"
mkdir -p "$BIN_DIR"
agentboot_tmp="${BIN_DIR}/.agentboot.new.$$"
ab_tmp="${BIN_DIR}/.ab.new.$$"
rm -f "$agentboot_tmp" "$ab_tmp"
cat > "$agentboot_tmp" <<EOF
#!/bin/sh
# AgentBoot 控制台
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/menu.py" "\$@"
EOF
cat > "$ab_tmp" <<EOF
#!/bin/sh
# AgentBoot 内置最小 Agent
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/agent.py" "\$@"
EOF
chmod +x "$agentboot_tmp" "$ab_tmp"
mv -f "$agentboot_tmp" "${BIN_DIR}/agentboot"
mv -f "$ab_tmp" "${BIN_DIR}/ab"
ok "已写入 ${BIN_DIR}"

# ---------- 4. PATH 注册（幂等） ----------
case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *)
        BLOCK="# >>> agentboot >>>"
        for rc in "${HOME}/.bashrc" "${HOME}/.profile"; do
            if [ -f "$rc" ] && ! grep -q "$BLOCK" "$rc" 2>/dev/null; then
                { echo ''; echo "$BLOCK";
                  echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
                  echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
                  echo 'done'; echo 'unset _d'; } >> "$rc"
                ok "PATH 已写入 $rc（重开终端生效）"
            fi
        done
        if [ -f "${HOME}/.zshrc" ] && ! grep -q "$BLOCK" "${HOME}/.zshrc" 2>/dev/null; then
            { echo ''; echo "$BLOCK";
              echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
              echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
              echo 'done'; echo 'unset _d'; } >> "${HOME}/.zshrc"
            ok "PATH 已写入 ~/.zshrc（重开终端生效）"
        fi
        ;;
esac

# ---------- 5. Python 检查（ab 需要；缺失时尽力自动安装） ----------
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
    step "未检测到 Python3，尝试自动安装（ab 内置 Agent 依赖）"
    if command -v apt-get >/dev/null 2>&1; then
        (sudo apt-get update -y && sudo apt-get install -y python3) >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then
        (sudo dnf install -y python3) >/dev/null 2>&1 || true
    elif command -v yum >/dev/null 2>&1; then
        (sudo yum install -y python3) >/dev/null 2>&1 || true
    elif command -v pacman >/dev/null 2>&1; then
        (sudo pacman -Sy --noconfirm python) >/dev/null 2>&1 || true
    elif command -v apk >/dev/null 2>&1; then
        (apk add --no-cache python3) >/dev/null 2>&1 || true
    elif command -v brew >/dev/null 2>&1; then
        (brew install python3) >/dev/null 2>&1 || true
    fi
    PY="$(command -v python3 || command -v python || true)"
    if [ -z "$PY" ]; then
        err "未能自动安装 Python3。请手动安装后运行：agentboot"
    fi
fi

# ---------- 6. 体检 ----------
if [ -n "$PY" ]; then
    step "环境体检"
    "$PY" "${APP_DIR}/core/agent.py" doctor >/dev/null 2>&1 || true
    "$PY" "${APP_DIR}/core/agent.py" doctor 2>/dev/null || true
fi

# ---------- 7. 完成 ----------
say ""
say "=============================================="
ok  "AgentBoot 安装完成！"
say "  控制台菜单 : agentboot"
say "  内置 Agent : ab      （默认 Agnes 免费模型，直接可用）"
say "  安装其他 Agent：运行 agentboot → 选 [2] 在线安装"
say "  当前终端立即生效：export PATH=\"${BIN_DIR}:\$PATH\""
say "=============================================="

# 交互终端时询问是否直接打开菜单
if [ -n "$PY" ] && [ -e /dev/tty ] && [ -t 2 ]; then
    printf '是否现在打开控制台菜单? [Y/n] '
    read ans < /dev/tty || ans="n"
    case "$ans" in
        n|N|no|NO) ;;
        *) exec "$PY" "${APP_DIR}/core/menu.py" ;;
    esac
fi
