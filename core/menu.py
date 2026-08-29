#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentBoot 控制台菜单（命令 agentboot）
================================
中文交互菜单：
  * 环境体检
  * 在线安装 Agent（菜单多选：Claude Code / Codex / Qwen Code / OpenCode / CodeBuddy / MiMo / Cline / Gemini CLI / iFlow ...）
  * 离线安装 Agent（从离线包 payloads/ 直接落盘，无需 npm）
  * 模型配置（Agnes 免费预设 / 自定义 OpenAI 兼容 / 本地 Ollama、LM Studio）
  * 镜像与代理设置（中国网络环境自适应：npmmirror 等）
也提供非交互子命令供脚本调用：
  python menu.py doctor
  python menu.py install claude-code,qwen-code
  python menu.py offline claude-code --payload /path/payloads
  python menu.py mirror auto|off|cn|proxy http://127.0.0.1:7890
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import platform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402  复用配置与模型能力

VERSION = "1.0.0"
APP_DIR = agent.APP_DIR
AB_HOME = agent.AB_HOME
RUNTIME_DIR = os.path.join(AB_HOME, "runtime")
AGENTS_DIR = os.path.join(AB_HOME, "agents")
NPM_PREFIX = os.path.join(AB_HOME, "npm-prefix")
ENV_JSON = os.path.join(AB_HOME, "env.json")

NODE_VERSION = "v22.14.0"
NPM_MIRROR = "https://registry.npmmirror.com"
NPM_OFFICIAL = "https://registry.npmjs.org"
NODE_MIRROR_CN = "https://registry.npmmirror.com/-/binary/node"
NODE_MIRROR_GLOBAL = "https://nodejs.org/dist"
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

POSIX = os.name != "nt"


# ---------------------------------------------------------------- 基础工具

def log_ok(msg):  print("✓ %s" % msg)
def log_err(msg): print("✗ %s" % msg)
def log_info(msg): print("· %s" % msg)


def plat_id():
    s = platform.system().lower()
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        arch = "x64"
    elif m in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "x64"
    return "%s-%s" % (s, arch)


def can_tcp(host, port=443, timeout=2.0):
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except Exception:
        return False


