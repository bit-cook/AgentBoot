#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentBoot 内置最小 Agent（命令 ab）
================================
设计目标：单文件、零第三方依赖（仅 Python 标准库）、极速启动。
当其他 Agent 都装不上时，它就是你的保底 Agent：
  * 默认使用 Agnes 免费模型（预置，开箱即用）
  * 支持自定义任意 OpenAI 兼容模型（含 Ollama / LM Studio 等本地模型）
  * 内置离线 Linux 知识库：可查阅 Linux 用法、操作系统、修复常见问题
  * 工具：run_cmd / read_file / write_file / edit_file / list_dir / linux_help / http_get
"""
import json
import os
import re
import subprocess
import sys
import time

VERSION = "1.0.0"
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AB_HOME = os.environ.get("AGENTBOOT_HOME") or os.path.join(os.path.expanduser("~"), ".agentboot")
CONFIG_PATH = os.path.join(AB_HOME, "config.json")
KB_DIR = os.path.join(APP_DIR, "tools", "linux-kb")

# ---------------------------------------------------------------- 基础设施

def _utf8_console():
    """让 Windows 控制台也能正常输出中文。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def ensure_home():
    if not os.path.isdir(AB_HOME):
        os.makedirs(AB_HOME, exist_ok=True)


# Agnes 为官方预设的永久免费模型，开箱即用；其余为常见本地模型示例。
PRESETS = {
    "agnes": {
        "label": "Agnes 免费模型（官方预设）",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "api_key": "sk-2JoDdkRgt4DcVP5hUcrTHFmwIIDS1G6x6rDYe8auHE5nOS5f",
        "model": "agnes-2.5-flash",
    },
    "ollama": {
        "label": "Ollama 本地模型（离线可用）",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "model": "qwen2.5:7b",
    },
    "lmstudio": {
        "label": "LM Studio 本地模型（离线可用）",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "",
        "model": "local-model",
    },
}
DEFAULT_ACTIVE = "agnes"


def default_config():
    return {
        "active": DEFAULT_ACTIVE,
        "providers": {},
        "confirm": "smart",   # smart=危险命令需确认 / always=全部放行 / safe=只放行只读命令
        "max_steps": 12,
    }


def load_config():
    ensure_home()
    if not os.path.exists(CONFIG_PATH):
        cfg = default_config()
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = default_config()
    for k, v in default_config().items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    ensure_home()
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def get_provider(cfg, name=None):
    name = name or cfg.get("active") or DEFAULT_ACTIVE
    p = dict((cfg.get("providers") or {}).get(name) or PRESETS.get(name) or {})
    if not p:
        p = dict(PRESETS[DEFAULT_ACTIVE])
        name = DEFAULT_ACTIVE
    p["name"] = name
    return p


def set_provider(cfg, name, base_url, api_key, model):
    cfg.setdefault("providers", {})[name] = {
        "base_url": base_url, "api_key": api_key, "model": model,
    }
    cfg["active"] = name
    save_config(cfg)


# ---------------------------------------------------------------- 模型 API（OpenAI 兼容）

class ApiError(Exception):
    pass


def _split_base(base_url):
    from urllib.parse import urlsplit
    u = (base_url or "").strip().rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    if not u.endswith("/v1"):
        u += "/v1"
    s = urlsplit(u)
    port = s.port or (443 if s.scheme == "https" else 80)
    return s.scheme, s.hostname, port, (s.path or "") + "/chat/completions"


