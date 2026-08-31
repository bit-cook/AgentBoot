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
  python menu.py uninstall claude-code,qwen-code [--purge]
  python menu.py offline claude-code --payload /path/payloads
  python menu.py mirror auto|off|cn|proxy http://127.0.0.1:7890
"""
import json
from contextlib import contextmanager
import os
import re
import shutil
import socket
import subprocess
import sys
import platform
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent  # noqa: E402  复用配置与模型能力
import i18n  # noqa: E402  双语支持

t = i18n.t

APP_DIR = agent.APP_DIR
VERSION = agent.VERSION
AB_HOME = agent.AB_HOME
RUNTIME_DIR = os.path.join(AB_HOME, "runtime")
AGENTS_DIR = os.path.join(AB_HOME, "agents")
NPM_PREFIX = os.path.join(AB_HOME, "npm-prefix")
ENV_JSON = os.path.join(AB_HOME, "env.json")

NODE_VERSION = "v22.23.2"
NPM_MIRROR = "https://registry.npmmirror.com"
NPM_OFFICIAL = "https://registry.npmjs.org"
NODE_MIRROR_CN = "https://registry.npmmirror.com/-/binary/node"
NODE_MIRROR_GLOBAL = "https://nodejs.org/dist"
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

CUSTOM_AGENTS = os.path.join(AB_HOME, "custom-agents.json")
INSTALL_STATE = os.path.join(AB_HOME, "installed-agents.json")

POSIX = os.name != "nt"


# ---------------------------------------------------------------- 基础工具

def log_ok(msg):  print("✓ %s" % msg)
def log_err(msg): print("✗ %s" % msg)
def log_info(msg): print("· %s" % msg)


def plat_id():
    s = platform.system().lower()
    if s == "windows":
        s = "win"
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        arch = "x64"
    elif m in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise RuntimeError("不支持的 CPU 架构：%s" % m)
    if s not in ("linux", "darwin", "win"):
        raise RuntimeError("不支持的操作系统：%s" % s)
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
            data = json.load(f)
        proxy = data.get("proxy") if isinstance(data, dict) else None
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_env_json(data):
    agent._atomic_private_json(ENV_JSON, data)


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
    agent._atomic_private_json(CUSTOM_AGENTS, items)


def load_install_state():
    """读取 AgentBoot 安装归属清单；损坏文件按空清单处理。"""
    try:
        with open(INSTALL_STATE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("agents"), dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "agents": {}}


def save_install_state(data):
    """同目录临时文件 + os.replace，避免中断时写坏安装清单。"""
    os.makedirs(AB_HOME, exist_ok=True)
    tmp = INSTALL_STATE + ".%s.tmp" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, INSTALL_STATE)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@contextmanager
def _install_state_lock():
    os.makedirs(AB_HOME, mode=0o700, exist_ok=True)
    lock_path = INSTALL_STATE + ".lock"
    with open(lock_path, "a+b") as lock:
        if os.path.getsize(lock_path) == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def record_install(a, source, executable=None, install_prefix=None):
    """记录由 AgentBoot 完成的安装，作为安全卸载的归属依据。"""
    with _install_state_lock():
        state = load_install_state()
        state["version"] = 1
        state["agents"][a["id"]] = {
            "name": a.get("name") or a["id"], "bin": a.get("bin"), "source": source,
            "method": a.get("method", "npm"),
            "package": a.get("npm") or a.get("pip") or a.get("script"),
            "executable": executable, "prefix": install_prefix,
            "custom": bool(a.get("custom")), "installed_at": int(time.time()),
        }
        save_install_state(state)


def forget_install(aid):
    with _install_state_lock():
        state = load_install_state()
        if state["agents"].pop(aid, None) is not None:
            save_install_state(state)


def custom_add_entry(entry):
    """添加一条自定义 Agent（id 重复时拒绝）。返回是否成功。"""
    if not _valid_agent_id(entry.get("id")) or not _valid_bin_name(entry.get("bin")):
        raise ValueError("Agent id/命令名只能包含字母、数字、点、下划线与连字符")
    items = load_custom_agents()
    registry_path = os.path.join(APP_DIR, "agents", "registry.json")
    try:
        with open(registry_path, "r", encoding="utf-8") as source:
            builtins = {item.get("id") for item in json.load(source).get("agents", [])}
    except Exception:
        builtins = set()
    if entry["id"] in builtins or any(item.get("id") == entry["id"] for item in items):
        raise ValueError("Agent id 已存在：%s" % entry["id"])
    entry["offline"] = False
    entry.setdefault("vendor", "自定义")
    items.append(entry)
    save_custom_agents(items)


def custom_remove_entry(aid):
    items = [a for a in load_custom_agents() if a.get("id") != aid]
    save_custom_agents(items)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "custom"


def _valid_agent_id(value):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(value or "")))


def _valid_bin_name(value):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(value or "")))


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
    if not _valid_agent_id(aid) or not _valid_bin_name(bin_):
        log_err("id 与命令名只能包含字母、数字、点、下划线与连字符")
        return None
    entry = {"id": aid, "name": name, "desc": "自定义 Agent", "bin": bin_, "method": m,
             "requires": [], "notes": ["用户自定义条目"]}
    if m == "npm":
        entry["npm"] = pkg
    elif m == "pip":
        entry["pip"] = pkg
    else:
        entry["script"] = pkg
    try:
        custom_add_entry(entry)
    except ValueError as error:
        log_err(str(error))
        return None
    log_ok("已保存到 %s" % CUSTOM_AGENTS)
    return aid


def runtime_node_dir():
    return os.path.join(RUNTIME_DIR, "node-%s" % plat_id())


def node_exe():
    d = runtime_node_dir()
    return os.path.join(d, "node.exe") if not POSIX else os.path.join(d, "bin", "node")


def npm_cmd(minimum=None, version_cache=None):
    """优先系统 npm，其次运行时自带 npm。"""
    n = shutil.which("npm")
    system_node = shutil.which("node")
    if n and node_ok(system_node, minimum, version_cache):
        return n
    d = runtime_node_dir()
    cand = os.path.join(d, "npm.cmd") if not POSIX else os.path.join(d, "bin", "npm")
    return cand if os.path.exists(cand) and node_ok(node_exe(), minimum, version_cache) else None


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

def _version_tuple(value):
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(value or ""))
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _version_satisfies(current, requirement):
    """Evaluate the simple npm engine ranges used by AgentBoot's registry."""
    for clause in str(requirement or ">=18").split("||"):
        matched = True
        comparisons = re.findall(r"(>=|<=|>|<|=)?\s*(\d+(?:\.\d+){0,2})", clause)
        if not comparisons:
            continue
        for operator, raw in comparisons:
            target = _version_tuple(raw)
            if operator == ">=" and not current >= target: matched = False
            elif operator == ">" and not current > target: matched = False
            elif operator == "<=" and not current <= target: matched = False
            elif operator == "<" and not current < target: matched = False
            elif operator in ("", "=") and not current == target: matched = False
        if matched:
            return True
    return False


