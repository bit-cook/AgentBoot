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
TAG="v1.6.0"
TARBALL="agentboot-online-${TAG}.tar.gz"
BOOT_BASE="https://boot.ide.pub"
GH="https://github.com/${REPO}/releases/download/${TAG}"
AB_ROOT="${HOME}/.agentboot"
APP_DIR="${AB_ROOT}/app"
# launcher 目录：优先 /usr/local/bin——它默认就在所有 shell 的 PATH 上，
# 装完当前终端立即可用，不需要 source ~/.bashrc（一键安装体验的关键）。
# root 直接可写；非 root 但有 passwordless sudo 时借 sudo 落盘（-n 非交互，
# 绝不弹密码提示）；两者都不满足退回 ~/.local/bin，由 PATH 注册写 shell
# 配置兜底（Debian/Ubuntu 的 ~/.profile 会为新登录 shell 加上它）。
BIN_DIR="${HOME}/.local/bin"
BIN_SUDO=""
if [ -d /usr/local/bin ] && [ -w /usr/local/bin ]; then
    BIN_DIR="/usr/local/bin"
elif [ -d /usr/local/bin ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    BIN_DIR="/usr/local/bin"
    BIN_SUDO="sudo -n"
fi
# 所有可能的旧 launcher 位置（版本间目录选择变化时清理，防止旧版挡住新版）
STALE_BIN_DIRS="${HOME}/.local/bin /usr/local/bin"

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

# ---------- 1. 下载在线包（项目控制的四源：Worker → Pages → jsDelivr 镜像 → GitHub Release；任一域名失效仍可安装） ----------
TMP="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-install-$$)"
mkdir -p "$TMP"
STAGE="${TMP}/src"
mkdir -p "$STAGE"
OLD_APP=""
SWAP_COMMITTED=0
cleanup_install() {
    code=$?
    trap - EXIT HUP INT TERM
    rm -f "${BIN_DIR}/.agentboot.new.$$" "${BIN_DIR}/.ab.new.$$"
    if [ "$code" -ne 0 ] && [ "$SWAP_COMMITTED" -eq 0 ] && [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
        rm -rf "$APP_DIR"
        mv "$OLD_APP" "$APP_DIR" || true
    fi
    rm -rf "$TMP"
    exit "$code"
}
trap cleanup_install EXIT HUP INT TERM

dl_ok=""
for url in \
    "${BOOT_BASE}/rel/${TARBALL}" \
    "https://bit-cook.github.io/AgentBoot/${TARBALL}" \
    "https://cdn.jsdelivr.net/gh/${REPO}@gh-pages/${TARBALL}" \
    "${GH}/${TARBALL}"
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
[ "$(wc -c < "${TMP}/${TARBALL}")" -le 20971520 ] || { err "在线包异常过大"; exit 1; }

# ---------- 2. 解压（系统自带 tar，无需安装解压软件） ----------
step "解压安装包"
members="${TMP}/members.txt"
tar -tzf "${TMP}/${TARBALL}" > "$members" || { err "无法读取安装包目录"; exit 1; }
[ "$(wc -l < "$members")" -le 20000 ] || { err "安装包文件数量异常"; exit 1; }
if awk 'BEGIN{bad=0} /^\//{bad=1} /(^|\/)\.\.($|\/)/{bad=1} END{exit bad?0:1}' "$members"; then
    err "安装包包含越界路径"; exit 1
fi
if ! tar -xzf "${TMP}/${TARBALL}" -C "$STAGE"; then
    err "解压失败：下载文件可能不完整。"
    exit 1
fi
SRC_DIR="$STAGE"
if [ "$(ls -A "$STAGE" | wc -l)" = "1" ] && [ -d "$STAGE/$(ls -A "$STAGE")" ]; then
    SRC_DIR="$STAGE/$(ls -A "$STAGE")"
fi

# 在提交应用目录前确认可执行的 Python 3；失败时现有安装保持不变。
PY="$(command -v python3 || true)"
if [ -z "$PY" ] && command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info[0] != 3)' >/dev/null 2>&1; then
    PY="$(command -v python)"
fi
if [ -z "$PY" ]; then
    step "未检测到 Python3，尝试自动安装"
    if command -v apt-get >/dev/null 2>&1; then (sudo apt-get update -y && sudo apt-get install -y python3) >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then (sudo dnf install -y python3) >/dev/null 2>&1 || true
    elif command -v yum >/dev/null 2>&1; then (sudo yum install -y python3) >/dev/null 2>&1 || true
    elif command -v pacman >/dev/null 2>&1; then (sudo pacman -Sy --noconfirm python) >/dev/null 2>&1 || true
    elif command -v apk >/dev/null 2>&1; then (apk add --no-cache python3) >/dev/null 2>&1 || true
    elif command -v brew >/dev/null 2>&1; then (brew install python3) >/dev/null 2>&1 || true
    fi
    PY="$(command -v python3 || true)"
fi
[ -n "$PY" ] || { err "未能准备 Python3，保留现有版本并退出。"; exit 1; }

step "安装程序到 ${APP_DIR}"
mkdir -p "$AB_ROOT"
NEW_APP="${AB_ROOT}/app.new.$$"
OLD_APP="${AB_ROOT}/app.old.$$"
rm -rf "$NEW_APP" "$OLD_APP"
mkdir -p "$NEW_APP"
cp -R "${SRC_DIR}/." "$NEW_APP/"
if [ ! -f "$NEW_APP/core/menu.py" ] || [ ! -f "$NEW_APP/core/agent.py" ] || [ ! -f "$NEW_APP/core/launch.py" ]; then
    err "安装包结构无效，保留现有版本"
    rm -rf "$NEW_APP"
    exit 1
fi
if [ -d "$APP_DIR" ]; then mv "$APP_DIR" "$OLD_APP"; fi
if mv "$NEW_APP" "$APP_DIR"; then
    :
else
    err "切换新版本失败，正在恢复旧版本"
    [ -d "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR"
    rm -rf "$NEW_APP"
    exit 1
fi
chmod +x "${APP_DIR}/install.sh" 2>/dev/null || true

# ---------- 3. 生成命令行入口 ----------
step "创建命令：agentboot（控制台） / ab（内置 Agent）"
# 临时文件与目标同目录（可写时）——保证 mv 原子替换；sudo 场景用 mktemp + sudo install
if [ -n "$BIN_SUDO" ]; then
    TMP_BASE="$(mktemp -d)"
    trap 'rm -rf "$TMP_BASE"' EXIT
else
    mkdir -p "$BIN_DIR"
    TMP_BASE="$BIN_DIR"
fi
agentboot_tmp="${TMP_BASE}/.agentboot.new.$$"
ab_tmp="${TMP_BASE}/.ab.new.$$"
rm -f "$agentboot_tmp" "$ab_tmp"
cat > "$agentboot_tmp" <<EOF
#!/bin/sh
# AgentBoot 控制台
PYTHON="\$(command -v python3 || command -v python)"
exec "\$PYTHON" "\$HOME/.agentboot/app/core/launch.py" menu "\$@"
EOF
cat > "$ab_tmp" <<EOF
#!/bin/sh
# AgentBoot 内置最小 Agent
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
install_launcher "$agentboot_tmp" agentboot || { err "写入 launcher 失败：${BIN_DIR}/agentboot"; exit 1; }
install_launcher "$ab_tmp" ab || { err "写入 launcher 失败：${BIN_DIR}/ab"; exit 1; }
SWAP_COMMITTED=1
rm -rf "$OLD_APP"
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
ok "已写入 ${BIN_DIR}"

# ---------- 4. PATH 注册（幂等） ----------
# 注意：rc 文件不存在时必须先创建再追加——早期版本用 [ -f "$rc" ] 判断，
# 在新系统（root 无 ~/.bashrc）上会静默跳过，导致装完 agentboot 找不到命令。
case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *)
        BLOCK="# >>> agentboot >>>"
        for rc in "${HOME}/.bashrc" "${HOME}/.profile"; do
            [ -d "$HOME" ] || continue
            grep -q "$BLOCK" "$rc" 2>/dev/null && continue
            [ -f "$rc" ] || : > "$rc" 2>/dev/null || { err "无法创建 $rc，PATH 需手动配置"; continue; }
            if { echo ''; echo "$BLOCK";
                 echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
                 echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
                 echo 'done'; echo 'unset _d'; } >> "$rc" 2>/dev/null; then
                ok "PATH 已写入 $rc（重开终端生效）"
            else
                err "无法写入 $rc，请手动把 ${BIN_DIR} 加入 PATH"
            fi
        done
        if ! grep -q "$BLOCK" "${HOME}/.zshrc" 2>/dev/null; then
            [ -d "$HOME" ] || HOME_ZSHRC_SKIP=1
            if [ -z "${HOME_ZSHRC_SKIP:-}" ]; then
                [ -f "${HOME}/.zshrc" ] || : > "${HOME}/.zshrc" 2>/dev/null || true
                if [ -f "${HOME}/.zshrc" ]; then
                    { echo ''; echo "$BLOCK";
                      echo 'for _d in "$HOME/.local/bin" "$HOME/.agentboot/bin"; do'
                      echo '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac'
                      echo 'done'; echo 'unset _d'; } >> "${HOME}/.zshrc" 2>/dev/null \
                        && ok "PATH 已写入 ~/.zshrc（重开终端生效）" || true
                fi
            fi
        fi
        ;;
esac

# ---------- 6. 体检 ----------
step "环境体检"
"$PY" "${APP_DIR}/core/agent.py" doctor 2>/dev/null || true

# ---------- 7. 完成 ----------
say ""
say "=============================================="
ok  "AgentBoot 安装完成！"
say ""
say "  如何启动："
say "    控制台菜单 : agentboot        （装/卸 Agent、镜像、模型配置）"
say "    内置 Agent : ab              （直接对话，默认 Groq qwen/qwen3.8-27b）"
say "    安装其他 Agent：运行 agentboot → 选 [2] 在线安装"
say ""
say "  模型说明：ab 默认用 Groq（qwen/qwen3.8-27b，极速推理）；未配置 Groq"
say "  API Key 时自动改用 Agnes 免费模型备选，两种方式都能直接对话。"
say ""
case ":$PATH:" in
    *":${BIN_DIR}:"*)
        say "  ✓ ${BIN_DIR} 已在 PATH 中——当前终端直接输入 agentboot 即可启动，"
        say "    无需 source、无需重开终端。"
        ;;
    *)
        if grep -q "# >>> agentboot >>>" "${HOME}/.bashrc" 2>/dev/null; then
            say "  PATH 已写入 ~/.bashrc。当前终端立即生效请执行："
            say "      source ~/.bashrc"
            say "  或者直接关掉本终端、重开一个（新终端自动生效）。"
        else
            say "  未能自动写入 shell 配置。当前终端立即生效请执行："
            say "      export PATH=\"${BIN_DIR}:\$PATH\""
            say "  并建议把上面这行追加到 ~/.bashrc，以后新终端自动生效。"
        fi
        ;;
esac
say "=============================================="

# 交互终端时询问是否直接打开菜单。
# 注意：curl | sh 安装时本脚本的 stdin 是已耗尽的管道，菜单必须改从
# /dev/tty 读输入，否则菜单一启动就遇到 EOF 直接退出（实测踩过）。
if [ -n "$PY" ] && [ -e /dev/tty ] && [ -t 2 ]; then
    printf '是否现在打开控制台菜单? [Y/n] '
    read ans < /dev/tty || ans="n"
    case "$ans" in
        n|N|no|NO) say "下次输入 agentboot 即可打开控制台。" ;;
        *) exec "$PY" "${APP_DIR}/core/menu.py" < /dev/tty ;;
    esac
fi
