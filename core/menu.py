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

CUSTOM_AGENTS = os.path.join(AB_HOME, "custom-agents.json")

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
    """内置注册表 + 用户自定义（custom-agents.json），同名 id 以先出现的内置为准。"""
    path = os.path.join(APP_DIR, "agents", "registry.json")
    with open(path, "r", encoding="utf-8") as f:
        agents = json.load(f)["agents"]
    builtin_ids = {a["id"] for a in agents}
    for c in load_custom_agents():
        if c.get("id") in builtin_ids:
            continue
        c["custom"] = True
        agents.append(c)
    return agents


def load_custom_agents():
    try:
        with open(CUSTOM_AGENTS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_custom_agents(items):
    os.makedirs(AB_HOME, exist_ok=True)
    with open(CUSTOM_AGENTS, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def custom_add_entry(entry):
    """添加一条自定义 Agent（id 重复时拒绝）。返回是否成功。"""
    items = load_custom_agents()
    entry["offline"] = False
    entry.setdefault("vendor", "自定义")
    items.append(entry)
    save_custom_agents(items)


def custom_remove_entry(aid):
    items = [a for a in load_custom_agents() if a.get("id") != aid]
    save_custom_agents(items)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "custom"


def custom_add_wizard():
    """交互式添加自定义 Agent 向导。返回新 id 或 None。"""
    print("\n---- 添加自定义 Agent ----")
    print("安装方式：[1] npm 包  [2] pip 包  [3] 安装脚本 URL")
    m = {"1": "npm", "2": "pip", "3": "script"}.get(input("选择: ").strip())
    if not m:
        log_err("无效方式")
        return None
    if m == "npm":
        pkg = input("npm 包名（如 @scope/xxx）: ").strip()
    elif m == "pip":
        pkg = input("pip 包名: ").strip()
    else:
        pkg = input("安装脚本 URL: ").strip()
    if not pkg:
        log_err("不能为空")
        return None
    default_id = _slug(pkg.split("/")[-1])
    aid = input("id（回车=%s）: " % default_id).strip() or default_id
    name = input("显示名（回车=%s）: " % aid).strip() or aid
    default_bin = pkg.split("/")[-1].split("@")[-1] if m == "npm" else aid
    bin_ = input("安装后的命令（回车=%s）: " % default_bin).strip() or default_bin
    entry = {"id": aid, "name": name, "desc": "自定义 Agent", "bin": bin_, "method": m,
             "requires": [], "notes": ["用户自定义条目"]}
    if m == "npm":
        entry["npm"] = pkg
    elif m == "pip":
        entry["pip"] = pkg
    else:
        entry["script"] = pkg
    custom_add_entry(entry)
    log_ok("已保存到 %s" % CUSTOM_AGENTS)
    return aid


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
        if os.path.isdir(runtime_node_dir()):
            dirs.append(runtime_node_dir())
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
        os_limits = a.get("os") or []
        if os_limits and plat_id().split("-")[0] not in os_limits:
            log_err("%s 官方仅支持 %s，当前平台 %s 不在其列"
                    % (a["name"], "/".join(os_limits), plat_id()))
            fail_list.append(aid)
            continue
        method = a.get("method", "npm")
        ok = False
        if a.get("special_install") == "hermes":
            log_info("使用 hermes 专用安装流程（自动适配网络）")
            ok = install_hermes_special(a)
            if not ok:
                log_err("专用流程失败：可检查 Git 是否安装、或配置代理后重试")
        elif method == "npm":
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
    ensure_path_registered()
    return fail_list


def install_via_script(a):
    url = a.get("script")
    if not url:
        return False
    urls = [url]
    if cn_mode():
        for p in ("https://gh-proxy.com/", "https://ghfast.top/"):
            urls.append(p + url)
    for u in urls:
        if POSIX:
            cmd = ["sh", "-c", 'curl -fsSL "%s" | sh' % u]
        else:
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                   "iwr -useb %s | iex" % u]
        log_info("$ %s" % " ".join(cmd))
        if subprocess.run(cmd, env=child_env()).returncode == 0:
            return True
        log_err("该脚本地址不可用，尝试下一个源 …")
    return False


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


# ---------------------------------------------------------------- hermes-agent 国内专用安装

def _npm_global_root(env):
    try:
        r = subprocess.run([npm_cmd() or "npm", "root", "-g"], capture_output=True,
                           text=True, timeout=60, env=env)
        return r.stdout.strip()
    except Exception:
        return ""


def _hermes_uv_meta(pkg_root):
    """从已安装的 uv-installer.js 解析 UV_VERSION 与当前平台的 uv 资产名/sha256。"""
    import re as _re
    path = os.path.join(pkg_root, "lib", "uv-installer.js")
    try:
        text = open(path, "r", encoding="utf-8").read()
    except OSError:
        return None, None, None
    m = _re.search(r'UV_VERSION\s*=\s*"([^"]+)"', text)
    version = m.group(1) if m else None
    if sys.platform == "win32":
        target = "aarch64-pc-windows-msvc" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64-pc-windows-msvc"
        asset = "uv-%s.zip" % target
        member = "uv.exe"
    else:
        target = ("aarch64-apple-darwin" if platform.machine().lower() in ("arm64", "aarch64")
                  else "x86_64-apple-darwin") if sys.platform == "darwin" else (
                  "aarch64-unknown-linux-gnu" if platform.machine().lower() in ("arm64", "aarch64")
                  else "x86_64-unknown-linux-gnu")
        asset = "uv-%s.tar.gz" % target
        member = target + "/uv"
    m = _re.search(r'"%s":\s*"([0-9a-f]{64})"' % _re.escape(asset), text)
    sha = m.group(1) if m else None
    return version, (asset, member), sha


def _download_mirror(urls, dest):
    import urllib.request
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "AgentBoot/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            return True
        except Exception:
            continue
    return False


def _seed_uv(pkg_root):
    """预置 uv 二进制到 <pkg>/.uv_bin 并写入 marker，绕过 postinstall 的 GitHub 直连下载。"""
    import tarfile
    import zipfile
    version, asset_info, sha = _hermes_uv_meta(pkg_root)
    if not (version and asset_info and sha):
        log_err("无法解析 hermes uv 安装参数（包结构变化？），回退官方流程")
        return False
    asset, member = asset_info
    uv_dir = os.path.join(pkg_root, ".uv_bin")
    exe = os.path.join(uv_dir, "uv.exe" if sys.platform == "win32" else "uv")
    marker = os.path.join(uv_dir, "install.json")
    if os.path.exists(marker) and os.path.exists(exe):
        try:
            m = json.load(open(marker, "r", encoding="utf-8"))
            if m.get("version") == version and m.get("sha256") == sha:
                return True  # 已预置
        except Exception:
            pass
    base = "https://github.com/astral-sh/uv/releases/download/%s/%s" % (version, asset)
    urls = [base]
    for p in ("https://ghfast.top/", "https://gh-proxy.com/"):
        urls.append(p + base)
    os.makedirs(uv_dir, exist_ok=True)
    archive = os.path.join(uv_dir, asset)
    log_info("从镜像下载 uv %s …" % version)
    if not _download_mirror(urls, archive):
        log_err("uv 镜像下载失败")
        return False
    if asset.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            data = z.read(member)
    else:
        with tarfile.open(archive, "r:gz") as t:
            data = t.extractfile(member).read()
    with open(exe, "wb") as f:
        f.write(data)
    if POSIX:
        os.chmod(exe, 0o755)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"version": version, "asset": asset, "sha256": sha}, f, indent=2)
    try:
        os.remove(archive)
    except OSError:
        pass
    log_ok("uv 已就绪（%.1f MB，镜像预置）" % (len(data) / 1048576.0))
    return True