def node_ok(path=None, minimum=None, version_cache=None):
    try:
        executable = path or shutil.which("node") or node_exe()
        current = version_cache.get(executable) if version_cache is not None else None
        if current is None:
            out = subprocess.run([executable, "--version"],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode != 0:
                return False
            current = _version_tuple(out.stdout.strip())
            if current and version_cache is not None:
                version_cache[executable] = current
        return bool(current and _version_satisfies(current, minimum or ">=18"))
    except Exception:
        pass
    return False


def ensure_node(minimum=None):
    """确保 Node 满足 Agent 最低版本；不足时部署便携运行时。"""
    import hashlib
    from urllib import request as urllib_request
    sysnode = shutil.which("node")
    if sysnode and node_ok(sysnode, minimum):
        return sysnode
    if os.path.exists(node_exe()) and node_ok(node_exe(), minimum):
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
    sums_path = os.path.join(dest_parent, "SHASUMS256-%s.txt" % NODE_VERSION)
    ok = False
    for u in urls:
        try:
            log_info("下载 Node 运行时：%s" % u)
            req = urllib_request.Request(u, headers={"User-Agent": "AgentBoot/1.0"})
            with urllib_request.urlopen(req, timeout=60) as r, open(archive, "wb") as f:
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
    try:
        if not os.path.exists(sums_path):
            sums_url = "%s/%s/SHASUMS256.txt" % (NODE_MIRROR_GLOBAL, NODE_VERSION)
            req = urllib_request.Request(sums_url, headers={"User-Agent": "AgentBoot/1.0"})
            with urllib_request.urlopen(req, timeout=60) as response, open(sums_path, "wb") as output:
                shutil.copyfileobj(response, output)
        expected = None
        with open(sums_path, "r", encoding="ascii") as sums:
            for line in sums:
                parts = line.split()
                if len(parts) >= 2 and parts[1].lstrip("*") == fname:
                    expected = parts[0].lower()
                    break
        actual = hashlib.sha256(open(archive, "rb").read()).hexdigest()
        if not expected or actual != expected:
            raise ValueError("checksum mismatch")
        log_ok("Node 运行时 SHA-256 校验通过")
    except Exception as e:
        log_err("Node 运行时 SHA-256 校验失败：%s" % e)
        try:
            os.remove(archive)
        except OSError:
            pass
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
    if node_ok(node_exe(), minimum):
        return node_exe()
    return None


def ensure_npm_prefix():
    """所有 npm Agent 固定安装到 AgentBoot 自有目录。"""
    os.makedirs(NPM_PREFIX, exist_ok=True)
    return NPM_PREFIX


def prefix_bin_dirs():
    dirs = []
    if POSIX:
        dirs.append(os.path.join(NPM_PREFIX, "bin"))
    else:
        dirs.append(NPM_PREFIX)
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


def _inside(path, parent):
    if not path:
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
    except (OSError, ValueError):
        return False


def _npm_package_name(spec):
    """去掉 npm 版本限定；保留 @scope/name。"""
    if not spec:
        return ""
    if spec.startswith("@"):
        slash = spec.find("/")
        version = spec.find("@", slash + 1)
        return spec[:version] if version >= 0 else spec
    return spec.split("@", 1)[0]


def detect_install(a):
    """返回安装归属；绝不把 PATH 上的同名外部命令冒充为 AgentBoot 安装。"""
    if not _valid_agent_id(a.get("id")) or not _valid_bin_name(a.get("bin")):
        return {"status": "invalid", "managed": False, "source": None, "entry": {}}
    entry = load_install_state()["agents"].get(a["id"])
    if entry:
        return {"status": "managed", "managed": True,
                "source": entry.get("source"), "entry": entry}
    offline_dir = os.path.join(AGENTS_DIR, a["id"])
    if os.path.isdir(offline_dir):
        return {"status": "legacy", "managed": True, "source": "offline", "entry": {}}
    found = find_bin(a.get("bin") or "")
    if found and (_inside(found, NPM_PREFIX) or _inside(found, os.path.join(AB_HOME, "bin"))):
        entry = {"executable": found}
        if _inside(found, NPM_PREFIX):
            entry["prefix"] = NPM_PREFIX
        return {"status": "legacy", "managed": True, "source": "online", "entry": entry}
    if a["id"] == "coco" and os.path.isdir(os.path.expanduser("~/.coco")):
        coco_shim = os.path.join(AB_HOME, "bin", "coco" + ("" if POSIX else ".cmd"))
        if os.path.exists(coco_shim):
            return {"status": "legacy", "managed": True, "source": "online",
                    "entry": {"executable": coco_shim}}
    if found:
        return {"status": "external", "managed": False, "source": None,
                "entry": {}, "executable": found}
    return {"status": "absent", "managed": False, "source": None, "entry": {}}


def _remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def _safe_extract_tar(archive, destination):
    """Extract after rejecting traversal, device nodes, and escaping links."""
    import tarfile
    root = os.path.realpath(destination)
    os.makedirs(root, exist_ok=True)
    for member in archive.getmembers():
        target = os.path.realpath(os.path.join(root, member.name))
        if not _inside(target, root):
            raise ValueError("tar 成员越界：%s" % member.name)
        if member.isdev() or member.isfifo():
            raise ValueError("tar 包含设备或管道：%s" % member.name)
        if member.issym():
            link_target = os.path.realpath(os.path.join(os.path.dirname(target), member.linkname))
            if not _inside(link_target, root):
                raise ValueError("tar 符号链接越界：%s" % member.name)
        elif member.islnk():
            link_target = os.path.realpath(os.path.join(root, member.linkname))
            if not _inside(link_target, root):
                raise ValueError("tar 硬链接越界：%s" % member.name)
    if hasattr(tarfile, "data_filter"):
        archive.extractall(root, filter="data")
    else:
        archive.extractall(root)


def _remove_owned_shims(a, entry):
    candidates = [entry.get("executable")]
    suffix = "" if POSIX else ".cmd"
    candidates.append(os.path.join(AB_HOME, "bin", (a.get("bin") or "") + suffix))
    if a["id"] == "coco":
        candidates += [os.path.join(AB_HOME, "bin", x + suffix) for x in ("web", "coweb")]
    seen = set()
    for path in candidates:
        if not path or path in seen or not _inside(path, os.path.join(AB_HOME, "bin")):
            continue
        seen.add(path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                marker = f.read(512)
            if "AgentBoot" not in marker:
                log_info(t("menu.uninstall_shim_changed") % path)
                continue
            _remove_path(path)
        except (FileNotFoundError, IsADirectoryError):
            pass


def _remove_coco(purge=False):
    root = os.path.expanduser("~/.coco")
    if not os.path.exists(root):
        return
    if os.path.islink(root) or not _inside(os.path.realpath(root), os.path.realpath(os.path.expanduser("~"))):
        raise OSError("拒绝删除符号链接或用户目录之外的 CoCo 路径：%s" % root)
    if purge:
        shutil.rmtree(root)
        return
    if not any(os.path.exists(os.path.join(root, name)) for name in ("bin", "runtime", "resources")):
        raise OSError("CoCo 程序目录缺少预期结构，拒绝自动删除：%s" % root)
    # CoCo 的 agent/ 内含会话、认证与用户设置；默认只移除程序文件。
    for name in os.listdir(root):
        if name == "agent":
            continue
        _remove_path(os.path.join(root, name))


def _remove_coco_external_launchers(entry):
    executable = entry.get("executable")
    if not executable:
        return
    directory = os.path.dirname(os.path.abspath(executable))
    allowed_dirs = {os.path.realpath(os.path.expanduser("~/.local/bin")), "/usr/local/bin"}
    if os.path.realpath(directory) not in allowed_dirs:
        return
    coco_root = os.path.realpath(os.path.expanduser("~/.coco"))
    suffix = ".cmd" if not POSIX else ""
    for name in ("coco", "web", "coweb"):
        path = os.path.join(directory, name + suffix)
        if not os.path.lexists(path):
            continue
        owned = False
        if os.path.islink(path):
            owned = _inside(os.path.realpath(path), coco_root)
        elif os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as source:
                    owned = ".coco" in source.read(1024)
            except OSError:
                pass
        if owned:
            os.remove(path)


def uninstall_one(a, purge=False):
    """安全卸载一个 Agent；返回 (成功, 面向用户的说明)。"""
    if not _valid_agent_id(a.get("id")) or not _valid_bin_name(a.get("bin")):
        return False, t("menu.uninstall_invalid_id")
    detected = detect_install(a)
    if not detected["managed"]:
        if detected["status"] == "external":
            return False, t("menu.uninstall_external")
        return False, t("menu.uninstall_nothing") % a["name"]

    entry = detected.get("entry") or {}
    source = detected.get("source")
    method = entry.get("method") or a.get("method", "npm")
    if a["id"] == "coco":
        try:
            _remove_coco(purge)
            _remove_coco_external_launchers(entry)
        except OSError as e:
            return False, str(e)
    elif source == "offline":
        try:
            shutil.rmtree(os.path.join(AGENTS_DIR, a["id"]), ignore_errors=False)
        except FileNotFoundError:
            pass
        except OSError as e:
            return False, str(e)
    elif method == "npm":
        npm = npm_cmd()
        package = _npm_package_name(entry.get("package") or a.get("npm"))
        if not npm or not package:
            return False, t("menu.uninstall_no_tool") % "npm"
        cmd = [npm, "uninstall", "-g", package]
        prefix = entry.get("prefix")
        if prefix and (_inside(prefix, AB_HOME) or prefix == NPM_PREFIX):
            cmd += ["--prefix", prefix]
        log_info("$ %s" % " ".join(cmd))
        if subprocess.run(cmd, env=child_env()).returncode != 0:
            return False, t("menu.uninstall_command_failed") % package
    elif method == "pip":
        py = find_python()
        package = entry.get("package") or a.get("pip")
        if not py or not package:
            return False, t("menu.uninstall_no_tool") % "Python/pip"
        cmd = [py, "-m", "pip", "uninstall", "-y", package]
        log_info("$ %s" % " ".join(cmd))
        if subprocess.run(cmd, env=child_env()).returncode != 0:
            return False, t("menu.uninstall_command_failed") % package
    elif method == "venv":
        pass
    else:
        return False, t("menu.uninstall_manual_script")

    try:
        offline_dir = os.path.join(AGENTS_DIR, a["id"])
        if os.path.lexists(offline_dir):
            _remove_path(offline_dir)
        _remove_owned_shims(a, entry)
        forget_install(a["id"])
    except OSError as e:
        return False, str(e)
    return True, t("menu.uninstall_ok") % a["name"]


def uninstall_agents(ids, purge=False):
    """批量卸载，去重且继续处理后续项；返回失败 id。"""
    by_id = {a["id"]: a for a in load_registry()}
    # 即使自定义注册条目已删除，安装快照仍可支持安全的 npm/pip 卸载。
    for aid, entry in load_install_state()["agents"].items():
        if aid in by_id:
            continue
        a = {"id": aid, "name": entry.get("name") or aid,
             "bin": entry.get("bin"), "method": entry.get("method"), "custom": True}
        package = entry.get("package")
        if entry.get("method") == "npm":
            a["npm"] = package
        elif entry.get("method") == "pip":
            a["pip"] = package
        elif entry.get("method") == "script":
            a["script"] = package
        by_id[aid] = a
    ok_list, fail_list, seen = [], [], set()
    for aid in ids:
        if aid in seen:
            continue
        seen.add(aid)
        a = by_id.get(aid)
        if not a:
            log_err(t("menu.unknown_agent") % aid)
            fail_list.append(aid)
            continue
        ok, message = uninstall_one(a, purge=purge)
        (log_ok if ok else log_err)(message)
        (ok_list if ok else fail_list).append(aid)
    print("\n" + t("menu.uninstall_summary") %
          (", ".join(ok_list) or "-", ", ".join(fail_list) or "-"))
    if ok_list and not purge:
        print(t("menu.uninstall_preserved"))
    return fail_list


# ---------------------------------------------------------------- 在线安装

def npm_install(pkg, minimum=None, context=None):
    packages = [pkg] if isinstance(pkg, str) else list(pkg)
    if not packages:
        return True
    context = context if context is not None else {}
    versions = context.setdefault("node_versions", {})
    npm = npm_cmd(minimum, versions)
    if not npm:
        got = ensure_node(minimum)
        if not got:
            log_err("需要 Node.js %s（无法自动部署，请检查网络）" % (minimum or ">=18"))
            return False
        versions.clear()
        npm = npm_cmd(minimum, versions)
    if not npm:
        log_err("Node 已就绪但未找到匹配的 npm")
        return False
    ensure_npm_prefix()
    cmd = [npm, "install", "-g"] + packages + ["--prefix", NPM_PREFIX,
           "--no-audit", "--no-fund", "--prefer-offline",
           "--progress=false", "--loglevel=error"]
    if "cn" not in context:
        context["cn"] = cn_mode()
    if context["cn"]:
        cmd += ["--registry", NPM_MIRROR]
    log_info("$ %s" % " ".join(cmd))
    if "env" not in context:
        context["env"] = child_env()
    r = subprocess.run(cmd, env=context["env"])
    return r.returncode == 0


def install_online(ids):
    agents = load_registry()
    by_id = {a["id"]: a for a in agents}
    ok_list, fail_list = [], []
    npm_context, ready = {}, []
    for aid in ids:
        a = by_id.get(aid)
        if not a:
            log_err("未知 Agent：%s（用 2 号菜单查看可用列表）" % aid)
            fail_list.append(aid)
            continue
        print("\n" + t("menu.install_header") % (a["name"], a.get("vendor", "")))
        print("  %s" % a.get("desc", ""))
        missing = [x for x in (a.get("requires") or []) if not shutil.which(x)]
        if missing:
            log_err(t("menu.install_missing_dep") % (a["name"], " + ".join(missing)))
            fail_list.append(aid)
            continue
        os_limits = a.get("os") or []
        if os_limits and plat_id().split("-")[0] not in os_limits:
            log_err(t("menu.install_os_limit") % (a["name"], "/".join(os_limits), plat_id()))
            fail_list.append(aid)
            continue
        ready.append(a)

    npm_groups = {}
    for a in ready:
        if a.get("method", "npm") == "npm" and not a.get("special_install"):
            npm_groups.setdefault(a.get("node") or ">=18", []).append(a)
    batched = set()
    for minimum, group in npm_groups.items():
        if len(group) < 2:
            continue
        packages = [a["npm"] for a in group]
        log_info("批量安装 %d 个 npm Agent（共用依赖解析与连接）" % len(group))
        if npm_install(packages, minimum, npm_context):
            batched.update(a["id"] for a in group)
        else:
            log_info("批量安装失败，回退逐个安装以定位问题")

    for a in ready:
        aid = a["id"]
        method = a.get("method", "npm")
        ok = False
        if a.get("special_install") == "hermes":
            log_info("使用 hermes 专用安装流程（自动适配网络）")
            ok = install_hermes_special(a)
            if not ok:
                log_err("专用流程失败：可检查 Git 是否安装、或配置代理后重试")
        elif method == "npm":
            ok = aid in batched or npm_install(a["npm"], a.get("node"), npm_context)
        elif method == "script":
            ok = install_via_script(a)
        elif method == "pip":
            ok = install_via_pip(a)
        elif method == "venv":
            ok = install_aider_venv(a)
        if ok and a.get("bin"):
            found = aider_venv_executable() if method == "venv" else find_bin(a["bin"])
            if found:
                env_extra, args_prefix = wire_agnes(a)
                executable = found
                if env_extra or args_prefix:
                    if not write_online_shim(a, found, env_extra, args_prefix):
                        log_err(t("menu.install_fail") % a["name"])
                        fail_list.append(aid)
                        continue
                    executable = os.path.join(AB_HOME, "bin", a["bin"] + ("" if POSIX else ".cmd"))
                record_install(a, "online", executable, NPM_PREFIX if method == "npm" else None)
                log_ok(t("menu.install_ok") % (a["name"], a["bin"]))
                ok_list.append(aid)
            else:
                log_err(t("menu.install_ok_nobin") % (a["name"], a["bin"]))
                fail_list.append(aid)
        elif ok:
            log_ok(t("menu.install_done") % a["name"])
            ok_list.append(aid)
        else:
            log_err(t("menu.install_fail") % a["name"])
            fail_list.append(aid)
        for note in a.get("notes", []) or []:
            print("  ℹ %s" % note)
    print("\n" + t("menu.install_summary") %
          (", ".join(ok_list) or "-", ", ".join(fail_list) or "-"))
    if not POSIX:
        print(t("menu.install_hint_win"))
    ensure_path_registered()
    return fail_list


def install_via_script(a):
    url = a.get("script")
    parsed = urllib.parse.urlsplit(url or "")
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        log_err("安装脚本必须使用有效的 HTTPS URL")
        return False
    urls = [url]
    if cn_mode() and parsed.hostname in ("github.com", "raw.githubusercontent.com"):
        for p in ("https://gh-proxy.com/", "https://ghfast.top/"):
            urls.append(p + url)
    for u in urls:
        path = None
        try:
            path = _download_script(u, ".sh" if POSIX else ".ps1")
            cmd = (["sh", path] if POSIX else
                   ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path])
            log_info("执行已下载脚本：%s" % u)
            if subprocess.run(cmd, env=child_env()).returncode == 0:
                return True
            log_err("安装脚本执行失败，尝试下一个源 …")
        except Exception as e:
            log_err("脚本下载失败(%s)：%s" % (u, e))
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
    return False


def _download_script(url, suffix):
    import tempfile
    from urllib import request as urllib_request
    request = urllib_request.Request(url, headers={"User-Agent": "AgentBoot/1.0"})
    fd, path = tempfile.mkstemp(prefix="agentboot-script-", suffix=suffix)
    try:
        total = 0
        with os.fdopen(fd, "wb") as output, urllib_request.urlopen(request, timeout=60) as response:
            final_url = urllib.parse.urlsplit(response.geturl())
            if final_url.scheme.lower() != "https":
                raise ValueError("安装脚本重定向到了非 HTTPS 地址")
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > 4 * 1024 * 1024:
                    raise ValueError("安装脚本超过 4 MiB 限制")
                output.write(chunk)
        if total == 0:
            raise ValueError("安装脚本为空")
        return path
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(path)
        except OSError:
            pass
        raise


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


def aider_venv_executable():
    relative = os.path.join("Scripts", "aider.exe") if not POSIX else os.path.join("bin", "aider")
    return os.path.join(AGENTS_DIR, "aider", "venv", relative)


def install_aider_venv(a):
    py = find_python()
    if not py:
        log_err("Aider 需要 Python 3.10+")
        return False
    check = subprocess.run([py, "-c", "import sys; print('%d.%d'%sys.version_info[:2])"],
                           capture_output=True, text=True, timeout=20)
    try:
        version = tuple(int(x) for x in check.stdout.strip().split(".")[:2])
    except ValueError:
        return False
    if check.returncode or version < (3, 10):
        log_err("Aider 需要 Python 3.10+，当前 %s" % check.stdout.strip())
        return False
    root = os.path.join(AGENTS_DIR, "aider")
    candidate, backup = root + ".new.%s" % os.getpid(), root + ".old.%s" % os.getpid()
    shutil.rmtree(candidate, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    if subprocess.run([py, "-m", "venv", os.path.join(candidate, "venv")]).returncode:
        return False
    pip = os.path.join(candidate, "venv", "Scripts", "pip.exe") if not POSIX else os.path.join(candidate, "venv", "bin", "pip")
    cmd = [pip, "install", "--disable-pip-version-check", a["pip"]]
    if cn_mode(): cmd += ["-i", PIP_MIRROR]
    if subprocess.run(cmd, env=child_env()).returncode:
        shutil.rmtree(candidate, ignore_errors=True)
        return False
    if os.path.isdir(root): os.replace(root, backup)
    try:
        os.replace(candidate, root)
        shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if os.path.isdir(backup) and not os.path.exists(root): os.replace(backup, root)
        raise
    return os.path.isfile(aider_venv_executable())


# ---------------------------------------------------------------- hermes-agent 国内专用安装

def _npm_global_root(env, npm=None):
    try:
        r = subprocess.run([npm or npm_cmd() or "npm", "root", "-g", "--prefix", NPM_PREFIX], capture_output=True,
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
    import hashlib
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
    actual_sha = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    if actual_sha != sha.lower():
        log_err("uv SHA-256 校验失败")
        try:
            os.remove(archive)
        except OSError:
            pass
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
    npm = npm_cmd(a.get("node"))
    if not npm:
        if not ensure_node(a.get("node")):
            log_err("Hermes 需要 Node.js %s" % (a.get("node") or ">=20"))
            return False
        npm = npm_cmd(a.get("node"))
    if not npm:
        return False
    ensure_npm_prefix()
    cmd = [npm, "install", "--ignore-scripts", "-g", a["npm"],
           "--prefix", NPM_PREFIX, "--no-audit", "--no-fund", "--prefer-offline",
           "--progress=false", "--loglevel=error"]
    if cn_mode():
        cmd += ["--registry", NPM_MIRROR]
    log_info("$ %s" % " ".join(cmd))
    env = child_env()
    if subprocess.run(cmd, env=env).returncode != 0:
        return False
    root = _npm_global_root(env, npm)
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
    node = node_exe() if _inside(npm, runtime_node_dir()) else shutil.which("node")
    if not node or not node_ok(node, a.get("node")):
        log_err("Hermes postinstall 未找到满足版本的 Node")
        return False
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
    with open(side, "r", encoding="utf-8") as source:
        expected = source.read().split()[0].lower()
    hasher = hashlib.sha256()
    with open(tgz, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            hasher.update(chunk)
    h = hasher.hexdigest()
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
    node_archive = None
    if node_bin and _node_ok(node_bin):
        log_ok("使用系统 Node")
    else:
        ntgz = next((os.path.join(payload, f) for f in os.listdir(payload)
                     if f.startswith("node-v") and f.endswith(".tar.gz")), None)
        if not ntgz:
            log_err("系统 Node 过旧且载荷无内置 Node 运行时")
            return False
        node_archive = ntgz

    # 备份用户 agent 配置 → 换新发行包 → 还原配置
    agent_dir = os.path.join(install_dir, "agent")
    # 备份必须放在 install_dir 外；否则随后删除 ~/.coco 会一并删掉备份。
    backup = install_dir + ".agent.agentboot-bak"
    had_agent = os.path.isdir(agent_dir)
    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)
    if had_agent:
        shutil.move(agent_dir, backup)
    if os.path.exists(install_dir):
        shutil.rmtree(install_dir)
    extract = install_dir + ".extract"
    if os.path.isdir(extract):
        shutil.rmtree(extract)
    os.makedirs(extract, exist_ok=True)
    with tarfile.open(tgz, "r:gz") as t:
        _safe_extract_tar(t, extract)
    try:
        os.replace(os.path.join(extract, "package"), install_dir)
        shutil.rmtree(extract, ignore_errors=True)
        if had_agent:
            shutil.move(backup, agent_dir)
    except Exception:
        if had_agent and os.path.isdir(backup) and not os.path.exists(agent_dir):
            os.makedirs(install_dir, exist_ok=True)
            shutil.move(backup, agent_dir)
        raise
    os.makedirs(os.path.join(agent_dir, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(agent_dir, "languages"), exist_ok=True)

    if node_archive:
        runtime = os.path.join(install_dir, "runtime")
        shutil.rmtree(runtime, ignore_errors=True)
        os.makedirs(runtime, exist_ok=True)
        with tarfile.open(node_archive, "r:gz") as archive:
            _safe_extract_tar(archive, runtime)
        children = [name for name in os.listdir(runtime) if name != "node"]
        if len(children) != 1 or not os.path.isdir(os.path.join(runtime, children[0])):
            raise ValueError("CoCo Node 载荷结构无效")
        os.replace(os.path.join(runtime, children[0]), os.path.join(runtime, "node"))
        node_bin = os.path.join(runtime, "node", "bin", "node")
        if not os.path.isfile(node_bin):
            raise ValueError("CoCo Node 入口缺失")
        os.chmod(node_bin, 0o755)
        log_ok("使用载荷内置 Node：%s" % node_bin)

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
        with open(key_file, "r", encoding="utf-8") as source:
            agnes_key = source.read().strip()
        _write_json(auth_path, {"agnes": {"type": "api_key", "key": agnes_key}})
    settings_path = os.path.join(agent_dir, "settings.json")
    if not os.path.exists(settings_path):
        _write_json(settings_path, {"defaultProvider": "agnes", "defaultModel": "agnes-2.5-flash",
                                    "defaultThinkingLevel": "max"})

    # 命令 shim（AgentBoot 管理的 bin 目录，已在 PATH）
    for name, arg in (("coco", ""), ("web", " web"), ("coweb", " web")):
        shim = os.path.join(bin_dir, name)
        with open(shim, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n# AgentBoot shim for coco\nexec \"%s\" \"%s\"%s \"$@\"\n" %
                    (node_bin, os.path.join(install_dir, "bin", "coco"), arg))
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
    print(t("menu.offline_header") % (pid, pdir))

    agents = {a["id"]: a for a in load_registry()}
    selected_npm = [agents[aid] for aid in ids
                    if aid in agents and agents[aid].get("method") == "npm"]
    # Bundled Node is the reproducible default and every selected Agent is checked individually below.
    strictest_node = ">=18"

    # 1) 离线包优先使用自带 Node，确保路径与版本可复现；无载荷时才回退系统 Node。
    offline_node = None
    if selected_npm:
        src_node = os.path.join(pdir, "node", pid)
        if os.path.isdir(src_node):
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            dst_node = runtime_node_dir()
            if os.path.exists(dst_node):
                shutil.rmtree(dst_node, ignore_errors=True)
            log_info("部署内置 Node 运行时 …")
            shutil.copytree(src_node, dst_node)
            if node_ok(node_exe(), strictest_node):
                offline_node = node_exe()
                log_ok("内置 Node 就绪：%s" % node_exe())
            else:
                log_err("内置 Node 不满足所选 Agent 最低版本 %s" % strictest_node)
        else:
            system_node = shutil.which("node")
            if system_node and node_ok(system_node, strictest_node):
                offline_node = system_node
                log_ok("离线包无 Node 载荷，使用系统 Node：%s" % system_node)
            else:
                log_err("离线包未包含 %s Node，系统 Node 也不满足 %s" % (pid, strictest_node))

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
                record_install(a, "offline", os.path.join(AB_HOME, "bin", "coco"))
                ok_list.append(aid)
            else:
                fail_list.append(aid)
            continue
        src = os.path.join(pdir, "agents", aid, pid, "node_modules")
        if not (a.get("method") == "npm" and os.path.isdir(src)):
            log_err(t("menu.offline_no_payload") % (a["name"], pid))
            fail_list.append(aid)
            continue
        if not offline_node or not node_ok(offline_node, a.get("node")):
            log_err(t("menu.offline_no_node") % a["name"])
            fail_list.append(aid)
            continue
        dst = os.path.join(AGENTS_DIR, aid)
        candidate = dst + ".new.%s" % os.getpid()
        backup = dst + ".old.%s" % os.getpid()
        shutil.rmtree(candidate, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        os.makedirs(candidate, exist_ok=True)
        candidate_nm = os.path.join(candidate, "node_modules")
        log_info(t("menu.offline_deploying") % (a["name"], dir_size_mb(src)))
        if POSIX:
            shutil.copytree(src, candidate_nm)
        else:
            # Windows：载荷可能含超长路径，robocopy 原生支持（exit<8 均为成功）
            r = subprocess.run(["robocopy", src, candidate_nm, "/E", "/NFL", "/NDL", "/NJH", "/NJS"],
                               capture_output=True)
            if r.returncode >= 8:
                log_err("robocopy 部署失败（code=%d）：%s" % (r.returncode, aid))
                shutil.rmtree(candidate, ignore_errors=True)
                fail_list.append(aid)
                continue
        if os.path.isdir(dst): os.replace(dst, backup)
        os.replace(candidate, dst)
        dst_nm = os.path.join(dst, "node_modules")
        if aid == "hermes":
            try:
                fixup_hermes_venv(os.path.join(pdir, "agents", "hermes", pid), dst_nm)
            except Exception as error:
                log_err("Hermes 路径修复失败：%s" % error)
                shutil.rmtree(dst, ignore_errors=True)
                if os.path.isdir(backup): os.replace(backup, dst)
                fail_list.append(aid)
                continue
        env_extra, args_prefix = wire_agnes(a)
        shim = write_shim(a, env_extra, args_prefix, node_path=offline_node)
        if shim:
            shutil.rmtree(backup, ignore_errors=True)
            record_install(a, "offline", os.path.join(
                AB_HOME, "bin", a["bin"] + ("" if POSIX else ".cmd")))
            log_ok(t("menu.offline_ok") % (a["name"], a["bin"]))
            ok_list.append(aid)
        else:
            shutil.rmtree(dst, ignore_errors=True)
            if os.path.isdir(backup): os.replace(backup, dst)
            fail_list.append(aid)
        for note in a.get("notes", []) or []:
            print("  ℹ %s" % note)
    ensure_path_registered()
    print("\n" + t("menu.install_summary") %
          (", ".join(ok_list) or "-", ", ".join(fail_list) or "-"))
    if not POSIX:
        print(t("menu.install_hint_win"))
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


def _npm_package_name_from_spec(spec):
    spec = str(spec or "")
    if spec.startswith("@"):
        slash = spec.find("/")
        version = spec.find("@", slash + 1)
        return spec[:version] if version >= 0 else spec
    return spec.split("@", 1)[0]


def offline_npm_entry(a):
    """Resolve the real npm package bin entry; .bin copies are not relocatable."""
    package_name = _npm_package_name_from_spec(a.get("npm"))
    if not package_name:
        return None
    package_dir = os.path.join(AGENTS_DIR, a["id"], "node_modules", *package_name.split("/"))
    metadata_path = os.path.join(package_dir, "package.json")
    try:
        with open(metadata_path, "r", encoding="utf-8") as source:
            metadata = json.load(source)
        bins = metadata.get("bin")
        if isinstance(bins, str):
            relative = bins
        elif isinstance(bins, dict):
            relative = bins.get(a.get("bin"))
            if not relative and len(bins) == 1:
                relative = next(iter(bins.values()))
        else:
            relative = None
        entry = os.path.normpath(os.path.join(package_dir, relative)) if relative else None
        return entry if entry and _inside(entry, package_dir) and os.path.isfile(entry) else None
    except (OSError, ValueError, TypeError):
        return None


def _npm_entry_kind(entry):
    extension = os.path.splitext(entry)[1].lower()
    if extension in (".js", ".mjs", ".cjs"):
        return "node"
    try:
        with open(entry, "rb") as source:
            first = source.readline(256).lower()
        if first.startswith(b"#!") and b"node" in first:
            return "node"
    except OSError:
        pass
    if extension in (".cmd", ".bat"):
        return "cmd"
    return "direct"


def write_shim(a, env_extra=None, args_prefix=None, node_path=None):
    """为离线安装的 Agent 生成启动 shim。"""
    aid, bin_ = a["id"], a["bin"]
    env_extra = env_extra or {}
    args_prefix = args_prefix or []
    node_path = node_path or node_exe()
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
                lines = _agnes_env_posix_lines(env_extra)
                nd = runtime_node_dir()
                if os.path.isdir(nd):
                    lines.append('[ -x "%s/bin/node" ] && export PATH="%s/bin:$PATH"' % (nd, nd))
                entry = offline_npm_entry(a)
                if not entry:
                    raise ValueError("未找到 %s 的真实 npm bin 入口" % aid)
                pre = " ".join('"%s"' % x for x in args_prefix)
                if _npm_entry_kind(entry) == "node":
                    lines.append('exec "%s" "%s"%s "$@"' %
                                 (node_path, entry, (" " + pre) if pre else ""))
                else:
                    lines.append('exec "%s"%s "$@"' % (entry, (" " + pre) if pre else ""))
                body = "\n".join(lines) + "\n"
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
                lines = ["rem AgentBoot shim (Agnes preset)"]
                lines += _agnes_env_cmd_lines(env_extra)
                entry = offline_npm_entry(a)
                if not entry:
                    raise ValueError("未找到 %s 的真实 npm bin 入口" % aid)
                pre = " ".join(args_prefix)
                kind = _npm_entry_kind(entry)
                if kind == "node":
                    lines.append('"%s" "%s"%s %%*' %
                                 (node_path, entry, (" " + pre) if pre else ""))
                elif kind == "cmd":
                    lines.append('call "%s"%s %%*' % (entry, (" " + pre) if pre else ""))
                else:
                    lines.append('"%s"%s %%*' % (entry, (" " + pre) if pre else ""))
                body = "\r\n".join(lines) + "\r\n"
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("@echo off\r\nrem AgentBoot shim for %s\r\n"
                        'set "AB_ROOT=%%USERPROFILE%%\\.agentboot"\r\n'
                        'if exist "%%AB_ROOT%%\\runtime\\node-win-x64\\node.exe" '
                        'set "PATH=%%AB_ROOT%%\\runtime\\node-win-x64;%%PATH%%"\r\n%s' % (aid, body))
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
        npm_bin = os.path.join(NPM_PREFIX, "bin")
        block = "\n".join([block_begin,
                           '# AgentBoot 添加的 PATH',
                           'for _d in "$HOME/.agentboot/bin" "$HOME/.local/bin" "%s"; do' % npm_bin,
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
                if block_begin in content and block_end in content:
                    before, rest = content.split(block_begin, 1)
                    _old, after = rest.split(block_end, 1)
                    updated = before.rstrip("\n") + "\n" + block + after.lstrip("\n")
                    with open(rc, "w", encoding="utf-8") as f:
                        f.write(updated)
                else:
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
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            log_err("代理地址必须是有效的 http:// 或 https:// URL")
            return False
        data["proxy"] = url
        save_env_json(data)
        os.environ["HTTP_PROXY"] = url
        os.environ["HTTPS_PROXY"] = url
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
        return True
    else:
        data.pop("proxy", None)
        save_env_json(data)
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        if npm_cmd():
            subprocess.run([npm_cmd(), "config", "delete", "proxy"], env=child_env(), capture_output=True)
            subprocess.run([npm_cmd(), "config", "delete", "https-proxy"], env=child_env(), capture_output=True)
        try:
            os.remove(os.path.join(AB_HOME, "env.sh"))
            os.remove(os.path.join(AB_HOME, "env.ps1"))
        except OSError:
            pass
        log_ok("代理已清除")
        return True


def write_env_scripts(url):
    with open(os.path.join(AB_HOME, "env.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write("export HTTP_PROXY=%s\nexport HTTPS_PROXY=%s\n" % (url, url))
    with open(os.path.join(AB_HOME, "env.ps1"), "w", encoding="utf-8") as f:
        f.write("$env:HTTP_PROXY='%s'\n$env:HTTPS_PROXY='%s'\n" % (url, url))


def mirror_status():
    cn = cn_mode()
    print(t("menu.mirror_net") % (t("menu.mirror_cn") if cn else t("menu.mirror_global")))
    print(t("menu.mirror_npm") % npm_current_registry())
    print(t("menu.mirror_npm_mirror") % ("✓" if can_tcp("registry.npmmirror.com") else "✗"))
    print(t("menu.mirror_npmjs") % ("✓" if can_tcp("registry.npmjs.org", 443, 1.5) else "✗"))
    env = load_env_json()
    print(t("menu.mirror_proxy") % (env.get("proxy") or os.environ.get("HTTPS_PROXY") or "-"))
    print(t("menu.mirror_switch") % (os.environ.get("AGENTBOOT_MIRROR") or "auto"))


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
    om, nm = t("menu.offline_mark"), t("menu.online_mark")
    for i, a in enumerate(agents, 1):
        offline_mark = om if a.get("offline") else nm
        mark = " ★" if a.get("custom") else ""
        print("  [%2d] %-16s %-24s (%s) %s%s" % (i, a["id"], a["name"], offline_mark, a.get("desc", ""), mark))
    extra = "  [ a] %s · [ 0] %s" % (t("menu.pick_all_a"), t("menu.pick_back"))
    if allow_custom:
        extra += t("menu.pick_custom")
    print(extra)
    raw = input(t("menu.pick_prompt")).strip().lower()
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


def pick_installed_agents(agents):
    """只显示能证明由 AgentBoot 管理的安装，防止误卸载同名系统命令。"""
    candidates = []
    print("\n%s" % t("menu.uninstall_title"))
    for a in agents:
        status = detect_install(a)
        if status["managed"]:
            candidates.append(a)
            print("  [%2d] %-16s %-24s (%s)" %
                  (len(candidates), a["id"], a["name"], status.get("source") or "legacy"))
    if not candidates:
        print(t("menu.uninstall_empty"))
        return []
    print("  [ 0] %s" % t("menu.pick_back"))
    raw = input(t("menu.pick_prompt")).strip().lower()
    if not raw or raw == "0":
        return []
    ids = []
    known = [a["id"] for a in candidates]
    for tok in re.split(r"[\s,，]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(candidates):
            ids.append(candidates[int(tok) - 1]["id"])
        elif tok in known:
            ids.append(tok)
    return sorted(set(ids), key=known.index)


def menu_model(cfg):
    """模型配置：与 ab /model 同一套提供商管理器（列表/切换/添加/删除/故障切换/测速）。"""
    agent.choose_model(cfg)


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
    print("\n" + t("menu.build_pick_platforms"))
    for i, (pid, desc) in enumerate(BUILD_PLATFORMS, 1):
        print("  [%d] %-14s %s" % (i, pid, desc))
    raw = input("平台编号: ").strip().lower()
    if not raw:
        return [plat_id()]
    ids = []
    for tok in re.split(r"[\s,，]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(BUILD_PLATFORMS):
            ids.append(BUILD_PLATFORMS[int(tok) - 1][0])
        elif tok in [p[0] for p in BUILD_PLATFORMS]:
            ids.append(tok)
    if not ids:
        log_err("未识别任何平台，使用当前平台")
        return [plat_id()]
    return sorted(set(ids), key=lambda x: [p[0] for p in BUILD_PLATFORMS].index(x))


def pick_offline_agents():
    """多选要打进离线包的 Agent（默认全选支持离线的）。返回 id 列表。"""
    capable = [a for a in load_registry() if a.get("offline")]
    print("\n" + t("menu.pick_offline_agents"))
    for i, a in enumerate(capable, 1):
        print("  [%2d] %-14s %-22s %s" % (i, a["id"], a["name"], a.get("desc", "")))
    print(t("menu.build_aider_hint"))
    raw = input(t("menu.pick_prompt")).strip().lower()
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
        log_err(t("menu.build_empty"))
        return False
    log_info(t("menu.build_start") % (",".join(platforms), ",".join(agents_ids)))
    print(t("menu.build_wait") + "\n")
    env = child_env()
    tag = "v" + VERSION
    if POSIX:
        script = os.path.join(APP_DIR, "scripts", "build-offline.sh")
        env.update({"PLATFORMS": ",".join(platforms), "AGENTS": ",".join(agents_ids), "TAG": tag})
        cmd = ["sh", script]
    else:
        script = os.path.join(APP_DIR, "scripts", "build-offline.ps1")
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
               "-Tag", tag, "-Platforms", ",".join(platforms), "-Agents", ",".join(agents_ids)]
    r = subprocess.run(cmd, env=env)
    ok = r.returncode == 0
    if ok:
        dist = os.path.join(APP_DIR, "dist")
        print("")
        log_ok(t("menu.build_done") % dist)
        try:
            for fn in sorted(os.listdir(dist)):
                if fn.startswith("AgentBoot-offline-%s-" % tag):
                    p = os.path.join(dist, fn)
                    if os.path.isfile(p):
                        print("  %-52s %8.1f MB" % (fn, os.path.getsize(p) / 1048576.0))
        except OSError:
            pass
    else:
        log_err(t("menu.build_fail") % r.returncode)
    return ok


def build_offline_wizard():
    platforms = pick_platforms()
    agents_ids = pick_offline_agents()
    if not agents_ids:
        log_err(t("menu.build_empty"))
        return
    print("\n" + t("menu.build_plan") % (", ".join(platforms), ", ".join(agents_ids)))
    if input(t("menu.build_confirm_yn")).strip().lower() in ("n", "no"):
        return
    print(t("menu.build_wait"))
    build_offline_run(platforms, agents_ids)


# ---------------------------------------------------------------- Agnes 预配置（安装即用）

def wire_agnes(a):
    """安装成功后按 Agent 类型预置 Agnes 免费模型。
    返回需要注入启动 shim 的环境变量 dict（config 文件类已直接落盘）。"""
    aid = a["id"]
    home = os.path.expanduser("~")
    agnes = agent.PRESETS["agnes"]
    base, key, model = agnes["base_url"], agnes["api_key"], agnes["model"]

    if aid == "codex":
        d = os.path.join(home, ".codex")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "config.toml")
        block = ('\n# >>> AgentBoot 预置 Agnes 免费模型 >>>\n'
                 'model = "agnes-2.5-flash"\n'
                 'model_provider = "agnes"\n\n'
                 '[model_providers.agnes]\n'
                 'name = "Agnes"\n'
                 'base_url = "https://apihub.agnes-ai.com/v1"\n'
                 'env_key = "AGNES_API_KEY"\n'
                 'wire_api = "chat"\n'
                 '# <<< AgentBoot <<<\n')
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(block)
        else:
            cur = open(p, "r", encoding="utf-8").read()
            if "model_providers.agnes" not in cur:
                with open(p, "a", encoding="utf-8", newline="\n") as f:
                    f.write(block)
        log_ok("已预置 Agnes 免费模型（~/.codex/config.toml）")
        return {"AGNES_API_KEY": key}, []

    if aid == "qwen-code":
        log_ok("已预置 Agnes 免费模型（OPENAI_* 环境变量随 shim 注入）")
        return {"OPENAI_API_KEY": key, "OPENAI_BASE_URL": base, "OPENAI_MODEL": model}, []

    if aid == "aider":
        log_ok("已预置 Agnes 免费模型（shim 自动追加 --model openai/agnes-2.5-flash）")
        return {"OPENAI_API_KEY": key, "OPENAI_API_BASE": base}, ["--model", "openai/" + model]

    if aid == "opencode":
        d = os.path.join(home, ".config", "opencode")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "opencode.json")
        cfg = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "agnes": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Agnes",
                    "options": {"baseURL": base, "apiKey": key},
                    "models": {model: {"name": "Agnes 2.5 Flash (free)"}}}},
            "model": "agnes/" + model}
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            log_ok("已预置 Agnes 免费模型（~/.config/opencode/opencode.json）")
        return {}, []

    return {}, []  # claude-code/gemini-cli 等官方协议登录类，不强行接线


def _agnes_env_cmd_lines(env_extra):
    return ['set "%s=%s"' % (k, v) for k, v in env_extra.items()]


def _agnes_env_posix_lines(env_extra):
    return ['export %s="%s"' % (k, v) for k, v in env_extra.items()]


def write_online_shim(a, found, env_extra, args_prefix=None):
    """在线安装后写包装 shim（注入 Agnes 环境变量并转发到真实命令）。"""
    aid, bin_ = a["id"], a["bin"]
    args_prefix = args_prefix or []
    bin_dir = os.path.join(AB_HOME, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    try:
        if POSIX:
            p = os.path.join(bin_dir, bin_)
            lines = ["#!/bin/sh", "# AgentBoot wrapper: Agnes 预置"]
            lines += _agnes_env_posix_lines(env_extra or {})
            pre = " ".join('"%s"' % x for x in args_prefix)
            lines.append('exec "%s"%s "$@"' % (found, (" " + pre) if pre else ""))
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(p, 0o755)
        else:
            p = os.path.join(bin_dir, bin_ + ".cmd")
            lines = ["@echo off", "rem AgentBoot wrapper: Agnes preset"]
            lines += _agnes_env_cmd_lines(env_extra or {})
            pre = " ".join(args_prefix)
            lines.append('"%s"%s %%*' % (found, (" " + pre) if pre else ""))
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                f.write("\r\n".join(lines) + "\r\n")
        return True
    except Exception as e:
        log_err("写入包装 shim 失败：%s" % e)
        return False


def menu_mirror():
    while True:
        print("\n" + t("menu.mirror_title"))
        mirror_status()
        print(" [1] " + t("menu.mirror_npm_to"))
        print(" [2] " + t("menu.mirror_npm_off"))
        print(" [3] " + t("menu.mirror_proxy_set"))
        print(" [4] " + t("menu.mirror_proxy_clear"))
        print(" [0] " + t("menu.pick_back"))
        c = input(t("menu.pick")).strip()
        if c == "1":
            set_npm_registry(NPM_MIRROR)
        elif c == "2":
            set_npm_registry(NPM_OFFICIAL)
        elif c == "3":
            url = input(t("menu.proxy_addr")).strip()
            if url:
                set_proxy(url)
        elif c == "4":
            set_proxy(None)
        else:
            return


def resolve_lang():
    """语言解析：环境变量 AGENTBOOT_LANG 优先，其次配置文件，默认中文。"""
    cfg = agent.load_config()
    lang = os.environ.get("AGENTBOOT_LANG") or cfg.get("lang") or "zh"
    i18n.set_lang(lang)
    return cfg


def set_lang_persist(lang, cfg=None):
    lang = "en" if str(lang or "").lower().startswith("en") else "zh"
    i18n.set_lang(lang)
    cfg = cfg if isinstance(cfg, dict) else agent.load_config()
    cfg["lang"] = lang
    agent.save_config(cfg)
    if lang == "en":
        log_ok(i18n.t("menu.lang_saved_en"))
    else:
        log_ok(i18n.t("menu.lang_saved"))


def lang_switch(cfg):
    print(i18n.t("menu.lang_title"))
    print(i18n.t("menu.lang_pick"))
    c = input(i18n.t("menu.pick")).strip()
    set_lang_persist("en" if c == "2" else "zh", cfg)


def banner():
    print(r"""
    _                    _            _
   /_\   __ _  ___ _ __ | |_ __ _  __| | ___
  //_\\ / _` |/ _ \ '_ \| __/ _` |/ _` |/ _ \
 /  _  \ (_| |  __/ | | | || (_| | (_| |  __/
 \_/ \_/\__, |\___|_| |_|\__\__,_|\__,_|\___|
        |___/   AgentBoot Console v%s
""" % VERSION)
    print(i18n.t("menu.tagline") + "\n")


def main_menu(cfg=None):
    cfg = cfg if isinstance(cfg, dict) else resolve_lang()
    agents = load_registry()
    while True:
        banner()
        print("  [1] %s" % t("menu.m1"))
        print("  [2] %s" % t("menu.m2"))
        print("  [3] %s" % t("menu.m3"))
        print("  [4] %s" % t("menu.m4"))
        print("  [5] %s" % t("menu.m5"))
        print("  [6] %s" % t("menu.m6"))
        print("  [7] %s" % t("menu.m7"))
        print("  [8] %s" % t("menu.m8"))
        print("  [9] %s" % t("menu.m9"))
        print("  [0] %s" % t("menu.bye"))
        c = input("\n" + t("menu.pick")).strip()
        if c == "1":
            doctor()
            input(t("menu.enter_back"))
        elif c == "2":
            ids = pick_agents(agents, t("menu.pick2_title"), allow_custom=True)
            if ids:
                install_online(ids)
                input(t("menu.enter_back"))
        elif c == "3":
            ids = pick_agents([a for a in agents if a.get("offline")], t("menu.pick3_title"))
            if ids:
                offline_install(ids)
                input(t("menu.enter_back"))
        elif c == "4":
            menu_model(cfg)
        elif c == "5":
            menu_mirror()
            input(t("menu.enter_back"))
        elif c == "6":
            agent.repl(cfg)
        elif c == "7":
            build_offline_wizard()
        elif c == "8":
            lang_switch(cfg)
        elif c == "9":
            ids = pick_installed_agents(agents)
            if ids:
                if input(t("menu.uninstall_confirm") % ", ".join(ids)).strip().lower() in ("y", "yes"):
                    uninstall_agents(ids)
                input(t("menu.enter_back"))
        elif c == "0":
            print(t("menu.bye"))
            return


def main():
    cfg = resolve_lang()
    agent._utf8_console()
    argv = sys.argv[1:]
    if not argv:
        main_menu(cfg)
        return
    cmd = argv[0]
    if cmd == "lang":
        set_lang_persist(argv[1] if len(argv) > 1 else "zh")
        return
    if cmd == "doctor":
        doctor()
    elif cmd == "install":
        ids = [t for t in re.split(r"[,\s]+", " ".join(argv[1:])) if t and not t.startswith("-")]
        if ids:
            failures = install_online(ids)
            if failures:
                raise SystemExit(1)
        else:
            print("用法: menu.py install claude-code qwen-code")
    elif cmd == "offline":
        payload = None
        if "--payload" in argv:
            i = argv.index("--payload")
            payload = argv[i + 1] if i + 1 < len(argv) else None
            rest = argv[1:i] + argv[i + 2:]
        else:
            rest = argv[1:]
        ids = [t for t in re.split(r"[,\s]+", " ".join(rest)) if t and not t.startswith("-")]
        if ids:
            failures = offline_install(ids, payload)
            if failures:
                raise SystemExit(1)
        else:
            print("用法: menu.py offline claude-code --payload <dir>")
    elif cmd in ("uninstall", "remove"):
        purge = "--purge" in argv
        rest = [arg for arg in argv[1:] if arg != "--purge"]
        ids = [tok for tok in re.split(r"[,\s]+", " ".join(rest)) if tok]
        if ids:
            failures = uninstall_agents(ids, purge=purge)
            if failures:
                raise SystemExit(1)
        else:
            print(t("menu.uninstall_usage"))
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
            if len(argv) < 3:
                print("用法: add-agent --del <id>")
                raise SystemExit(2)
            custom_remove_entry(argv[2])
            log_ok("已删除自定义 Agent：%s" % argv[2])
        elif len(argv) >= 4 and argv[2] in ("npm", "pip", "script"):
            aid, m, pkg = argv[1], argv[2], argv[3]
            entry = {"id": aid, "name": aid, "desc": "自定义 Agent", "bin": argv[4] if len(argv) > 4 else aid,
                     "method": m, "requires": [], "notes": ["用户自定义条目"]}
            if not _valid_agent_id(entry["id"]) or not _valid_bin_name(entry["bin"]):
                log_err("id 与命令名只能包含字母、数字、点、下划线与连字符")
                raise SystemExit(2)
            if m == "npm":
                entry["npm"] = pkg
            elif m == "pip":
                entry["pip"] = pkg
            else:
                entry["script"] = pkg
            try:
                custom_add_entry(entry)
            except ValueError as error:
                log_err(str(error))
                raise SystemExit(2)
            log_ok("已添加自定义 Agent：%s（%s）" % (aid, pkg))
        else:
            print(__doc__)
    elif cmd == "build-offline":
        # 用法：build-offline <平台列表> <Agent列表>（逗号分隔），无参数进入向导
        if len(argv) >= 3:
            plats = [t for t in re.split(r"[,\s]+", argv[1]) if t]
            ids = [t for t in re.split(r"[,\s]+", argv[2]) if t]
            if not build_offline_run(plats, ids):
                raise SystemExit(1)
        else:
            build_offline_wizard()
    elif cmd in ("version", "--version"):
        print("AgentBoot 控制台 v%s" % VERSION)
    elif cmd == "menu":
        main_menu(cfg)
    else:
        print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n（已退出）")