def chat(cfg, messages, stream_cb=None, tools=None, max_tokens=None, temperature=0.7):
    """调用 OpenAI 兼容接口。返回 (content, tool_calls)。stream_cb 用于流式打印增量文本。"""
    import http.client
    import ssl

    p = get_provider(cfg)
    scheme, host, port, path = _split_base(p.get("base_url", ""))
    if not host:
        raise ApiError("模型接口地址为空，请先运行 `ab model` 或在菜单里配置模型。")

    body = {"model": p.get("model"), "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    if max_tokens:
        body["max_tokens"] = max_tokens
    if stream_cb is not None:
        body["stream"] = True

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if p.get("api_key"):
        headers["Authorization"] = "Bearer " + p["api_key"]

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if scheme == "https":
        ctx = ssl.create_default_context()
        if os.environ.get("AGENTBOOT_INSECURE") == "1":
            ctx = ssl._create_unverified_context()
        conn = http.client.HTTPSConnection(host, port, timeout=180, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=180)

    last_err = None
    for attempt in range(3):
        try:
            conn.request("POST", path, body=payload, headers=headers)
            resp = conn.getresponse()
            if resp.status != 200:
                data = resp.read(8192).decode("utf-8", "replace")
                conn.close()
                try:
                    j = json.loads(data)
                    msg = j.get("error", {}).get("message") or data
                except Exception:
                    msg = data
                if resp.status < 500:
                    raise ApiError("HTTP %s：%s" % (resp.status, msg[:400]))
                raise ApiError("HTTP %s：%s" % (resp.status, msg[:400]))
            if stream_cb is None:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                conn.close()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                return msg.get("content") or "", msg.get("tool_calls") or []
            return _read_stream(resp, stream_cb, conn)
        except ApiError:
            try:
                conn.close()
            except Exception:
                pass
            raise
        except Exception as e:  # 网络类错误：退避重试
            last_err = e
            try:
                conn.close()
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1 + attempt)
                if scheme == "https":
                    ctx = ssl.create_default_context()
                    if os.environ.get("AGENTBOOT_INSECURE") == "1":
                        ctx = ssl._create_unverified_context()
                    conn = http.client.HTTPSConnection(host, port, timeout=180, context=ctx)
                else:
                    conn = http.client.HTTPConnection(host, port, timeout=180)
    raise ApiError("无法连接模型接口：%s（若需代理，请先设置 HTTP_PROXY/HTTPS_PROXY）" % last_err)


