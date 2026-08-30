#!/bin/sh
# =============================================================
#  AgentBoot 离线一键安装（Linux / macOS）
#  前提：已拿到 AgentBoot-offline-vX.Y.Z.tar.gz（或 .zip / 自解压 .sh）
#  本脚本位于离线包根目录，无需联网、无需解压软件（tar 为系统自带）。
#
#  用法：
#    sh install-offline.sh              # 安装后打开控制台菜单（推荐）
#    sh install-offline.sh --all        # 直接安装全部支持离线的 Agent
#    sh install-offline.sh claude-code qwen-code   # 安装指定 Agent
# =============================================================
set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AB_ROOT="${HOME}/.agentboot"
APP_DIR="${AB_ROOT}/app"
BIN_DIR="${HOME}/.local/bin"

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
err()  { printf '✗ %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

step "AgentBoot 离线安装（无需联网）"

for launcher in "${BIN_DIR}/agentboot" "${BIN_DIR}/ab"; do
    if [ -L "$launcher" ]; then
        err "拒绝覆盖符号链接命令：$launcher"; exit 1
    fi
    if [ -e "$launcher" ] && ! grep -q '^# AgentBoot ' "$launcher" 2>/dev/null; then
        err "拒绝覆盖不属于 AgentBoot 的命令：$launcher"; exit 1
    fi
done

# ---------- 1. 校验离线载荷 ----------
if [ ! -d "${SCRIPT_DIR}/payloads/agents" ]; then
    err "未找到 payloads/ 离线载荷目录。请确认脚本位于完整解压后的离线包根目录。"
    exit 1
fi
SUMS="${SCRIPT_DIR}/PAYLOAD_SHA256SUMS.txt"
[ -s "$SUMS" ] || { err "缺少 PAYLOAD_SHA256SUMS.txt，拒绝安装未验证载荷"; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then HASH_CMD="sha256sum"
elif command -v shasum >/dev/null 2>&1; then HASH_CMD="shasum -a 256"
else err "缺少 SHA-256 校验工具"; exit 1
fi
while read -r expected relative; do
    [ -n "$expected" ] || continue
    file="${SCRIPT_DIR}/${relative}"
    [ -f "$file" ] || { err "载荷缺失：$relative"; exit 1; }
    actual="$($HASH_CMD "$file" | awk '{print $1}')"
    [ "$actual" = "$expected" ] || { err "载荷校验失败：$relative"; exit 1; }
done < "$SUMS"
ok "离线载荷 SHA-256 校验通过：${SCRIPT_DIR}/payloads"

# ---------- 2. 安装程序本体 ----------
step "安装程序到 ${APP_DIR}"
mkdir -p "$AB_ROOT"
NEW_APP="${AB_ROOT}/app.new.$$"
OLD_APP="${AB_ROOT}/app.old.$$"
rm -rf "$NEW_APP" "$OLD_APP"
mkdir -p "$NEW_APP"
cp -R "${SCRIPT_DIR}/core"      "$NEW_APP/"
cp -R "${SCRIPT_DIR}/agents"    "$NEW_APP/"
cp -R "${SCRIPT_DIR}/tools"     "$NEW_APP/"
cp -R "${SCRIPT_DIR}/scripts"   "$NEW_APP/"
for f in VERSION README.md 安装指南.md LICENSE CHANGELOG.md install.sh install.bat install-offline.sh install-offline.ps1; do
    [ -f "${SCRIPT_DIR}/$f" ] && cp -f "${SCRIPT_DIR}/$f" "$NEW_APP/" || true
done
if [ ! -f "$NEW_APP/core/menu.py" ] || [ ! -f "$NEW_APP/core/agent.py" ]; then
    err "离线包结构无效，保留现有版本"; rm -rf "$NEW_APP"; exit 1
fi
[ -d "$APP_DIR" ] && mv "$APP_DIR" "$OLD_APP"
if mv "$NEW_APP" "$APP_DIR"; then rm -rf "$OLD_APP"
else [ -d "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR"; err "升级失败，已恢复旧版本"; exit 1
fi

# ---------- 3. Python 检查（ab 需要；绝大多数系统自带） ----------
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
    err "本机没有 python3。请用系统包管理器安装（apt/dnf/apk/brew install python3），然后重跑本脚本。"
    say  "（Linux 服务器一般自带 python3；macOS 终端运行会自动触发安装。）"
    exit 1
fi
ok "Python：$PY"

# ---------- 4. 命令入口 ----------
step "创建命令：agentboot（控制台） / ab（内置 Agent）"
mkdir -p "$BIN_DIR"
agentboot_tmp="${BIN_DIR}/.agentboot.new.$$"
ab_tmp="${BIN_DIR}/.ab.new.$$"
rm -f "$agentboot_tmp" "$ab_tmp"
cat > "$agentboot_tmp" <<EOF
#!/bin/sh
# AgentBoot launcher
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/menu.py" "\$@"
EOF
cat > "$ab_tmp" <<EOF
#!/bin/sh
# AgentBoot launcher
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/agent.py" "\$@"
EOF
chmod +x "$agentboot_tmp" "$ab_tmp"
mv -f "$agentboot_tmp" "${BIN_DIR}/agentboot"
mv -f "$ab_tmp" "${BIN_DIR}/ab"

# PATH（幂等写入）
case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *)
        for rc in "${HOME}/.bashrc" "${HOME}/.profile"; do
            if [ -f "$rc" ] && ! grep -q "agentboot" "$rc" 2>/dev/null; then
                { echo ''; echo '# >>> agentboot >>>';
                  echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
                  echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
                  echo 'done'; echo 'unset _d'; } >> "$rc"
            fi
        done
        [ -f "${HOME}/.zshrc" ] && ! grep -q "agentboot" "${HOME}/.zshrc" 2>/dev/null && \
            { echo ''; echo '# >>> agentboot >>>';
              echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
              echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
              echo 'done'; echo 'unset _d'; } >> "${HOME}/.zshrc" || true
        ;;
esac

export AGENTBOOT_PAYLOAD="${SCRIPT_DIR}/payloads"
export PATH="${BIN_DIR}:${PATH}"

# ---------- 5. 安装 Agent（离线载荷落盘，不调用 npm） ----------
ARGS="${*:-}"
if [ -n "$ARGS" ]; then
    step "离线安装指定 Agent：$ARGS"
    if [ "$ARGS" = "--all" ]; then
        PACKED="$(awk -F: '/^agents[[:space:]]*:/ {gsub(/[[:space:]]/,"",$2); print $2}' "${SCRIPT_DIR}/MANIFEST.txt")"
        [ -n "$PACKED" ] || { err "MANIFEST.txt 未列出 Agent"; exit 1; }
        "$PY" "${APP_DIR}/core/menu.py" offline --payload "${SCRIPT_DIR}/payloads" "$PACKED"
    else
        "$PY" "${APP_DIR}/core/menu.py" offline --payload "${SCRIPT_DIR}/payloads" $ARGS
    fi
fi

# ---------- 6. 完成 ----------
say ""
say "=============================================="
ok  "AgentBoot 离线安装完成！"
say "  控制台菜单 : agentboot   （菜单[3] 可继续离线安装其他 Agent）"
say "  内置 Agent : ab          （默认 Agnes 免费模型；联网后可直接用）"
say "  纯离线用模型：菜单[4] → 配置本地模型（Ollama / LM Studio）"
say "=============================================="

if [ -z "$ARGS" ] && [ -e /dev/tty ] && [ -t 2 ]; then
    printf '是否现在打开控制台菜单? [Y/n] '
    read ans < /dev/tty || ans="n"
    case "$ans" in
        n|N|no|NO) ;;
        *) exec "$PY" "${APP_DIR}/core/menu.py" ;;
    esac
fi