def _github_git_reachable():
    """探测 github.com 的 git 端点是否可用（决定 hermes 安装是否启用镜像重写）。"""
    try:
        r = subprocess.run(["git", "ls-remote", "https://github.com/NousResearch/hermes-agent.git", "HEAD"],
                           capture_output=True, timeout=30, env=child_env())
        return r.returncode == 0
    except Exception:
        return False


def install_hermes_special(a):
    """hermes-agent：分步安装（包体 → uv 预置 → postinstall，git/Python/PyPI 自动适配网络）。"""
    # 1) 包体（跳过会直连 GitHub 的 postinstall）
    cmd = [npm_cmd() or "npm", "install", "--ignore-scripts", "-g", a["npm"], "--no-audit", "--no-fund"]
    if cn_mode():
        cmd += ["--registry", NPM_MIRROR]
    log_info("$ %s" % " ".join(cmd))
    env = child_env()
    if subprocess.run(cmd, env=env).returncode != 0:
        return False
    root = _npm_global_root(env)
    pkg_root = os.path.join(root, "hermes-agent")
    if not os.path.isdir(pkg_root):
        log_err("未定位到 hermes-agent 包目录")
        return False
    # 2) 预置 uv（官方地址优先，镜像兜底）
    if not _seed_uv(pkg_root):
        return False
    # 3) 执行官方 postinstall：git 不可达时启用镜像重写；Python/PyPI 镜像对全球用户同样可用
    env = child_env()
    if not _github_git_reachable():
        log_info("github.com git 端点不可达：启用镜像重写")
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.https://gh-proxy.com/https://github.com/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://github.com/",
        })
    env.update({
        "UV_PYTHON_INSTALL_MIRROR": "https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download",
        "UV_HTTP_TIMEOUT": "180",
    })
    node = shutil.which("node") or node_exe()
    script = os.path.join(pkg_root, "scripts", "postinstall.js")
    r = subprocess.run([node, script], env=env)
    return r.returncode == 0


