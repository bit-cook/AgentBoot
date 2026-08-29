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

# ---------- 1. 校验离线载荷 ----------
if [ ! -d "${SCRIPT_DIR}/payloads/agents" ]; then
    err "未找到 payloads/ 离线载荷目录。请确认脚本位于完整解压后的离线包根目录。"
    exit 1
fi
ok "离线载荷校验通过：${SCRIPT_DIR}/payloads"

# ---------- 2. 安装程序本体 ----------
step "安装程序到 ${APP_DIR}"
mkdir -p "$APP_DIR"
cp -R "${SCRIPT_DIR}/core"      "$APP_DIR/"
cp -R "${SCRIPT_DIR}/agents"    "$APP_DIR/"
cp -R "${SCRIPT_DIR}/tools"     "$APP_DIR/"
cp -R "${SCRIPT_DIR}/scripts"   "$APP_DIR/"
for f in README.md 安装指南.md LICENSE CHANGELOG.md install.sh install.bat install-offline.sh install-offline.ps1; do
    [ -f "${SCRIPT_DIR}/$f" ] && cp -f "${SCRIPT_DIR}/$f" "$APP_DIR/" || true
done

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
cat > "${BIN_DIR}/agentboot" <<EOF
#!/bin/sh
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/menu.py" "\$@"
EOF
cat > "${BIN_DIR}/ab" <<EOF
#!/bin/sh
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/agent.py" chat "\$@"
EOF
chmod +x "${BIN_DIR}/agentboot" "${BIN_DIR}/ab"

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
        "$PY" "${APP_DIR}/core/menu.py" offline --payload "${SCRIPT_DIR}/payloads" \
            "$("$PY" -c "import json,sys;print(' '.join(a['id'] for a in json.load(open(sys.argv[1]))['agents'] if a.get('offline')))" "${APP_DIR}/agents/registry.json")"
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