def python_ok(path):
    """验证 python 可真实执行（排除 Windows 商店的 python 存根）。"""
    if not path:
        return False
    try:
        r = subprocess.run([path, "-c", "print(1)"], capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def find_python():
    for cand in (shutil.which("python3"), shutil.which("python"), shutil.which("py")):
        if python_ok(cand):
            return cand
    return None


def cn_mode():
    """中国网络环境判定：环境变量优先，其次探测 npm 官方源连通性。"""
    forced = os.environ.get("AGENTBOOT_MIRROR", "").strip().lower()
    if forced in ("cn", "on", "1", "true"):
        return True
    if forced in ("off", "global", "0", "false"):
        return False
    return not can_tcp("registry.npmjs.org", 443, 1.5)


def load_env_json():
    try:
        with open(ENV_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_env_json(data):
    os.makedirs(AB_HOME, exist_ok=True)
    with open(ENV_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_registry():
    path = os.path.join(APP_DIR, "agents", "registry.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["agents"]


def runtime_node_dir():
    return os.path.join(RUNTIME_DIR, "node-%s" % plat_id())


def node_exe():
    d = runtime_node_dir()
    return os.path.join(d, "node.exe") if not POSIX else os.path.join(d, "bin", "node")


def npm_cmd():
    """优先系统 npm，其次运行时自带 npm。"""
    n = shutil.which("npm")
    if n:
        return n
    d = runtime_node_dir()
    cand = os.path.join(d, "npm.cmd") if not POSIX else os.path.join(d, "bin", "npm")
    return cand if os.path.exists(cand) else None


def child_env():
    env = dict(os.environ)
    nd = runtime_node_dir()
    if os.path.isdir(nd):
        env["PATH"] = (os.path.join(nd, "") if POSIX else nd + os.sep) + os.pathsep + \
                      (os.path.join(nd, "bin") + os.pathsep if POSIX else "") + env.get("PATH", "")
    p = load_env_json().get("proxy")
    if p:
        env.setdefault("HTTP_PROXY", p)
        env.setdefault("HTTPS_PROXY", p)
    return env


# ---------------------------------------------------------------- Node 运行时

def node_ok():
    try:
        out = subprocess.run([shutil.which("node") or node_exe(), "--version"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            major = int(re.match(r"v?(\d+)", out.stdout.strip()).group(1))
            return major >= 18
    except Exception:
        pass
    return False


def ensure_node():
    """确保 node>=18 可用；缺失时从镜像下载便携运行时到 ~/.agentboot/runtime。"""
    sysnode = shutil.which("node")
    if sysnode and node_ok():
        return sysnode
    if os.path.exists(node_exe()) and node_ok():
        return node_exe()

    pid = plat_id()
    cn = cn_mode()
    base = NODE_MIRROR_CN if cn else NODE_MIRROR_GLOBAL
    if pid.startswith("win"):
        fname = "node-%s-win-x64.zip" % NODE_VERSION
        inner = "node-%s-win-x64" % NODE_VERSION
    else:
        ext = "tar.gz" if pid.startswith("darwin") else "tar.xz"
        fname = "node-%s-%s.%s" % (NODE_VERSION, pid, ext)
        inner = "node-%s-%s" % (NODE_VERSION, pid)
    urls = ["/".join([base, NODE_VERSION, fname])]
    if cn:
        urls.append("/".join([NODE_MIRROR_GLOBAL, NODE_VERSION, fname]))
    else:
        urls.append("/".join([NODE_MIRROR_CN, NODE_VERSION, fname]))

    dest_parent = RUNTIME_DIR
    os.makedirs(dest_parent, exist_ok=True)
    archive = os.path.join(dest_parent, fname)
    import urllib.request
    ok = False
    for u in urls:
        try:
            log_info("下载 Node 运行时：%s" % u)
            req = urllib.request.Request(u, headers={"User-Agent": "AgentBoot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(archive, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            ok = True
            break
        except Exception as e:
            log_err("下载失败(%s)：%s" % (u, e))
    if not ok:
        return None
    log_info("解压到 %s …" % dest_parent)
    if fname.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest_parent)
    else:
        subprocess.run(["tar", "-xf", archive, "-C", dest_parent], check=True)
    if os.path.exists(runtime_node_dir()):
        import shutil as _sh
        _sh.rmtree(runtime_node_dir(), ignore_errors=True)
    os.replace(os.path.join(dest_parent, inner), runtime_node_dir())
    try:
        os.remove(archive)
    except OSError:
        pass
    if node_ok():
        return node_exe()
    return None


def ensure_npm_prefix():
    """POSIX 普通用户安装到 ~/.agentboot/npm-prefix，避免 sudo；Windows 用默认用户目录。"""
    if POSIX:
        try:
            root = os.geteuid() == 0
        except AttributeError:
            root = False
        if not root:
            os.makedirs(NPM_PREFIX, exist_ok=True)
            subprocess.run(["npm", "config", "set", "prefix", NPM_PREFIX],
                           env=child_env(), capture_output=True)
    return None


def prefix_bin_dirs():
    dirs = []
    if POSIX:
        dirs.append(os.path.join(NPM_PREFIX, "bin"))
    else:
        ap = os.environ.get("APPDATA")
        if ap:
            dirs.append(os.path.join(ap, "npm"))
    return [d for d in dirs if os.path.isdir(d)]


def find_bin(name):
    cands = [name + (".cmd" if not POSIX else "")] if not POSIX else [name]
    for d in prefix_bin_dirs():
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return shutil.which(name)


# ---------------------------------------------------------------- 在线安装

def npm_install(pkg):
    if not (shutil.which("npm") or npm_cmd()):
        got = ensure_node()
        if not got:
            log_err("需要 Node.js（无法自动下载，请检查网络或手动安装 Node 18+）")
            return False
    ensure_npm_prefix()
    cmd = [npm_cmd() or "npm", "install", "-g", pkg, "--no-audit", "--no-fund"]
    if cn_mode():
        cmd += ["--registry", NPM_MIRROR]
    log_info("$ %s" % " ".join(cmd))
    r = subprocess.run(cmd, env=child_env())
    return r.returncode == 0


def install_online(ids):
    agents = load_registry()
    by_id = {a["id"]: a for a in agents}
    ok_list, fail_list = [], []
    for aid in ids:
        a = by_id.get(aid)
        if not a:
            log_err("未知 Agent：%s（用 2 号菜单查看可用列表）" % aid)
            fail_list.append(aid)
            continue
        print("\n========== 安装 %s（%s）==========" % (a["name"], a.get("vendor", "")))
        print("  %s" % a.get("desc", ""))
        missing = [t for t in (a.get("requires") or []) if not shutil.which(t)]
        if missing:
            log_err("%s 需要前置依赖：%s。请先安装后重试（Windows 建议 https://git-scm.com，"
                    "Linux 用系统包管理器安装 git）" % (a["name"], " + ".join(missing)))
            fail_list.append(aid)
            continue
        method = a.get("method", "npm")
        ok = False
        if method == "npm":
            ok = npm_install(a["npm"])
        elif method == "script":
            ok = install_via_script(a)
        elif method == "pip":
            ok = install_via_pip(a)
        if ok and a.get("bin"):
            found = find_bin(a["bin"])
            if found:
                log_ok("%s 安装完成，命令：%s" % (a["name"], a["bin"]))
                ok_list.append(aid)
            else:
                log_err("%s 已执行安装，但未在 PATH 找到 %s，请重开终端后再试" % (a["name"], a["bin"]))
                fail_list.append(aid)
        elif ok:
            log_ok("%s 安装完成" % a["name"])
            ok_list.append(aid)
        else:
            log_err("%s 安装失败（可尝试菜单[3]离线安装，或检查网络/代理）" % a["name"])
            fail_list.append(aid)
        for note in a.get("notes", []) or []:
            print("  ℹ %s" % note)
    print("\n汇总：成功 %s · 失败 %s" % (ok_list or "无", fail_list or "无"))
    if not POSIX:
        print("提示：新安装的命令需要重新打开终端窗口才会进入 PATH。")
    return fail_list


def install_via_script(a):
    url = a.get("script")
    if not url:
        return False
    if POSIX:
        cmd = ["sh", "-c", 'curl -fsSL "%s" | sh' % url]
    else:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "iwr -useb %s | iex" % url]
    log_info("$ %s" % " ".join(cmd))
    return subprocess.run(cmd, env=child_env()).returncode == 0


def install_via_pip(a):
    py = shutil.which("python3") or shutil.which("python")
    if not py:
        log_err("需要 Python 3 与 pip")
        return False
    cmd = [py, "-m", "pip", "install", a["pip"], "-U"]
    if cn_mode():
        cmd += ["-i", PIP_MIRROR]
    log_info("$ %s" % " ".join(cmd))
    return subprocess.run(cmd).returncode == 0


# ---------------------------------------------------------------- 离线安装

def find_payload_dir(explicit=None):
    cands = []
    if explicit:
        cands.append(explicit)
    env_p = os.environ.get("AGENTBOOT_PAYLOAD")
    if env_p:
        cands.append(env_p)
    cands += [os.path.join(APP_DIR, "payloads"), os.path.join(os.getcwd(), "payloads")]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "agents")):
            return c
    return None


def offline_install(ids, payload_dir=None):
    pdir = find_payload_dir(payload_dir)
    if not pdir:
        log_err("未找到离线包 payloads/ 目录。请确认已解压完整离线安装包，"
                "或用 --payload 指定路径。")
        return [i for i in ids]
    pid = plat_id()
    print("离线安装 · 平台 %s · 载荷目录 %s" % (pid, pdir))

    # 1) Node 运行时（系统没有 node 时启用内置运行时）
    have_node = bool(shutil.which("node")) and node_ok()
    if not have_node:
        src_node = os.path.join(pdir, "node", pid)
        if os.path.isdir(src_node):
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            dst_node = runtime_node_dir()
            if os.path.exists(dst_node):
                shutil.rmtree(dst_node, ignore_errors=True)
            log_info("部署内置 Node 运行时 …")
            shutil.copytree(src_node, dst_node)
            if node_ok():
                have_node = True
                log_ok("内置 Node 就绪：%s" % node_exe())
            else:
                log_err("内置 Node 校验失败")
        else:
            log_err("离线包未包含 %s 的 Node 运行时，且系统无 Node，无法安装 npm 类 Agent" % pid)

    # 2) Windows：部署内置 Python（供 ab 使用，若系统无可用 python）
    if not POSIX and not find_python():
        emb = os.path.join(pdir, "python", "win-embed.zip")
        if os.path.exists(emb):
            dst_py = os.path.join(RUNTIME_DIR, "python")
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            import zipfile
            with zipfile.ZipFile(emb) as z:
                z.extractall(dst_py)
            log_ok("内置 Python 就绪：%s" % os.path.join(dst_py, "python.exe"))

    # 3) 逐个 Agent 落盘
    agents = {a["id"]: a for a in load_registry()}
    ok_list, fail_list = [], []
    for aid in ids:
        a = agents.get(aid)
        if not a:
            log_err("未知 Agent：%s" % aid)
            fail_list.append(aid)
            continue
        src = os.path.join(pdir, "agents", aid, pid, "node_modules")
        if not (a.get("method") == "npm" and os.path.isdir(src)):
            log_err("%s：离线包中没有 %s 平台的载荷（该 Agent 可能不适合离线安装）" % (a["name"], pid))
            fail_list.append(aid)
            continue
        if not have_node:
            log_err("%s：缺少 Node 运行时，无法离线安装" % a["name"])
            fail_list.append(aid)
            continue
        dst = os.path.join(AGENTS_DIR, aid)
        os.makedirs(dst, exist_ok=True)
        dst_nm = os.path.join(dst, "node_modules")
        if os.path.exists(dst_nm):
            shutil.rmtree(dst_nm, ignore_errors=True)
        log_info("部署 %s（约 %.1f MB）…" % (a["name"], dir_size_mb(src)))
        shutil.copytree(src, dst_nm)
        shim = write_shim(a)
        if shim:
            log_ok("%s 离线安装完成，命令：%s" % (a["name"], a["bin"]))
            ok_list.append(aid)
        else:
            fail_list.append(aid)
        for note in a.get("notes", []) or []:
            print("  ℹ %s" % note)
    ensure_path_registered()
    print("\n汇总：成功 %s · 失败 %s" % (ok_list or "无", fail_list or "无"))
    print("提示：新命令需重新打开终端进入 PATH。")
    return fail_list


def dir_size_mb(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1048576.0


def write_shim(a):
    """为离线安装的 Agent 生成启动 shim。"""
    aid, bin_ = a["id"], a["bin"]
    try:
        if POSIX:
            bin_dir = os.path.join(AB_HOME, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            path = os.path.join(bin_dir, bin_)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(
                    "#!/bin/sh\n"
                    '# AgentBoot shim for %s\n'
                    'AB_ROOT="$HOME/.agentboot"\n'
                    'ND="$AB_ROOT/runtime/node-%s"\n'
                    '[ -x "$ND/bin/node" ] && export PATH="$ND/bin:$PATH"\n'
                    'export PATH="$AB_ROOT/agents/%s/node_modules/.bin:$PATH"\n'
                    'exec "%s" "$@"\n' % (aid, plat_id(), aid, bin_)
                )
            os.chmod(path, 0o755)
        else:
            bin_dir = os.path.join(AB_HOME, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            path = os.path.join(bin_dir, bin_ + ".cmd")
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "@echo off\r\n"
                    "rem AgentBoot shim for %s\r\n"
                    'set "AB_ROOT=%%USERPROFILE%%\\.agentboot"\r\n'
                    'if exist "%%AB_ROOT%%\\runtime\\node-win-x64\\node.exe" set "PATH=%%AB_ROOT%%\\runtime\\node-win-x64;%%PATH%%"\r\n'
                    'set "PATH=%%AB_ROOT%%\\agents\\%s\\node_modules\\.bin;%%PATH%%"\r\n'
                    '%s %%*\r\n' % (aid, aid, bin_)
                )
        return True
    except Exception as e:
        log_err("写入 shim 失败：%s" % e)
        return False


def ensure_path_registered():
    """把 AgentBoot 相关目录加入用户 PATH（幂等）。"""
    targets = [os.path.join(AB_HOME, "bin")] + (prefix_bin_dirs() if POSIX else [])
    if POSIX:
        block_begin = "# >>> agentboot >>>"
        block_end = "# <<< agentboot <<<"
        block = "\n".join([block_begin,
                           '# AgentBoot 添加的 PATH',
                           'for _d in "$HOME/.agentboot/bin" "$HOME/.local/bin" "%s"; do' % NPM_PREFIX,
                           '  [ -d "$_d" ] && case ":$PATH:" in *":$_d:"*) ;; *) export PATH="$_d:$PATH";; esac',
                           'done',
                           'unset _d',
                           block_end, ""])
        for rc in [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.profile"),
                   os.path.expanduser("~/.zshrc")]:
            try:
                content = ""
                if os.path.exists(rc):
                    with open(rc, "r", encoding="utf-8") as f:
                        content = f.read()
                if block_begin in content:
                    continue
                with open(rc, "a", encoding="utf-8") as f:
                    f.write("\n" + block)
            except Exception:
                pass
    else:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE)
            try:
                cur, typ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                cur, typ = "", winreg.REG_EXPAND_SZ
            parts = [p for p in cur.split(";") if p]
            changed = False
            for t in targets:
                t = os.path.normpath(t)
                if t.lower() not in [p.lower() for p in parts]:
                    parts.insert(0, t)
                    changed = True
            if changed:
                winreg.SetValueEx(key, "Path", 0, typ, ";".join(parts))
            winreg.CloseKey(key)
            os.environ["PATH"] = ";".join(targets + [os.environ.get("PATH", "")])
        except Exception as e:
            log_err("更新用户 PATH 失败：%s（可手动把 %s 加入 PATH）" % (e, os.path.join(AB_HOME, "bin")))


# ---------------------------------------------------------------- 镜像与代理

def npm_current_registry():
    try:
        r = subprocess.run([npm_cmd() or "npm", "config", "get", "registry"],
                           capture_output=True, text=True, timeout=20, env=child_env())
        return r.stdout.strip()
    except Exception:
        return "?"


def set_npm_registry(url):
    if not npm_cmd():
        log_err("npm 不可用（先安装 Node 或让菜单下载运行时）")
        return
    subprocess.run([npm_cmd(), "config", "set", "registry", url], env=child_env())
    log_ok("npm registry 已设为 %s" % url)


def set_proxy(url=None):
    data = load_env_json()
    if url:
        data["proxy"] = url
        save_env_json(data)
        if npm_cmd():
            subprocess.run([npm_cmd(), "config", "set", "proxy", url], env=child_env(), capture_output=True)
            subprocess.run([npm_cmd(), "config", "set", "https-proxy", url], env=child_env(), capture_output=True)
        write_env_scripts(url)
        log_ok("代理已保存：%s" % url)
        print("  也可在 shell 中执行：")
        if POSIX:
            print('    export HTTP_PROXY=%s HTTPS_PROXY=%s' % (url, url))
        else:
            print('    setx HTTP_PROXY %s' % url)
    else:
        data.pop("proxy", None)
        save_env_json(data)
        if npm_cmd():
            subprocess.run([npm_cmd(), "config", "delete", "proxy"], env=child_env(), capture_output=True)
            subprocess.run([npm_cmd(), "config", "delete", "https-proxy"], env=child_env(), capture_output=True)
        try:
            os.remove(os.path.join(AB_HOME, "env.sh"))
            os.remove(os.path.join(AB_HOME, "env.ps1"))
        except OSError:
            pass
        log_ok("代理已清除")


def write_env_scripts(url):
    with open(os.path.join(AB_HOME, "env.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write("export HTTP_PROXY=%s\nexport HTTPS_PROXY=%s\n" % (url, url))
    with open(os.path.join(AB_HOME, "env.ps1"), "w", encoding="utf-8") as f:
        f.write("$env:HTTP_PROXY='%s'\n$env:HTTPS_PROXY='%s'\n" % (url, url))


def mirror_status():
    cn = cn_mode()
    print("网络判定      : %s" % ("中国大陆网络（自动启用镜像）" if cn else "国际网络（官方源可达）"))
    print("npm registry  : %s" % npm_current_registry())
    print("npmmirror 可达: %s" % ("✓" if can_tcp("registry.npmmirror.com") else "✗"))
    print("npmjs 可达    : %s" % ("✓" if can_tcp("registry.npmjs.org", 443, 1.5) else "✗"))
    env = load_env_json()
    print("HTTP 代理     : %s" % (env.get("proxy") or os.environ.get("HTTPS_PROXY") or "未设置"))
    print("镜像开关      : AGENTBOOT_MIRROR=%s" % (os.environ.get("AGENTBOOT_MIRROR") or "自动"))


# ---------------------------------------------------------------- 环境体检

def doctor():
    print("AgentBoot 环境体检 v%s · 平台 %s" % (VERSION, plat_id()))
    print("-" * 52)
    py = shutil.which("python3") or shutil.which("python")
    print("Python : %s" % (py or "未安装（Windows 会自动用内置运行时）"))
    node = shutil.which("node") or (node_exe() if os.path.exists(node_exe()) else None)
    print("Node   : %s" % (node or "未安装（安装 Agent 时会自动下载 v22 运行时）"))
    print("npm    : %s" % (npm_cmd() or "未安装"))
    print("git    : %s" % (shutil.which("git") or "未安装（可选）"))
    print("curl   : %s" % (shutil.which("curl") or "未安装（可选）"))
    print("-" * 52)
    mirror_status()
    print("-" * 52)
    try:
        agents = load_registry()
        print("可安装 Agent（%d 个）：" % len(agents))
        for a in agents:
            installed = bool(find_bin(a.get("bin") or ""))
            mark = "已安装" if installed else "未安装"
            print("  %-14s %-22s [%s]" % (a["id"], a["name"], mark))
    except Exception as e:
        log_err("读取 Agent 注册表失败：%s" % e)
    pdir = find_payload_dir()
    print("离线载荷     : %s" % (pdir or "未找到（离线安装功能需解压完整离线包）"))
    print("-" * 52)
    agent.doctor(agent.load_config())


# ---------------------------------------------------------------- 交互菜单

def pick_agents(agents, title):
    print("\n%s" % title)
    for i, a in enumerate(agents, 1):
        offline_mark = "可离线" if a.get("offline") else "仅在线"
        print("  [%2d] %-16s %-24s (%s) %s" % (i, a["id"], a["name"], offline_mark, a.get("desc", "")))
    print("  [ a] 全选 npm 类 · [ 0] 返回")
    raw = input("输入编号（可多选，空格/逗号分隔）: ").strip().lower()
    if not raw or raw == "0":
        return []
    if raw == "a":
        return [a["id"] for a in agents if a.get("method") == "npm"]
    ids = []
    for tok in re.split(r"[\s,，]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(agents):
            ids.append(agents[int(tok) - 1]["id"])
        elif tok in [a["id"] for a in agents]:
            ids.append(tok)
    return sorted(set(ids), key=lambda x: [a["id"] for a in agents].index(x))


def menu_model(cfg):
    while True:
        p = agent.get_provider(cfg)
        print("\n---- 模型配置 ----")
        print("当前：%s · %s @ %s" % (p["name"], p.get("model"), p.get("base_url")))
        print(" [1] 使用 Agnes 免费模型（官方预设，推荐）")
        print(" [2] 自定义 OpenAI 兼容接口（中转/私有部署）")
        print(" [3] 本地 Ollama（http://127.0.0.1:11434/v1）")
        print(" [4] 本地 LM Studio（http://127.0.0.1:1234/v1）")
        print(" [5] 测试当前模型连通性")
        print(" [6] 查看当前配置")
        print(" [0] 返回")
        c = input("选择: ").strip()
        if c == "1":
            cfg["active"] = "agnes"
            agent.save_config(cfg)
            log_ok("已切换到 Agnes 免费模型")
        elif c == "2":
            print("示例：Agnes=https://apihub.agnes-ai.com/v1 · vLLM=http://1.2.3.4:8000/v1 · OpenAI=https://api.openai.com/v1")
            base = input("Base URL: ").strip()
            key = input("API Key（可留空）: ").strip()
            model = input("模型 ID: ").strip()
            if base and model:
                agent.set_provider(cfg, "custom", base, key, model)
                log_ok("已保存自定义模型")
            else:
                log_err("Base URL 与模型 ID 不能为空")
        elif c == "3":
            model = input("Ollama 模型名（回车=qwen2.5:7b）: ").strip() or "qwen2.5:7b"
            agent.set_provider(cfg, "ollama", "http://127.0.0.1:11434/v1", "", model)
            log_ok("已切换到 Ollama（请确保已 ollama pull 模型）")
        elif c == "4":
            model = input("LM Studio 模型名（回车=local-model）: ").strip() or "local-model"
            agent.set_provider(cfg, "lmstudio", "http://127.0.0.1:1234/v1", "", model)
            log_ok("已切换到 LM Studio（请确保服务已启动）")
        elif c == "5":
            print("⏳ 测试中 …")
            ok, msg = agent.test_provider(cfg)
            log_ok("连通正常：%s" % msg) if ok else log_err("失败：%s" % msg)
        elif c == "6":
            agent.show_status(cfg)
        else:
            return


def menu_mirror():
    while True:
        print("\n---- 镜像与代理 ----")
        mirror_status()
        print(" [1] 切换 npm 到 npmmirror 镜像（国内推荐）")
        print(" [2] 恢复 npm 官方源")
        print(" [3] 设置 HTTP 代理（npm + AgentBoot 下载共用）")
        print(" [4] 清除代理")
        print(" [0] 返回")
        c = input("选择: ").strip()
        if c == "1":
            set_npm_registry(NPM_MIRROR)
        elif c == "2":
            set_npm_registry(NPM_OFFICIAL)
        elif c == "3":
            url = input("代理地址（如 http://127.0.0.1:7890）: ").strip()
            if url:
                set_proxy(url)
        elif c == "4":
            set_proxy(None)
        else:
            return


def banner():
    print(r"""
    _                    _            _
   /_\   __ _  ___ _ __ | |_ __ _  __| | ___
  //_\\ / _` |/ _ \ '_ \| __/ _` |/ _` |/ _ \
 /  _  \ (_| |  __/ | | | || (_| | (_| |  __/
 \_/ \_/\__, |\___|_| |_|\__\__,_|\__,_|\___|
        |___/   AgentBoot 控制台 v%s
""" % VERSION)
    print("极简 · 极速 · 开箱即用的 AI Agent 启动器（默认 Agnes 免费模型）\n")


def main_menu():
    cfg = agent.load_config()
    agents = load_registry()
    while True:
        banner()
        print("  [1] 环境体检（推荐先跑一次）")
        print("  [2] 在线安装 Agent（菜单多选）")
        print("  [3] 离线安装 Agent（需离线安装包）")
        print("  [4] 模型配置（Agnes 免费预设 / 自定义 / 本地模型）")
        print("  [5] 镜像与代理设置（中国网络自适应）")
        print("  [6] 启动内置 Agent（ab）")
        print("  [0] 退出")
        c = input("\n选择: ").strip()
        if c == "1":
            doctor()
            input("\n回车返回 …")
        elif c == "2":
            ids = pick_agents(agents, "---- 在线安装 Agent ----")
            if ids:
                install_online(ids)
                input("\n回车返回 …")
        elif c == "3":
            ids = pick_agents([a for a in agents if a.get("offline")], "---- 离线安装 Agent（仅列出支持离线的）----")
            if ids:
                offline_install(ids)
                input("\n回车返回 …")
        elif c == "4":
            menu_model(cfg)
        elif c == "5":
            menu_mirror()
            input("\n回车返回 …")
        elif c == "6":
            agent.repl(cfg)
        elif c == "0":
            print("再见！")
            return


def main():
    agent._utf8_console()
    argv = sys.argv[1:]
    if not argv:
        main_menu()
        return
    cmd = argv[0]
    if cmd == "doctor":
        doctor()
    elif cmd == "install":
        ids = [t for t in re.split(r"[,\s]+", " ".join(argv[1:])) if t and not t.startswith("-")]
        install_online(ids) if ids else print("用法: menu.py install claude-code qwen-code")
    elif cmd == "offline":
        payload = None
        if "--payload" in argv:
            i = argv.index("--payload")
            payload = argv[i + 1] if i + 1 < len(argv) else None
            rest = argv[1:i] + argv[i + 2:]
        else:
            rest = argv[1:]
        ids = [t for t in re.split(r"[,\s]+", " ".join(rest)) if t and not t.startswith("-")]
        offline_install(ids, payload) if ids else print("用法: menu.py offline claude-code --payload <dir>")
    elif cmd == "mirror":
        arg = argv[1] if len(argv) > 1 else "auto"
        if arg == "auto":
            os.environ.pop("AGENTBOOT_MIRROR", None)
            mirror_status()
        elif arg == "cn":
            os.environ["AGENTBOOT_MIRROR"] = "cn"
            set_npm_registry(NPM_MIRROR)
        elif arg == "off":
            os.environ["AGENTBOOT_MIRROR"] = "off"
            mirror_status()
        elif arg == "proxy":
            set_proxy(argv[2] if len(argv) > 2 else None)
        else:
            print("用法: menu.py mirror auto|cn|off|proxy [url]")
    elif cmd in ("version", "--version"):
        print("AgentBoot 控制台 v%s" % VERSION)
    elif cmd == "menu":
        main_menu()
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n（已退出）")