# ---------------------------------------------------------------- 离线安装

def fixup_hermes_venv(payload_plat_dir, dst_nm):
    """hermes 离线载荷：三变体路径替换（原始/JSON 转义/正斜杠）+ 生成直调入口 runpy。

    载荷在打包机完成 postinstall（含 venv），但 venv 的 .exe 启动器内嵌打包机绝对路径
    无法搬移，因此安装后改写 pyvenv.cfg / editable finder / 状态文件的路径，
    并用 venv python 直调 hermes_cli.main 的 runpy 绕过 .exe 启动器。
    """
    marker = os.path.join(payload_plat_dir, "PACK_ROOT.txt")
    if not os.path.exists(marker):
        log_err("hermes 载荷缺少 PACK_ROOT.txt（旧版载荷），跳过 venv 路径修复")
        return
    old_root = open(marker, "r", encoding="utf-8").read().strip().rstrip("\\/")
    new_root = os.path.join(dst_nm, "hermes-agent")
    old_variants = [old_root, old_root.replace("\\", "\\\\"), old_root.replace("\\", "/")]
    new_variants = [new_root, new_root.replace("\\", "\\\\"), new_root.replace("\\", "/")]
    text_ext = {".json", ".cfg", ".txt", ".cmd", ".sh", ".ps1", ".py", ".js", ".mjs", ".cjs",
                ".ini", ".toml", ".yaml", ".yml", ".md", ".bat", ".nu", ""}
    names = {"activate", "activate.bat", "activate.csh", "activate.fish", "activate.nu"}
    fixed = 0
    for base, _dirs, files in os.walk(dst_nm):
        for fn in files:
            p = os.path.join(base, fn)
            ext = os.path.splitext(fn)[1].lower()
            if ext not in text_ext and fn not in names:
                continue
            try:
                if os.path.getsize(p) > 3 * 1024 * 1024:
                    continue
                t = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if not any(v in t for v in old_variants):
                continue
            for v, nv in zip(old_variants, new_variants):
                t = t.replace(v, nv)
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(t)
            fixed += 1
    log_ok("hermes 离线路径修复：%d 个文件" % fixed)

    # 直调入口 runpy（绕过内嵌绝对路径的 .exe 启动器）
    runpy = os.path.join(AGENTS_DIR, "hermes", "hermes-run.py")
    with open(runpy, "w", encoding="utf-8", newline="\n") as f:
        f.write("import sys\nfrom hermes_cli.main import main\nsys.exit(main())\n")


