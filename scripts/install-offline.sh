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
# launcher 目录：优先 /usr/local/bin——默认就在所有 shell 的 PATH 上，
# 装完当前终端立即可用，不需要 source ~/.bashrc。root 直接可写；非 root
# 但有 passwordless sudo 时借 sudo 落盘（-n 非交互，不弹密码）；两者都
# 不满足退回 ~/.local/bin，由 PATH 注册写 shell 配置兜底。
BIN_DIR="${HOME}/.local/bin"
BIN_SUDO=""
if [ -d /usr/local/bin ] && [ -w /usr/local/bin ]; then
    BIN_DIR="/usr/local/bin"
elif [ -d /usr/local/bin ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    BIN_DIR="/usr/local/bin"
    BIN_SUDO="sudo -n"
fi
STALE_BIN_DIRS="${HOME}/.local/bin /usr/local/bin"

say()  { printf '%s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
err()  { printf '✗ %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }

step "AgentBoot 离线安装（无需联网）"

OLD_APP=""
SWAP_COMMITTED=0
rollback_install() {
    code=$?
    trap - EXIT HUP INT TERM
    rm -f "${BIN_DIR}/.agentboot.new.$$" "${BIN_DIR}/.ab.new.$$"
    if [ "$code" -ne 0 ] && [ "$SWAP_COMMITTED" -eq 0 ] && [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
        rm -rf "$APP_DIR"
        mv "$OLD_APP" "$APP_DIR" || true
    fi
    exit "$code"
}
trap rollback_install EXIT HUP INT TERM

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

PY="$(command -v python3 || true)"
if [ -z "$PY" ] && command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info[0] != 3)' >/dev/null 2>&1; then
    PY="$(command -v python)"
fi
[ -n "$PY" ] || { err "本机没有可用 Python3，保留现有版本并退出。"; exit 1; }

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
if [ ! -f "$NEW_APP/core/menu.py" ] || [ ! -f "$NEW_APP/core/agent.py" ] || [ ! -f "$NEW_APP/core/launch.py" ]; then
    err "离线包结构无效，保留现有版本"; rm -rf "$NEW_APP"; exit 1
fi
[ -d "$APP_DIR" ] && mv "$APP_DIR" "$OLD_APP"
if mv "$NEW_APP" "$APP_DIR"; then :
else [ -d "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR"; err "升级失败，已恢复旧版本"; exit 1
fi

# ---------- 3. Python 检查（ab 需要；绝大多数系统自带） ----------
ok "Python：$PY"

# ---------- 4. 命令入口 ----------
step "创建命令：agentboot（控制台） / ab（内置 Agent）"
# 落盘前探写：BIN_DIR 选择阶段的 -w / sudo -n 推断可能失灵（只读挂载、
# immutable 目录、LSM 拦截等），探写失败即回落到 ~/.local/bin，
# 绝不在应用已落盘后卡死在"创建命令"这一步（半安装脏状态）。
probe_bin_dir() {
    _probe="${BIN_DIR}/.ab_probe.$$"
    if [ -n "$BIN_SUDO" ]; then
        $BIN_SUDO touch "$_probe" 2>/dev/null || return 1
        $BIN_SUDO rm -f "$_probe" 2>/dev/null || true
    else
        touch "$_probe" 2>/dev/null || return 1
        rm -f "$_probe" 2>/dev/null || true
    fi
    return 0
}
if ! probe_bin_dir; then
    if [ "$BIN_DIR" != "${HOME}/.local/bin" ]; then
        err "无法写入 ${BIN_DIR}，回落到 ~/.local/bin"
        BIN_DIR="${HOME}/.local/bin"
        BIN_SUDO=""
    fi
    mkdir -p "$BIN_DIR" || { err "无法创建 ${BIN_DIR}，请手动安装"; exit 1; }
    if ! probe_bin_dir; then
        err "无法写入 ${BIN_DIR}，请检查权限后重试"
        exit 1
    fi
    ok "命令入口将安装到 ${BIN_DIR}"
fi
# 临时文件与目标同目录（可写时）——保证 mv 原子替换；sudo 场景用 mktemp + sudo install
# mktemp 尊重 $TMPDIR，其不可写时回退 /tmp（与下载临时目录同款容错）
if [ -n "$BIN_SUDO" ]; then
    TMP_BASE="$(mktemp -d 2>/dev/null || mktemp -d -p /tmp 2>/dev/null || echo "/tmp/agentboot-launcher-$$")"
    trap 'rm -rf "$TMP_BASE"' EXIT
else
    TMP_BASE="$BIN_DIR"
fi
agentboot_tmp="${TMP_BASE}/.agentboot.new.$$"
ab_tmp="${TMP_BASE}/.ab.new.$$"
rm -f "$agentboot_tmp" "$ab_tmp"
cat > "$agentboot_tmp" <<EOF
#!/bin/sh
# AgentBoot launcher
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/launch.py" menu "\$@"
EOF
cat > "$ab_tmp" <<EOF
#!/bin/sh
# AgentBoot launcher
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/launch.py" agent "\$@"
EOF
chmod +x "$agentboot_tmp" "$ab_tmp"
# 落盘：拒绝符号链接；可直接写则同目录 mv（原子）；sudo 场景经 sudo install
install_launcher() {
    launcher="${BIN_DIR}/$2"
    if [ -L "$launcher" ]; then
        err "拒绝写入：$launcher 是符号链接"
        return 1
    fi
    if [ -n "$BIN_SUDO" ]; then
        $BIN_SUDO install -m 755 "$1" "$launcher"
    else
        mv -f "$1" "$launcher"
    fi
}
# 命令入口创建失败时回滚：升级则恢复旧版，新装则撤掉刚落地的应用，
# 杜绝"应用在、命令无"的半安装脏状态（重跑安装器即可自愈）
rollback_install() {
    if [ -d "${OLD_APP:-}" ]; then
        rm -rf "$APP_DIR"
        mv "$OLD_APP" "$APP_DIR"
    elif [ "${SWAP_COMMITTED:-0}" != "1" ]; then
        rm -rf "$APP_DIR"
    fi
}
install_launcher "$agentboot_tmp" agentboot || { rollback_install; err "写入 launcher 失败：${BIN_DIR}/agentboot"; exit 1; }
install_launcher "$ab_tmp" ab || { rollback_install; err "写入 launcher 失败：${BIN_DIR}/ab"; exit 1; }
SWAP_COMMITTED=1
# 清理另一处位置的旧 launcher（只删 AgentBoot 自己的：内容指向 launch.py）
for stale_dir in $STALE_BIN_DIRS; do
    [ "$stale_dir" = "$BIN_DIR" ] && continue
    for stale_bin in agentboot ab; do
        stale_path="$stale_dir/$stale_bin"
        if [ -f "$stale_path" ] && grep -q "launch.py" "$stale_path" 2>/dev/null; then
            rm -f "$stale_path" 2>/dev/null && say "· 清理旧位置 launcher：$stale_path"
        fi
    done
done
rm -rf "$OLD_APP"

# PATH（幂等写入）
# 注意：rc 不存在时要先创建再写——用 [ -f ] 判断会在新系统上静默跳过，
# 导致装完 agentboot 找不到命令（v1.4.4 实测踩过）。
case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *)
        for rc in "${HOME}/.bashrc" "${HOME}/.profile"; do
            [ -d "$HOME" ] || continue
            grep -q "agentboot" "$rc" 2>/dev/null && continue
            [ -f "$rc" ] || : > "$rc" 2>/dev/null || continue
            { echo ''; echo '# >>> agentboot >>>';
              echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
              echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
              echo 'done'; echo 'unset _d'; } >> "$rc" 2>/dev/null \
                && ok "PATH 已写入 $rc（重开终端生效）" \
                || err "无法写入 $rc，请手动把 ${BIN_DIR} 加入 PATH"
        done
        if [ -d "$HOME" ] && ! grep -q "agentboot" "${HOME}/.zshrc" 2>/dev/null; then
            [ -f "${HOME}/.zshrc" ] || : > "${HOME}/.zshrc" 2>/dev/null || true
            [ -f "${HOME}/.zshrc" ] && \
                { echo ''; echo '# >>> agentboot >>>';
                  echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
                  echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
                  echo 'done'; echo 'unset _d'; } >> "${HOME}/.zshrc" 2>/dev/null || true
        fi
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
say ""
say "  如何启动："
say "    控制台菜单 : agentboot   （菜单[3] 可继续离线安装其他 Agent）"
say "    内置 Agent : ab          （默认 Agnes 免费模型；联网后可直接用）"
say "    纯离线用模型：菜单[4] → 配置本地模型（Ollama / LM Studio）"
say ""
case ":$PATH:" in
    *":${BIN_DIR}:"*)
        say "  ✓ ${BIN_DIR} 已在 PATH 中——当前终端直接输入 agentboot 即可启动，"
        say "    无需 source、无需重开终端。"
        ;;
    *)
        if grep -q "agentboot" "${HOME}/.bashrc" 2>/dev/null; then
            say "  PATH 已写入 ~/.bashrc。当前终端立即生效请执行：source ~/.bashrc"
            say "  或者关掉本终端重开一个（新终端自动生效）。"
        else
            say "  未能自动写入 shell 配置。当前终端立即生效请执行："
            say "      export PATH=\"${BIN_DIR}:\$PATH\""
        fi
        ;;
esac
say "=============================================="

if [ -z "$ARGS" ] && [ -e /dev/tty ] && [ -t 2 ]; then
    printf '是否现在打开控制台菜单? [Y/n] '
    read ans < /dev/tty || ans="n"
    case "$ans" in
        n|N|no|NO) say "下次输入 agentboot 即可打开控制台。" ;;
        # stdin 必须是 /dev/tty：经管道运行本脚本时 stdin 已耗尽，
        # 不重定向菜单一启动就 EOF 退出（v1.4.4 实测踩过）
        *) exec "$PY" "${APP_DIR}/core/menu.py" < /dev/tty ;;
    esac
fi