def _read_stream(resp, stream_cb, conn):
    content_parts = []
    tool_calls = {}  # index -> {"id","name","arguments"}

    def flush_tc():
        out = []
        for idx in sorted(tool_calls):
            tc = tool_calls[idx]
            out.append({
                "id": tc.get("id") or ("call_%s" % idx),
                "type": "function",
                "function": {"name": tc.get("name") or "", "arguments": tc.get("arguments") or ""},
            })
        return out

    try:
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            for choice in obj.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                    stream_cb(piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = (slot["name"] + fn["name"]) if slot["name"] else fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
    finally:
        try:
            conn.close()
        except Exception:
            pass

    content = "".join(content_parts)
    tcs = flush_tc()
    if not content and not tcs:
        raise ApiError("模型返回为空（流式）。")
    return content, tcs


def test_provider(cfg, name=None):
    """连通性测试：让模型回一个字。"""
    try:
        content, _ = chat(cfg, [{"role": "user", "content": "请只回复两个字：正常"}],
                          stream_cb=None, max_tokens=16, temperature=0)
        return True, (content or "").strip()[:40] or "（空响应）"
    except Exception as e:
        return False, str(e)[:300]


# ---------------------------------------------------------------- 离线 Linux 知识库

_KB_CACHE = None


def _kb_sections():
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE
    sections = []
    if os.path.isdir(KB_DIR):
        for fn in sorted(os.listdir(KB_DIR)):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(KB_DIR, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            parts = re.split(r"(?m)^##\s+", text)
            for part in parts[1:]:
                lines = part.splitlines()
                title = lines[0].strip() if lines else fn
                body = "\n".join(lines[1:]).strip()
                sections.append({"file": fn, "title": title, "body": body})
    _KB_CACHE = sections
    return sections


def linux_help(query):
    """在离线知识库中检索最相关的段落。中文整句自动做 2 字词片段匹配。"""
    q = (query or "").strip()
    if not q:
        return "（请给出关键词，例如：磁盘满了怎么办）"
    # 去掉疑问词后分词；整句无空格时再用 2 字滑动片段兜底
    base = re.sub(r"(怎么办|怎么回事|怎么|如何|为什么|为啥|什么原因|咋|呢|吗|？|\?|！|。|，)", " ", q.lower())
    toks = [(t, 3) for t in re.split(r"[\s,，。/?！]+", base) if t]
    core = re.sub(r"[\s,，。/?！]+", "", base)
    grams = [(core[i:i + 2], 1) for i in range(max(0, len(core) - 1))]
    scored = []
    for sec in _kb_sections():
        title = sec["title"].lower()
        body = (sec["title"] + "\n" + sec["body"]).lower()
        score = 0
        for t, w in toks:
            if t in title:
                score += 3 * w
            if t in body:
                score += w
        for g, w in grams:
            if g in title:
                score += 2 * w
            elif g in body:
                score += w
        if score:
            scored.append((score, sec))
    if not scored:
        scored.sort(key=lambda x: -x[0])
        return "知识库中没有直接匹配「%s」的内容。\n可用主题：%s" % (
            q, "、".join(sorted({s['file'].replace('.md', '') for s in _kb_sections()})))
    scored.sort(key=lambda x: -x[0])
    outs = []
    for score, sec in scored[:3]:
        body = sec["body"]
        if len(body) > 1600:
            body = body[:1600] + "\n…（已截断）"
        outs.append("【%s · %s】\n%s" % (sec["file"].replace(".md", ""), sec["title"], body))
    return "\n\n".join(outs)


# ---------------------------------------------------------------- 工具实现

SAFE_FIRST = {
    "ls", "cat", "pwd", "head", "tail", "wc", "grep", "find", "stat", "file",
    "df", "du", "free", "ps", "uname", "uptime", "which", "whereis", "id",
    "whoami", "hostname", "date", "ip", "ss", "ping", "dig", "nslookup",
    "echo", "lscpu", "lsblk", "lsmod", "lspci", "lsusb", "env", "printenv",
    "systemctl", "journalctl", "dmesg", "man", "apropos", "top", "vmstat",
    "iostat", "sar", "netstat", "route", "arp", "getenforce", "sestatus",
    # Windows 常见只读命令
    "dir", "type", "ipconfig", "systeminfo", "tasklist", "ver", "whoami",
    "netstat", "where", "wmic", "sc", "driverquery", "hostname",
}

DANGER_RE = [
    r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)*[/~]", r"\bmkfs(\.\w+)?\b", r"\bdd\b\s+if=",
    r"\bshutdown\b", r"\breboot\b", r"\binit\s+0\b", r"\bhalt\b", r"\bpoweroff\b",
    r">\s*/dev/sd[a-z]", r"\bfdisk\b", r"\bparted\b", r"\bwipefs\b", r"\bgdisk\b",
    r"\bchmod\s+-R\s+777\s+/\b", r"\bchown\s+-R\s+\S+\s+/\s*$", r"\bgit\s+push\s+.*--force",
    r"\bdrop\s+(database|table)\b", r":\(\)\{.*\};:", r"\bcurl\b[^\n|]*\|\s*(ba)?sh\b",
    r"\bwget\b[^\n|]*\|\s*(ba)?sh\b", r"\bformat\b\s+[a-c]:", r"\bdel\s+/[sfq]",
    r"\brd\s+/s\b", r"\bRemove-Item\s+.*-Recurse.*-Force\s+-Path\s+[\"']?[A-Za-z]:\\",
    r"\btruncate\s+-s\s*0\s+/", r"\bmv\b\s+.*\s+/dev/null", r"\biptables\s+-F\b",
    r"\bufw\s+disable\b", r"\bswapoff\b", r"\buserdel\b", r"\bpasswd\s+-d\b",
]


def classify_cmd(cmd):
    c = cmd.strip()
    low = c.lower()
    for pat in DANGER_RE:
        if re.search(pat, low):
            return "danger"
    first = re.split(r"[\s|;&]+", low)[0] if low else ""
    path_first = os.path.basename(first)
    if first in SAFE_FIRST or path_first in SAFE_FIRST:
        return "safe"
    return "normal"


def run_cmd(cmd, timeout=60):
    timeout = min(max(int(timeout or 60), 5), 300)
    shell = ["cmd", "/c", cmd] if os.name == "nt" else ["/bin/sh", "-c", cmd]
    try:
        r = subprocess.run(shell, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        out = ((r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr.strip() else "")).strip()
        code = r.returncode
    except subprocess.TimeoutExpired:
        out, code = "（命令超时 %ss，已终止）" % timeout, 124
    except FileNotFoundError as e:
        out, code = "启动 shell 失败：%s" % e, 127
    if len(out) > 8000:
        half = 4000
        out = out[:half] + "\n…（输出过长，已截断中间部分）…\n" + out[-half:]
    return "exit=%d\n%s" % (code, out or "（无输出）")


def read_file(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return "错误：文件不存在：%s" % path
    if os.path.isdir(path):
        return "错误：这是一个目录，请用 list_dir：%s" % path
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(24000)
        if size > 24000:
            data += "\n…（文件较大，仅显示前 24000 字符）"
        return data or "（空文件）"
    except Exception as e:
        return "读取失败：%s" % e


def write_file(path, content):
    path = os.path.expanduser(path)
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or "")
        return "已写入 %s（%d 字符）" % (path, len(content or ""))
    except Exception as e:
        return "写入失败：%s" % e


def edit_file(path, old, new):
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return "读取失败：%s" % e
    n = text.count(old)
    if n == 0:
        return "错误：未找到要替换的内容（old 必须与文件内容完全一致）"
    if n > 1:
        return "错误：old 出现了 %d 次，为安全起见请提供更长的唯一片段" % n
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace(old, new, 1))
    return "已修改 %s" % path


def list_dir(path="."):
    path = os.path.expanduser(path or ".")
    if not os.path.isdir(path):
        return "错误：目录不存在：%s" % path
    try:
        entries = sorted(os.listdir(path))
    except Exception as e:
        return "列出失败：%s" % e
    lines = []
    for name in entries[:300]:
        full = os.path.join(path, name)
        if os.path.isdir(full):
            lines.append(name + "/")
        else:
            try:
                lines.append("%s  (%d B)" % (name, os.path.getsize(full)))
            except Exception:
                lines.append(name)
    return "\n".join(lines) or "（空目录）"


def http_get(url):
    if not re.match(r"^https?://", url or ""):
        return "错误：仅支持 http/https 地址"
    try:
        from urllib.request import Request, urlopen
        req = Request(url, headers={"User-Agent": "AgentBoot/1.0"})
        with urlopen(req, timeout=15) as r:
            data = r.read(300000)
        text = data.decode("utf-8", "replace")
        if len(data) >= 299000:
            text += "\n…（已截断）"
        return text if text.strip() else "（空响应）"
    except Exception as e:
        return "抓取失败：%s" % e


# ---------------------------------------------------------------- 工具 schema（OpenAI 格式）

TOOLS = [
    {"type": "function", "function": {"name": "run_cmd", "description": "在本机执行 shell 命令并返回输出。用于查看系统状态、操作 Linux、诊断和修复问题。",
     "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "要执行的命令"}, "timeout": {"type": "integer", "description": "超时秒数(5-300)，默认60"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取文本文件内容。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "写入/覆盖文本文件。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "精确替换文件中的一段文本（old 必须在文件中唯一）。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "列出目录内容。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "linux_help", "description": "查询离线 Linux 知识库（命令用法、服务管理、网络、磁盘、故障排查等）。回答 Linux 问题前应优先查询。",
     "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "关键词，如：查看端口占用 / systemd 服务管理 / 磁盘满了"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "http_get", "description": "抓取一个网页/接口的文本内容（上限300KB）。",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
]


def execute_tool(cfg, name, args, session_allow):
    """执行工具，返回 (结果文本, 是否危险命令)。"""
    if name == "run_cmd":
        cmd = args.get("command", "")
        level = classify_cmd(cmd)
        if level == "danger" and cfg.get("confirm") != "always" and cmd not in session_allow:
            return "已拦截高危命令（如需放行请在交互模式下确认，或修改配置 confirm=always）：%s" % cmd, True
        if level != "safe" and cfg.get("confirm") == "smart" and cmd not in session_allow:
            if _is_interactive():
                print("\n  ⚠ 将执行命令：\n    %s" % cmd)
                ans = input("  允许执行? [y=允许 / n=拒绝 / a=本会话总是允许] ").strip().lower()
                if ans == "a":
                    session_allow.add(cmd)
                elif ans != "y":
                    return "用户拒绝了该命令。", False
            # 非交互（run 模式/管道）：放行普通命令，仅拦截 danger
        return run_cmd(cmd, args.get("timeout")), level == "danger"
    if name == "read_file":
        return read_file(args.get("path", "")), False
    if name == "write_file":
        if _is_interactive():
            print("  ✎ 写入文件：%s" % args.get("path", ""))
        return write_file(args.get("path", ""), args.get("content", "")), False
    if name == "edit_file":
        if _is_interactive():
            print("  ✎ 修改文件：%s" % args.get("path", ""))
        return edit_file(args.get("path", ""), args.get("old", ""), args.get("new", "")), False
    if name == "list_dir":
        return list_dir(args.get("path", ".")), False
    if name == "linux_help":
        return linux_help(args.get("query", "")), False
    if name == "http_get":
        return http_get(args.get("url", "")), False
    return "未知工具：%s" % name, False


def _is_interactive():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


# ---------------------------------------------------------------- Agent 主循环

def system_prompt():
    plat = "%s / %s" % (platform_info(), sys.platform)
    return (
        "你是 AgentBoot 内置的终端智能助手（ab），直接运行在用户本机，当前系统：%s。\n"
        "你可以调用工具：执行命令、读写文件、查询离线 Linux 知识库、抓取网页。\n"
        "守则：\n"
        "1. 始终用简体中文，回答简洁、直接、可执行。\n"
        "2. 涉及 Linux 命令用法、报错、配置时，先用 linux_help 查询离线知识库。\n"
        "3. 修复问题前先用只读命令确认现状（如 df/free/systemctl status），再动手。\n"
        "4. 高危操作（删除、格式化、重启、改分区）必须先说明后果。\n"
        "5. 给用户的命令放入独立代码块。\n"
        "6. 任务完成后简述做了什么、结果如何。" % plat
    )


def platform_info():
    try:
        import platform
        return "%s %s" % (platform.system(), platform.release())
    except Exception:
        return "unknown"


def agent_loop(cfg, user_text, history=None, stream=True):
    """执行一轮完整任务，返回 (最终回复, 新历史)。"""
    history = history or []
    msgs = [{"role": "system", "content": system_prompt()}]
    msgs += history[-12:]
    msgs.append({"role": "user", "content": user_text})
    session_allow = set()
    final = ""
    for _ in range(int(cfg.get("max_steps", 12))):
        cb = (lambda piece: (sys.stdout.write(piece), sys.stdout.flush())) if (stream and _is_interactive()) else None
        if cb:
            sys.stdout.write("\n")
            sys.stdout.flush()
        content, tool_calls = chat(cfg, msgs, stream_cb=cb, tools=TOOLS)
        if cb:
            sys.stdout.write("\n")
            sys.stdout.flush()
        if not tool_calls:
            final = content
            break
        assistant_msg = {"role": "assistant", "content": content or "", "tool_calls": tool_calls}
        msgs.append(assistant_msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except Exception:
                args = {"command": fn.get("arguments", "")} if name == "run_cmd" else {}
            short = json.dumps(args, ensure_ascii=False)
            if len(short) > 160:
                short = short[:160] + "…"
            print("  ▸ %s %s" % (name, short))
            result, _danger = execute_tool(cfg, name, args, session_allow)
            if len(result) > 9000:
                result = result[:9000] + "\n…（已截断）"
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
    else:
        final = content or "（达到最大步数限制，已停止）"
    history = history + [{"role": "user", "content": user_text}, {"role": "assistant", "content": final or ""}]
    return final, history


# ---------------------------------------------------------------- 交互界面

BANNER = r"""
   _                    _            _
  /_\   __ _  ___ _ __ | |_ __ _  __| | ___
 //_\\ / _` |/ _ \ '_ \| __/ _` |/ _` |/ _ \
/  _  \ (_| |  __/ | | | || (_| | (_| |  __/
\_/ \_/\__, |\___|_| |_|\__\__,_|\__,_|\___|
       |___/   AgentBoot 内置 Agent v%s
""" % VERSION


HELP_TEXT = """命令：
  /帮助 /help        显示本帮助
  /模型 /model       查看或切换模型（/model 可进入交互选择）
  /linux <关键词>    直接查离线 Linux 知识库
  /清空 /clear       清空本轮对话历史
  /状态 /status      显示当前模型与配置
  /退出 /exit        退出
直接输入问题或任务即可，例如：
  查一下这台机器磁盘占用情况，若有异常给出清理建议
  nginx 起不来怎么排查？
"""


def choose_model(cfg):
    names = list(PRESETS.keys()) + [n for n in (cfg.get("providers") or {}) if n not in PRESETS]
    print("\n可用模型源：")
    for i, n in enumerate(names, 1):
        p = get_provider(cfg, n)
        mark = " ← 当前" if n == cfg.get("active") else ""
        print("  [%d] %-10s %s  (%s)%s" % (i, n, p.get("model", ""), p.get("label", "自定义"), mark))
    print("  [n] 新增自定义 OpenAI 兼容模型（支持本地模型）")
    print("  [0] 取消")
    choice = input("选择: ").strip().lower()
    if choice == "0" or choice == "":
        return
    if choice == "n":
        print("示例：Agnes=https://apihub.agnes-ai.com/v1 · Ollama=http://127.0.0.1:11434/v1 · LM Studio=http://127.0.0.1:1234/v1")
        base = input("Base URL: ").strip()
        key = input("API Key（可留空）: ").strip()
        model = input("模型 ID: ").strip()
        if not base or not model:
            print("✗ Base URL 与模型 ID 不能为空")
            return
        name = "custom-%d" % (len([n for n in (cfg.get("providers") or {}) if n.startswith("custom")]) + 1)
        set_provider(cfg, name, base, key, model)
    else:
        try:
            name = names[int(choice) - 1]
        except (ValueError, IndexError):
            print("✗ 无效选择")
            return
        cfg["active"] = name
        save_config(cfg)
    p = get_provider(cfg)
    print("⏳ 正在测试 %s（%s）…" % (p["name"], p["model"]))
    ok, msg = test_provider(cfg)
    print(("✓ 连通正常：%s" % msg) if ok else ("✗ 测试失败：%s" % msg))


def show_status(cfg):
    p = get_provider(cfg)
    print("当前模型源: %s\n接口: %s\n模型: %s\n确认策略: %s\n配置文件: %s" % (
        p["name"], p.get("base_url"), p.get("model"), cfg.get("confirm"), CONFIG_PATH))


def repl(cfg):
    print(BANNER)
    p = get_provider(cfg)
    print("模型: %s @ %s（Agnes 官方免费预设，可用 /model 切换）" % (p.get("model"), p.get("base_url")))
    print(HELP_TEXT)
    history = []
    while True:
        try:
            text = input("\n你 › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            return
        if not text:
            continue
        low = text.lower()
        if low in ("/exit", "/quit", "/退出", "/q"):
            print("再见！")
            return
        if low in ("/help", "/帮助", "?"):
            print(HELP_TEXT)
            continue
        if low in ("/model", "/模型"):
            choose_model(cfg)
            p = get_provider(cfg)
            print("当前模型: %s @ %s" % (p.get("model"), p.get("base_url")))
            continue
        if low.startswith("/linux"):
            q = text[6:].strip()
            print(linux_help(q) if q else "用法：/linux <关键词>")
            continue
        if low in ("/clear", "/清空"):
            history = []
            print("已清空对话历史。")
            continue
        if low in ("/status", "/状态"):
            show_status(cfg)
            continue
        try:
            _final, history = agent_loop(cfg, text, history)
        except KeyboardInterrupt:
            print("\n（已中断本条任务）")
        except ApiError as e:
            print("✗ %s" % e)
        except Exception as e:
            print("✗ 出错：%s" % e)


def doctor(cfg):
    print("AgentBoot 环境体检 v%s" % VERSION)
    print("-" * 46)
    print("Python   : %s.%s.%s %s" % (*sys.version_info[:3], sys.executable))
    p = get_provider(cfg)
    print("模型源   : %s（%s @ %s）" % (p["name"], p.get("model"), p.get("base_url")))
    ok, msg = test_provider(cfg)
    print("模型连通 : %s %s" % ("✓" if ok else "✗", msg if not ok else ""))
    n_kb = len(_kb_sections())
    print("Linux知识库: %s（%d 个主题段落）" % ("✓" if n_kb else "✗ 缺失 tools/linux-kb", n_kb))
    for tool, host in (("node", None), ("npm", None), ("git", None)):
        import shutil
        path = shutil.which(tool)
        print("%-8s : %s" % (tool, path or "未安装（可由菜单安装/自动下载运行时）"))
    for name, host in (("npm镜像(registry.npmmirror.com)", "registry.npmmirror.com"),
                       ("GitHub(api.github.com)", "api.github.com"),
                       ("模型(apihub.agnes-ai.com)", "apihub.agnes-ai.com")):
        try:
            import socket
            socket.create_connection((host, 443), timeout=2).close()
            print("网络     : ✓ %s" % name)
        except Exception:
            print("网络     : ✗ %s 不可达" % name)
    print("-" * 46)
    print("启动 Agent：ab   ·   打开控制台菜单：agentboot")


# ---------------------------------------------------------------- 入口

def main():
    _utf8_console()
    cfg = load_config()
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "chat"
    args = argv[1:]
    if cmd in ("help", "--help", "-h"):
        print(__doc__)
        print("用法: ab [chat|run <任务>|model|doctor|linux <关键词>|version]")
        return
    if cmd in ("version", "--version", "-v"):
        print("AgentBoot Agent v%s" % VERSION)
        return
    if cmd == "doctor":
        doctor(cfg)
        return
    if cmd in ("model", "--model"):
        _utf8_console()
        if _is_interactive():
            show_status(cfg)
            choose_model(cfg)
        else:
            print("请在交互终端运行：ab model")
        return
    if cmd == "linux":
        print(linux_help(" ".join(args)))
        return
    if cmd == "run":
        if not args:
            print("用法: ab run \"你的任务\"")
            return
        final, _ = agent_loop(cfg, " ".join(args), stream=(not _is_interactive()))
        if final and not _is_interactive():
            print(final)
        return
    if cmd == "chat":
        if _is_interactive():
            repl(cfg)
        else:
            text = sys.stdin.read().strip()
            if text:
                final, _ = agent_loop(cfg, text, stream=False)
                print(final or "")
        return
    # 兜底：把参数当作任务直接执行
    final, _ = agent_loop(cfg, " ".join([cmd] + args), stream=False)
    if final:
        print(final)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n（已退出）")