def coco_offline_install(a, payload):
    """CoCo 离线安装（Linux/macOS）：本地复刻官方安装步骤，不联网。"""
    import hashlib
    import tarfile
    tgz = os.path.join(payload, "coco-0.8.0.tgz")
    side = tgz + ".sha256"
    key_file = os.path.join(payload, "agnes.key")
    if not (os.path.exists(tgz) and os.path.exists(side) and os.path.exists(key_file)):
        log_err("CoCo 离线载荷不完整（缺 coco-0.8.0.tgz / .sha256 / agnes.key）")
        return False
    expected = open(side, "r", encoding="utf-8").read().split()[0].lower()
    h = hashlib.sha256(open(tgz, "rb").read()).hexdigest()
    if h != expected:
        log_err("CoCo 发行包 SHA-256 校验失败")
        return False
    log_ok("CoCo 发行包校验通过")

    home = os.path.expanduser("~")
    install_dir = os.path.join(home, ".coco")
    bin_dir = os.path.join(AB_HOME, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    # Node：系统 >=22.19 优先，否则用载荷内置 Node 22.23.2
    def _node_ok(p):
        try:
            out = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=15)
            major, minor = re.match(r"v?(\d+)\.(\d+)", out.stdout.strip()).groups()
            return (int(major), int(minor)) >= (22, 19)
        except Exception:
            return False

    node_bin = shutil.which("node")
    if node_bin and _node_ok(node_bin):
        log_ok("使用系统 Node")
    else:
        ntgz = next((os.path.join(payload, f) for f in os.listdir(payload)
                     if f.startswith("node-v") and f.endswith(".tar.gz")), None)
        if not ntgz:
            log_err("系统 Node 过旧且载荷无内置 Node 运行时")
            return False
        runtime = os.path.join(install_dir, "runtime")
        if os.path.isdir(runtime):
            shutil.rmtree(runtime, ignore_errors=True)
        os.makedirs(runtime, exist_ok=True)
        with tarfile.open(ntgz, "r:gz") as t:
            t.extractall(runtime, filter="tar")
        inner = os.listdir(runtime)[0]
        os.replace(os.path.join(runtime, inner), os.path.join(runtime, "node"))
        node_bin = os.path.join(runtime, "node", "bin", "node")
        os.chmod(node_bin, 0o755)
        log_ok("使用载荷内置 Node：%s" % node_bin)

    # 备份用户 agent 配置 → 换新发行包 → 还原配置
    agent_dir = os.path.join(install_dir, "agent")
    backup = agent_dir + ".agentboot-bak"
    had_agent = os.path.isdir(agent_dir)
    if had_agent:
        shutil.move(agent_dir, backup)
    if os.path.exists(install_dir):
        shutil.rmtree(install_dir)
    extract = install_dir + ".extract"
    if os.path.isdir(extract):
        shutil.rmtree(extract)
    os.makedirs(extract, exist_ok=True)
    with tarfile.open(tgz, "r:gz") as t:
        t.extractall(extract, filter="tar")
    os.replace(os.path.join(extract, "package"), install_dir)
    shutil.rmtree(extract, ignore_errors=True)
    if had_agent:
        shutil.move(backup, agent_dir)
    os.makedirs(os.path.join(agent_dir, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(agent_dir, "languages"), exist_ok=True)

    # 写配置：models 骨架 + Agnes 密钥 + 默认设置
    registry_path = os.path.join(install_dir, "resources", "provider-registry.v1.json")
    providers = {}
    if os.path.exists(registry_path):
        reg = json.load(open(registry_path, "r", encoding="utf-8"))
        for pid_, entry in (reg.get("providers") or {}).items():
            providers[pid_] = {k: entry[k] for k in ("api", "authHeader", "baseUrl", "compat") if k in entry}
            providers[pid_]["models"] = []
    def _write_json(path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.chmod(path, 0o600)
    models_path = os.path.join(agent_dir, "models.json")
    if not os.path.exists(models_path):
        _write_json(models_path, {"providers": providers})
    auth_path = os.path.join(agent_dir, "auth.json")
    if not os.path.exists(auth_path):
        agnes_key = open(key_file, "r", encoding="utf-8").read().strip()
        _write_json(auth_path, {"agnes": {"type": "api_key", "key": agnes_key}})
    settings_path = os.path.join(agent_dir, "settings.json")
    if not os.path.exists(settings_path):
        _write_json(settings_path, {"defaultProvider": "agnes", "defaultModel": "agnes-2.5-flash",
                                    "defaultThinkingLevel": "max"})

    # 命令 shim（AgentBoot 管理的 bin 目录，已在 PATH）
    for name, arg in (("coco", ""), ("web", " web"), ("coweb", " web")):
        shim = os.path.join(bin_dir, name)
        with open(shim, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\nexec \"%s\" \"%s\"%s \"$@\"\n" % (node_bin, os.path.join(install_dir, "bin", "coco"), arg))
        os.chmod(shim, 0o755)
    log_ok("%s 离线安装完成，命令：coco / web / coweb（预置 Agnes 免费模型）" % a["name"])
    return True


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
        if aid == "coco":
            if not POSIX:
                log_err("CoCo Agent 官方仅支持 Linux/macOS，Windows 无法离线安装")
                fail_list.append(aid)
                continue
            plat_payload = os.path.join(pdir, "agents", "coco", pid)
            if not os.path.isdir(plat_payload):
                log_err("%s：离线包中没有 %s 平台的载荷" % (a["name"], pid))
                fail_list.append(aid)
                continue
            if coco_offline_install(a, plat_payload):
                ok_list.append(aid)
            else:
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
        if POSIX:
            shutil.copytree(src, dst_nm)
        else:
            # Windows：载荷可能含超长路径，robocopy 原生支持（exit<8 均为成功）
            r = subprocess.run(["robocopy", src, dst_nm, "/E", "/NFL", "/NDL", "/NJH", "/NJS"],
                               capture_output=True)
            if r.returncode >= 8:
                log_err("robocopy 部署失败（code=%d）：%s" % (r.returncode, aid))
                fail_list.append(aid)
                continue
        if aid == "hermes":
            fixup_hermes_venv(os.path.join(pdir, "agents", "hermes", pid), dst_nm)
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
            if a.get("special_install") == "hermes":
                venv_py = os.path.join(AGENTS_DIR, "hermes", "node_modules", "hermes-agent",
                                       "runtime", "hermes-agent", "venv", "bin", "python")
                runpy = os.path.join(AGENTS_DIR, "hermes", "hermes-run.py")
                body = 'exec "%s" "%s" "$@"\n' % (venv_py, runpy)
            else:
                nd = runtime_node_dir()
                body = ""
                if os.path.isdir(nd):
                    body += '[ -x "%s/bin/node" ] && export PATH="%s/bin:$PATH"\n' % (nd, nd)
                body += 'export PATH="$AB_ROOT/agents/%s/node_modules/.bin:$PATH"\nexec "%s" "$@"\n' % (aid, bin_)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("#!/bin/sh\n# AgentBoot shim for %s\nAB_ROOT=\"$HOME/.agentboot\"\n%s" % (aid, body))
            os.chmod(path, 0o755)
        else:
            bin_dir = os.path.join(AB_HOME, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            path = os.path.join(bin_dir, bin_ + ".cmd")
            if a.get("special_install") == "hermes":
                venv_py = os.path.join(AGENTS_DIR, "hermes", "node_modules", "hermes-agent",
                                       "runtime", "hermes-agent", "venv", "Scripts", "python.exe")
                runpy = os.path.join(AGENTS_DIR, "hermes", "hermes-run.py")
                body = '"%s" "%s" %%*\r\n' % (venv_py, runpy)
            else:
                body = ('if exist "%AB_ROOT%\\runtime\\node-win-x64\\node.exe" '
                        'set "PATH=%AB_ROOT%\\runtime\\node-win-x64;%%PATH%%"\r\n'
                        'set "PATH=%AB_ROOT%\\agents\\%s\\node_modules\\.bin;%%PATH%%"\r\n'
                        '%s %%*\r\n' % (aid, bin_))
            with open(path, "w", encoding="ascii", newline="") as f:
                f.write("@echo off\r\nrem AgentBoot shim for %s\r\n"
                        'set "AB_ROOT=%%USERPROFILE%%\\.agentboot"\r\n%s' % (aid, body))
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

def pick_agents(agents, title, allow_custom=False):
    print("\n%s" % title)
    for i, a in enumerate(agents, 1):
        offline_mark = "可离线" if a.get("offline") else "仅在线"
        mark = " ★" if a.get("custom") else ""
        print("  [%2d] %-16s %-24s (%s) %s%s" % (i, a["id"], a["name"], offline_mark, a.get("desc", ""), mark))
    extra = "  [ a] 全选 npm 类 · [ 0] 返回"
    if allow_custom:
        extra += " · [ +] 添加自定义 Agent"
    print(extra)
    raw = input("输入编号（可多选，空格/逗号分隔）: ").strip().lower()
    if not raw or raw == "0":
        return []
    if raw == "+":
        nid = custom_add_wizard()
        return [nid] if nid else []
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


# ---------------------------------------------------------------- 自定义离线包构建

BUILD_PLATFORMS = [
    ("linux-x64", "Linux x64（Intel/AMD 服务器、桌面）"),
    ("linux-arm64", "Linux arm64（ARM 服务器、国产化设备）"),
    ("win-x64", "Windows 10/11 x64"),
    ("darwin-x64", "macOS Intel"),
    ("darwin-arm64", "macOS Apple Silicon (M 系列)"),
]


def pick_platforms():
    """多选目标平台，返回平台 id 列表。空输入 = 常用三平台。"""
    print("\n选择目标平台（可多选，空格/逗号分隔；回车 = 常用三平台）：")
    for i, (pid, desc) in enumerate(BUILD_PLATFORMS, 1):
        print("  [%d] %-14s %s" % (i, pid, desc))
    raw = input("平台编号: ").strip().lower()
    if not raw:
        return ["linux-x64", "win-x64", "darwin-arm64"]
    ids = []
    for tok in re.split(r"[\s,，]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(BUILD_PLATFORMS):
            ids.append(BUILD_PLATFORMS[int(tok) - 1][0])
        elif tok in [p[0] for p in BUILD_PLATFORMS]:
            ids.append(tok)
    if not ids:
        log_err("未识别任何平台，使用默认三平台")
        return ["linux-x64", "win-x64", "darwin-arm64"]
    return sorted(set(ids), key=lambda x: [p[0] for p in BUILD_PLATFORMS].index(x))


def pick_offline_agents():
    """多选要打进离线包的 Agent（默认全选支持离线的）。返回 id 列表。"""
    capable = [a for a in load_registry() if a.get("method") == "npm" or a.get("id") == "coco"]
    print("\n选择要打入离线包的 Agent（可多选；回车 = 全选）：")
    for i, a in enumerate(capable, 1):
        print("  [%2d] %-14s %-22s %s" % (i, a["id"], a["name"], a.get("desc", "")))
    print("  （aider 为 pip 生态暂不支持离线，已自动排除）")
    raw = input("Agent 编号: ").strip().lower()
    if raw == "a" or not raw:
        return [a["id"] for a in capable]
    ids = []
    for tok in re.split(r"[\s,，]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(capable):
            ids.append(capable[int(tok) - 1]["id"])
        elif tok in [a["id"] for a in capable]:
            ids.append(tok)
    return sorted(set(ids), key=lambda x: [a["id"] for a in capable].index(x))


def build_offline_run(platforms, agents_ids):
    """调用 scripts/build-offline.* 构建自定义离线包（跨平台分发到对应脚本）。"""
    if not platforms or not agents_ids:
        log_err("平台与 Agent 列表不能为空")
        return False
    log_info("开始构建：平台=%s · Agent=%s" % (",".join(platforms), ",".join(agents_ids)))
    print("（首次构建会自动下载便携 Node/Python 与各 Agent 依赖，耗时取决于网速，请耐心等待）\n")
    env = child_env()
    if POSIX:
        script = os.path.join(APP_DIR, "scripts", "build-offline.sh")
        env.update({"PLATFORMS": ",".join(platforms), "AGENTS": ",".join(agents_ids), "TAG": "v1.0.0"})
        cmd = ["sh", script]
    else:
        script = os.path.join(APP_DIR, "scripts", "build-offline.ps1")
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
               "-Tag", "v1.0.0", "-Platforms", ",".join(platforms), "-Agents", ",".join(agents_ids)]
    r = subprocess.run(cmd, env=env)
    ok = r.returncode == 0
    if ok:
        dist = os.path.join(APP_DIR, "dist")
        print("")
        log_ok("构建完成，产物在 %s：" % dist)
        try:
            for fn in sorted(os.listdir(dist)):
                if fn.startswith("AgentBoot-offline-v1.0.0-"):
                    p = os.path.join(dist, fn)
                    if os.path.isfile(p):
                        print("  %-52s %8.1f MB" % (fn, os.path.getsize(p) / 1048576.0))
        except OSError:
            pass
    else:
        log_err("构建脚本退出码 %s" % r.returncode)
    return ok


def build_offline_wizard():
    platforms = pick_platforms()
    agents_ids = pick_offline_agents()
    if not agents_ids:
        log_err("未选择任何 Agent")
        return
    print("\n即将构建：平台 %s · Agent %s" % (", ".join(platforms), ", ".join(agents_ids)))
    if input("确认开始? [Y/n] ").strip().lower() in ("n", "no"):
        return
    build_offline_run(platforms, agents_ids)


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
        print("  [7] 构建自定义离线安装包（选平台/选 Agent，瘦身）")
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
        elif c == "7":
            build_offline_wizard()
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
    elif cmd == "add-agent":
        # 用法：
        #   add-agent --list
        #   add-agent --del <id>
        #   add-agent <id> npm <包名> [bin]
        #   add-agent <id> pip <包名> [bin]
        #   add-agent <id> script <URL> <bin>
        arg = argv[1] if len(argv) > 1 else ""
        if arg in ("--list", "list"):
            items = load_custom_agents()
            print("自定义 Agent（%d 个）：%s" % (len(items), os.path.join(AB_HOME, "custom-agents.json")))
            for a in items:
                print("  %-16s %-10s %-32s bin=%s" % (a.get("id"), a.get("method"), a.get("npm") or a.get("pip") or a.get("script"), a.get("bin")))
        elif arg in ("--del", "del", "remove"):
            custom_remove_entry(argv[2])
            log_ok("已删除自定义 Agent：%s" % argv[2])
        elif len(argv) >= 4 and argv[2] in ("npm", "pip", "script"):
            aid, m, pkg = argv[1], argv[2], argv[3]
            entry = {"id": aid, "name": aid, "desc": "自定义 Agent", "bin": argv[4] if len(argv) > 4 else aid,
                     "method": m, "requires": [], "notes": ["用户自定义条目"]}
            if m == "npm":
                entry["npm"] = pkg
            elif m == "pip":
                entry["pip"] = pkg
            else:
                entry["script"] = pkg
            custom_add_entry(entry)
            log_ok("已添加自定义 Agent：%s（%s）" % (aid, pkg))
        else:
            print(__doc__)
    elif cmd == "build-offline":
        # 用法：build-offline <平台列表> <Agent列表>（逗号分隔），无参数进入向导
        if len(argv) >= 3:
            plats = [t for t in re.split(r"[,\s]+", argv[1]) if t]
            ids = [t for t in re.split(r"[,\s]+", argv[2]) if t]
            build_offline_run(plats, ids)
        else:
            build_offline_wizard()
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
