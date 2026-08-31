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
import ipaddress
import os
import re
import shlex
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n  # noqa: E402

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    VERSION = open(os.path.join(APP_DIR, "VERSION"), "r", encoding="ascii").read().strip()
except OSError:
    VERSION = "1.2.0"
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
    os.makedirs(AB_HOME, mode=0o700, exist_ok=True)
    try:
        os.chmod(AB_HOME, 0o700)
    except OSError:
        pass


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
        "lang": "zh",         # 界面语言：zh（默认）/ en
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
    if not isinstance(cfg, dict):
        cfg = default_config()
    if not isinstance(cfg.get("providers"), dict):
        cfg["providers"] = {}
    confirm = str(cfg.get("confirm", "smart")).strip().lower()
    cfg["confirm"] = confirm if confirm in ("safe", "smart", "always") else "smart"
    raw_steps = cfg.get("max_steps", 12)
    try:
        steps = int(raw_steps)
    except (TypeError, ValueError):
        steps = 12
    cfg["max_steps"] = 12 if steps < 1 else min(steps, 50)
    cfg["lang"] = "en" if str(cfg.get("lang", "zh")).lower().startswith("en") else "zh"
    if not isinstance(cfg.get("fallback", []), list):
        cfg["fallback"] = []
    for k, v in default_config().items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    ensure_home()
    _atomic_private_json(CONFIG_PATH, cfg)


def _atomic_private_json(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def get_provider(cfg, name=None):
    name = name or cfg.get("active") or DEFAULT_ACTIVE
    p = dict((cfg.get("providers") or {}).get(name) or PRESETS.get(name) or {})
    if not p:
        p = dict(PRESETS[DEFAULT_ACTIVE])
        name = DEFAULT_ACTIVE
    p["name"] = name
    return p


def set_provider(cfg, name, base_url, api_key, model, activate=True):
    cfg.setdefault("providers", {})[name] = {
        "base_url": base_url, "api_key": api_key, "model": model,
    }
    if activate:
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
    if s.scheme not in ("http", "https"):
        raise ApiError("模型接口仅支持 https；本地无密钥模型可使用回环 http。")
    if not s.hostname:
        raise ApiError("模型接口地址缺少主机名。")
    port = s.port or (443 if s.scheme == "https" else 80)
    return s.scheme, s.hostname, port, (s.path or "") + "/chat/completions"


def _is_literal_loopback(host):
    if str(host or "").lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host).strip("[]")).is_loopback
    except ValueError:
        return False


def _validate_model_transport(scheme, host, api_key):
    if scheme == "https":
        return
    if scheme == "http" and _is_literal_loopback(host) and not api_key:
        return
    raise ApiError("拒绝不安全的模型接口：仅允许 HTTPS，或无 API Key 的 localhost/回环 HTTP。")


# 连接池：复用 TLS 连接，砍掉每轮对话的握手开销（极限性能核心）
_POOL = {}
_SSL_CONTEXTS = {}


def _ssl_context():
    import ssl
    insecure = os.environ.get("AGENTBOOT_INSECURE") == "1"
    context = _SSL_CONTEXTS.get(insecure)
    if context is None:
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        _SSL_CONTEXTS[insecure] = context
    return context


def _connect(scheme, host, port, timeout=180):
    import http.client
    from urllib.parse import urlsplit
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy_url:
        try:
            env_path = os.path.join(AB_HOME, "env.json")
            with open(env_path, "r", encoding="utf-8") as source:
                proxy_url = (json.load(source) or {}).get("proxy")
        except Exception:
            proxy_url = None
    proxy = urlsplit(proxy_url) if proxy_url else None
    if proxy and (proxy.scheme not in ("http", "https") or not proxy.hostname):
        raise ApiError("代理地址无效，仅支持 http/https。")
    key = (scheme, host, port, proxy_url or "")
    conn = _POOL.get(key)
    if conn is not None:
        return conn
    if scheme == "https":
        ctx = _ssl_context()
        if proxy:
            conn = http.client.HTTPSConnection(proxy.hostname, proxy.port or (443 if proxy.scheme == "https" else 80),
                                               timeout=timeout, context=ctx)
            tunnel_headers = {}
            if proxy.username:
                import base64
                raw = "%s:%s" % (proxy.username, proxy.password or "")
                tunnel_headers["Proxy-Authorization"] = "Basic " + base64.b64encode(raw.encode()).decode()
            conn.set_tunnel(host, port, headers=tunnel_headers)
        else:
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    elif scheme == "http":
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    else:
        raise ApiError("不支持的模型接口协议：%s" % scheme)
    _POOL[key] = conn
    return conn


def _drop_pool(scheme, host, port):
    keys = [key for key in _POOL if key[:3] == (scheme, host, port)]
    for key in keys:
        conn = _POOL.pop(key, None)
        if conn is None:
            continue
        try:
            conn.close()
        except Exception:
            pass


class StreamInterrupted(ApiError):
    """流式响应中断且未收到任何内容（可安全重试）。"""


def chat(cfg, messages, stream_cb=None, tools=None, max_tokens=None, temperature=0.7):
    """调用 OpenAI 兼容接口（连接复用 + 自动重试）。返回 (content, tool_calls)。"""
    p = get_provider(cfg)
    scheme, host, port, path = _split_base(p.get("base_url", ""))
    if not host:
        raise ApiError("模型接口地址为空，请先运行 `ab model` 或在菜单里配置模型。")
    _validate_model_transport(scheme, host, p.get("api_key"))

    body = {"model": p.get("model"), "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    if max_tokens:
        body["max_tokens"] = max_tokens
    if stream_cb is not None:
        body["stream"] = True

    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "Connection": "keep-alive"}
    if p.get("api_key"):
        headers["Authorization"] = "Bearer " + p["api_key"]

    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    last_err = None
    for attempt in range(3):
        try:
            conn = _connect(scheme, host, port)
            conn.request("POST", path, body=payload, headers=headers)
            resp = conn.getresponse()
            if resp.status != 200:
                data = resp.read(8192).decode("utf-8", "replace")
                try:
                    msg = json.loads(data).get("error", {}).get("message") or data
                except Exception:
                    msg = data
                if resp.status >= 500:
                    _drop_pool(scheme, host, port)   # 服务端异常：弃用连接后重试
                    last_err = ApiError("HTTP %s：%s" % (resp.status, msg[:400]))
                    if attempt < 2:
                        time.sleep(1 + attempt)
                        continue
                    raise last_err
                raise ApiError("HTTP %s：%s" % (resp.status, msg[:400]))
            if stream_cb is None:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                return msg.get("content") or "", msg.get("tool_calls") or []
            return _read_stream(resp, stream_cb, conn, scheme, host, port)
        except StreamInterrupted as e:
            last_err = e
            _drop_pool(scheme, host, port)
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            raise ApiError("模型流在完成前中断，请重试。")
        except ApiError:
            raise
        except Exception as e:   # 网络类错误：连接可能已坏，弃用后重建重试
            last_err = e
            _drop_pool(scheme, host, port)
            if attempt < 2:
                time.sleep(1 + attempt)
    raise ApiError("无法连接模型接口：%s（若需代理，请先设置 HTTP_PROXY/HTTPS_PROXY）" % last_err)


def _read_stream(resp, stream_cb, conn, scheme, host, port):
    content_parts = []
    tool_calls = {}
    terminal = False
    malformed = False

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
                terminal = True
                break
            try:
                obj = json.loads(data)
            except Exception:
                malformed = True
                break
            for choice in obj.get("choices") or []:
                if choice.get("finish_reason") is not None:
                    terminal = True
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
        try:
            resp.read()   # 排空剩余分块，保持连接可复用
        except Exception:
            pass
    except Exception:
        partial = "".join(content_parts)
        _drop_pool(scheme, host, port)
        if partial:
            raise ApiError("模型流中断（已收到部分文本，未执行任何工具）。")
        raise StreamInterrupted("")
    if malformed:
        _drop_pool(scheme, host, port)
        raise ApiError("模型流包含无效 JSON，已拒绝处理。")
    if not terminal:
        _drop_pool(scheme, host, port)
        if content_parts:
            raise ApiError("模型流在完成前中断（已收到部分文本，未执行任何工具）。")
        raise StreamInterrupted("")
    content = "".join(content_parts)
    tcs = flush_tc()
    for tc in tcs:
        try:
            parsed = json.loads(tc["function"]["arguments"] or "{}")
        except (TypeError, ValueError):
            raise ApiError("模型返回了不完整的工具参数 JSON，已拒绝执行。")
        if not tc["function"]["name"] or not isinstance(parsed, dict):
            raise ApiError("模型返回了无效的工具参数，已拒绝执行。")
    if not content and not tcs:
        raise ApiError("模型返回为空（流式）。")
    return content, tcs


def chat_auto(cfg, messages, stream_cb=None, **kw):
    """主模型源失败时自动切换备用源（cfg["fallback"]: 备用模型源名列表）。"""
    order = [cfg.get("active") or DEFAULT_ACTIVE]
    for n in (cfg.get("fallback") or []):
        if n and n not in order:
            order.append(n)
    if len(order) == 1:
        return chat(cfg, messages, stream_cb=stream_cb, **kw)
    last = None
    for i, name in enumerate(order):
        c2 = dict(cfg)
        c2["active"] = name
        try:
            return chat(c2, messages, stream_cb=stream_cb, **kw)
        except ApiError as e:
            last = e
            if i < len(order) - 1:
                sys.stdout.write(i18n.t("agent.failover") % (name, order[i + 1]))
            continue
    raise last


def _ttfb(cfg, prompt="回复：1"):
    """测量首包延迟（毫秒）：从发起到收到第一个 SSE 数据行（HTTP 层，不依赖正文）。"""
    p = get_provider(cfg)
    scheme, host, port, path = _split_base(p.get("base_url", ""))
    body = {"model": p.get("model"), "messages": [{"role": "user", "content": prompt}],
            "stream": True, "max_tokens": 8, "temperature": 0}
    headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
    if p.get("api_key"):
        headers["Authorization"] = "Bearer " + p["api_key"]
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    t0 = time.perf_counter()
    try:
        conn = _connect(scheme, host, port)
        conn.request("POST", path, body=payload, headers=headers)
        resp = conn.getresponse()
        while True:
            line = resp.readline()
            if not line:
                break
            s = line.decode("utf-8", "replace").strip()
            if s.startswith("data:") and s[5:].strip() not in ("", "[DONE]"):
                elapsed = (time.perf_counter() - t0) * 1000.0
                # 首字到达时立即停表，再排空极短响应，使第二轮真实复用同一连接。
                try:
                    resp.read()
                except Exception:
                    _drop_pool(scheme, host, port)
                return elapsed
        return None
    except Exception:
        _drop_pool(scheme, host, port)
        return None


def _shrink(msgs, budget=60000, keep_recent=8):
    """上下文预算控制：超出预算时，把较老的大段工具输出替换为省略标记。"""
    total = sum(len(str(m.get("content") or "")) for m in msgs)
    if total <= budget:
        return
    for i in range(len(msgs)):
        if len(msgs) - i <= keep_recent or total <= budget:
            break
        m = msgs[i]
        if m.get("role") == "tool":
            c = str(m.get("content") or "")
            if len(c) > 400:
                total -= len(c) - 400
                m["content"] = c[:300] + "\n…[已省略以节省上下文]"


# ---------------------------------------------------------------- 会话持久化

SESSION_FILE = os.path.join(AB_HOME, "last-session.json")


def save_session(history):
    try:
        ensure_home()
        _atomic_private_json(SESSION_FILE, {"saved": time.strftime("%Y-%m-%d %H:%M"),
                                            "history": history[-12:]})
    except OSError:
        pass


def load_session():
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("history") or []
    except Exception:
        return []


def bench(cfg):
    print(i18n.t("agent.bench_title"))
    t0 = time.perf_counter()
    linux_help("端口占用")
    cold = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    linux_help("磁盘满了")
    warm = (time.perf_counter() - t0) * 1000.0
    print(i18n.t("agent.bench_kb") % (cold, warm))
    t1 = _ttfb(cfg)
    t2 = _ttfb(cfg)
    if t1 and t2:
        print(i18n.t("agent.bench_ttfb") % (t1, t2))
        if t1 > t2:
            print(i18n.t("agent.bench_gain") % (t1 - t2))
    else:
        print(i18n.t("agent.bench_fail"))


def test_provider(cfg, name=None):
    """连通性测试：让模型回一个字。"""
    try:
        target = dict(cfg)
        if name:
            target["active"] = name
        content, _ = chat(target, [{"role": "user", "content": "请只回复两个字：正常"}],
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
                tl, bl = title.lower(), (title + "\n" + body).lower()
                sections.append({"file": fn, "title": title, "body": body,
                                 "title_l": tl, "body_l": bl})
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
        title = sec["title_l"]
        body = sec["body_l"]
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
    "echo", "lscpu", "lsblk", "lsmod", "lspci", "lsusb", "printenv",
    "journalctl", "dmesg", "man", "apropos", "top", "vmstat",
    "iostat", "sar", "netstat", "getenforce", "sestatus",
    # Windows 常见只读命令
    "ipconfig", "systeminfo", "tasklist", "whoami",
    "netstat", "where", "driverquery", "hostname",
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

READ_ONLY_SUBCOMMANDS = {
    "systemctl": {"status", "show", "cat", "is-active", "is-enabled", "is-failed",
                  "list-units", "list-unit-files", "list-dependencies", "get-default"},
    "sc": {"query", "queryex", "qc", "qdescription", "qfailure", "qtriggerinfo"},
}

MUTATING_FLAGS = {
    "journalctl": ("--rotate", "--sync", "--flush", "--relinquish-var",
                   "--smart-relinquish-var", "--vacuum-", "--setup-keys"),
    "dmesg": ("-c", "--read-clear", "-C", "--clear", "-D", "--console-off",
              "-E", "--console-on", "-n", "--console-level"),
    "date": ("-s", "--set", "-u", "--universal"),
}


def _simple_command_level(segment):
    """Conservatively classify one shell pipeline segment."""
    try:
        words = shlex.split(segment, posix=os.name != "nt")
    except ValueError:
        return "normal"
    if not words:
        return "safe"
    while words and ("=" in words[0] and not words[0].startswith(("=", "-"))):
        words.pop(0)
    while words and os.path.basename(words[0]).lower() in ("sudo", "command", "nohup"):
        words.pop(0)
    if not words:
        return "normal"
    if os.path.basename(words[0]) != words[0] or "/" in words[0] or "\\" in words[0]:
        return "normal"
    first = words[0].lower()
    args = [str(word).lower() for word in words[1:]]
    if first in ("sh", "bash", "zsh", "dash", "cmd", "powershell", "pwsh", "env"):
        return "normal"
    if first == "find" and any(arg == "-delete" or arg.startswith(("-exec", "-ok", "-fprint", "-fls")) for arg in args):
        return "normal"
    if first in MUTATING_FLAGS:
        for arg in words[1:]:
            value = str(arg)
            for flag in MUTATING_FLAGS[first]:
                if value == flag or (flag.endswith("-") and value.startswith(flag)) or value.startswith(flag + "="):
                    return "normal"
    if first == "ip":
        if not args:
            return "safe"
        family = args[0]
        return "safe" if family in ("addr", "address", "route", "link", "neigh", "neighbor") and \
            (len(args) == 1 or args[1] in ("show", "list", "get")) else "normal"
    if first in READ_ONLY_SUBCOMMANDS:
        return "safe" if args and args[0] in READ_ONLY_SUBCOMMANDS[first] else "normal"
    return "safe" if first in SAFE_FIRST else "normal"


def classify_cmd(cmd):
    c = cmd.strip()
    for pat in DANGER_RE:
        if re.search(pat, c, re.IGNORECASE):
            return "danger"
    if re.search(r"[;&|<>\r\n]|`|\$\(|\$\(\(|\$\{|\btee\b", c):
        return "normal"
    return _simple_command_level(c)


def _trusted_executable(name):
    """Resolve a bare allowlisted command from OS-owned directories only."""
    import shutil
    if not name or os.path.basename(name) != name or "/" in name or "\\" in name:
        return None
    if os.name == "nt":
        root = os.environ.get("SystemRoot", r"C:\Windows")
        search = [os.path.join(root, "System32"), root]
    else:
        search = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    path = shutil.which(name, path=os.pathsep.join(search))
    return os.path.realpath(path) if path else None


def safe_command_argv(cmd):
    if classify_cmd(cmd) != "safe":
        return None
    try:
        words = shlex.split(cmd, posix=os.name != "nt")
    except ValueError:
        return None
    if not words:
        return None
    executable = _trusted_executable(words[0])
    return [executable] + words[1:] if executable else None


def run_safe_cmd(cmd, timeout=60):
    import subprocess
    argv = safe_command_argv(cmd)
    if not argv:
        return "exit=126\n拒绝执行无法从可信系统目录解析的只读命令。"
    timeout = min(max(int(timeout or 60), 5), 300)
    try:
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
        output = ((result.stdout or "") + (("\n[stderr] " + result.stderr) if result.stderr.strip() else "")).strip()
        return "exit=%d\n%s" % (result.returncode, output[:8000] or "（无输出）")
    except subprocess.TimeoutExpired:
        return "exit=124\n（只读命令超时 %ss，已终止）" % timeout
    except OSError as error:
        return "exit=126\n启动只读命令失败：%s" % error


def run_cmd(cmd, timeout=60):
    import subprocess   # 惰性导入：保持启动极速
    timeout = min(max(int(timeout or 60), 5), 300)
    shell = ["cmd", "/c", cmd] if os.name == "nt" else ["/bin/sh", "-c", cmd]
    out_file = tempfile.TemporaryFile(mode="w+b")
    err_file = tempfile.TemporaryFile(mode="w+b")
    try:
        kwargs = {"stdout": out_file, "stderr": err_file}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(shell, **kwargs)
        try:
            process.wait(timeout=timeout)
            code = process.returncode
        except subprocess.TimeoutExpired:
            code = 124
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=2)
                except Exception:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
            process.wait()
        def read_bounded(stream):
            stream.flush()
            size = stream.tell()
            stream.seek(0)
            if size <= 8000:
                return stream.read().decode("utf-8", "replace")
            first = stream.read(4000).decode("utf-8", "replace")
            stream.seek(max(0, size - 4000))
            last = stream.read(4000).decode("utf-8", "replace")
            return first + "\n…（输出过长，已截断中间部分）…\n" + last
        stdout = read_bounded(out_file)
        stderr = read_bounded(err_file)
        out = (stdout + (("\n[stderr] " + stderr) if stderr.strip() else "")).strip()
        if code == 124:
            out = "（命令超时 %ss，已终止整个进程树）\n%s" % (timeout, out)
    except subprocess.TimeoutExpired:
        out, code = "（命令超时 %ss，已终止）" % timeout, 124
    except FileNotFoundError as e:
        out, code = "启动 shell 失败：%s" % e, 127
    finally:
        out_file.close()
        err_file.close()
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


def search_files(pattern, path=".", regex=False, max_results=40):
    """跨平台文件内容/文件名搜索（Windows 上没有 grep 时的替代品）。"""
    root = os.path.expanduser(path or ".")
    if not os.path.isdir(root):
        return "错误：目录不存在：%s" % root
    try:
        rx = re.compile(pattern) if regex else None
    except re.error as e:
        return "正则错误：%s" % e
    low = pattern.lower()
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".agentboot"}
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        if len(out) >= max_results:
            break
        for fn in files:
            if len(out) >= max_results:
                break
            fp = os.path.join(base, fn)
            if rx and rx.search(fn):
                out.append("[文件名] " + fp)
                continue
            try:
                if os.path.getsize(fp) > 2 * 1024 * 1024:
                    continue
                with open(fp, "rb") as f:
                    if b"\0" in f.read(1024):
                        continue
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    for ln, line in enumerate(f, 1):
                        hit = rx.search(line) if rx else low in line.lower()
                        if hit:
                            out.append("%s:%d: %s" % (fp, ln, line.strip()[:160]))
                            if len(out) >= max_results:
                                break
            except OSError:
                continue
    return "\n".join(out) if out else "（无匹配）"


def _validate_public_http_url(url):
    from urllib.parse import urlsplit
    parsed = urlsplit(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("仅支持不含凭据的 http/https 公网地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                       type=socket.SOCK_STREAM)
    except OSError as error:
        raise ValueError("域名解析失败：%s" % error)
    if not addresses:
        raise ValueError("域名没有可用地址")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError("拒绝访问非公网地址：%s" % address)
    return parsed


def http_get(url):
    try:
        from urllib.request import Request, build_opener, HTTPRedirectHandler
        _validate_public_http_url(url)

        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                _validate_public_http_url(newurl)
                return HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)

        req = Request(url, headers={"User-Agent": "AgentBoot/1.0"})
        with build_opener(SafeRedirect()).open(req, timeout=15) as r:
            data = r.read(300000)
        text = data.decode("utf-8", "replace")
        if len(data) >= 299000:
            text += "\n…（已截断）"
        return text if text.strip() else "（空响应）"
    except Exception as e:
        return "抓取失败或已拒绝：%s" % e


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
    {"type": "function", "function": {"name": "search_files", "description": "在目录中搜索文件名或文件内容（跨平台，Windows 上替代 grep）。支持正则。",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "搜索关键词或正则"}, "path": {"type": "string", "description": "起始目录，默认当前目录"}, "regex": {"type": "boolean", "description": "是否按正则匹配，默认false"}}, "required": ["pattern"]}}},
]


def execute_tool(cfg, name, args, session_allow):
    """执行工具，返回 (结果文本, 是否危险命令)。"""
    if name == "run_cmd":
        cmd = args.get("command", "")
        level = classify_cmd(cmd)
        policy = str(cfg.get("confirm", "smart")).strip().lower()
        if policy not in ("safe", "smart", "always"):
            policy = "smart"
        if policy == "safe" and level != "safe":
            return "safe 模式只允许只读命令，已拒绝：%s" % cmd, level == "danger"
        if level == "danger" and policy != "always" and cmd not in session_allow:
            return "已拦截高危命令（如需放行请在交互模式下确认，或修改配置 confirm=always）：%s" % cmd, True
        if level != "safe" and policy == "smart" and cmd not in session_allow:
            if _is_interactive():
                print("\n  ⚠ 将执行命令：\n    %s" % cmd)
                ans = input("  允许执行? [y=允许 / n=拒绝 / a=本会话总是允许] ").strip().lower()
                if ans == "a":
                    session_allow.add(cmd)
                elif ans != "y":
                    return "用户拒绝了该命令。", False
            else:
                return "非交互模式无法确认写操作，已拒绝；如需自动执行请设置 confirm=always。", False
        if level == "safe":
            return run_safe_cmd(cmd, args.get("timeout")), False
        return run_cmd(cmd, args.get("timeout")), level == "danger"
    if name == "read_file":
        return read_file(args.get("path", "")), False
    if name == "write_file":
        policy = str(cfg.get("confirm", "smart")).strip().lower()
        if policy not in ("safe", "smart", "always"):
            policy = "smart"
        key = "write_file:%s" % args.get("path", "")
        if policy == "safe":
            return "safe 模式只允许只读工具，已拒绝写入文件。", False
        if policy == "smart" and key not in session_allow:
            if not _is_interactive():
                return "非交互模式无法确认写文件，已拒绝；如需自动执行请设置 confirm=always。", False
            print("\n  ✎ 将写入文件：%s" % args.get("path", ""))
            ans = input("  允许写入? [y=允许 / n=拒绝 / a=本会话允许此路径] ").strip().lower()
            if ans == "a":
                session_allow.add(key)
            elif ans != "y":
                return "用户拒绝了文件写入。", False
        return write_file(args.get("path", ""), args.get("content", "")), False
    if name == "edit_file":
        policy = str(cfg.get("confirm", "smart")).strip().lower()
        if policy not in ("safe", "smart", "always"):
            policy = "smart"
        key = "edit_file:%s" % args.get("path", "")
        if policy == "safe":
            return "safe 模式只允许只读工具，已拒绝修改文件。", False
        if policy == "smart" and key not in session_allow:
            if not _is_interactive():
                return "非交互模式无法确认修改文件，已拒绝；如需自动执行请设置 confirm=always。", False
            print("\n  ✎ 将修改文件：%s" % args.get("path", ""))
            ans = input("  允许修改? [y=允许 / n=拒绝 / a=本会话允许此路径] ").strip().lower()
            if ans == "a":
                session_allow.add(key)
            elif ans != "y":
                return "用户拒绝了文件修改。", False
        return edit_file(args.get("path", ""), args.get("old", ""), args.get("new", "")), False
    if name == "list_dir":
        return list_dir(args.get("path", ".")), False
    if name == "linux_help":
        return linux_help(args.get("query", "")), False
    if name == "search_files":
        return search_files(args.get("pattern", ""), args.get("path", "."),
                            bool(args.get("regex"))), False
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
    if i18n.get_lang() == "en":
        return (
            "You are AgentBoot's built-in terminal assistant running locally on %s.\n"
            "Use tools for commands, files, the offline Linux knowledge base, and public web pages.\n"
            "Rules: answer concisely in English; inspect with read-only tools before changing state; "
            "explain destructive consequences first; put commands in code blocks; summarize verified results." % plat
        )
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
        _shrink(msgs)   # 上下文预算控制：清理过老的大段工具输出
        cb = (lambda piece: (sys.stdout.write(piece), sys.stdout.flush())) if (stream and _is_interactive()) else None
        if cb:
            sys.stdout.write("\n")
            sys.stdout.flush()
        content, tool_calls = chat_auto(cfg, msgs, stream_cb=cb, tools=TOOLS)
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
  /模型 /model       模型提供商管理器（添加/切换/删除/故障切换）
  /linux <关键词>    直接查离线 Linux 知识库
  /继续              恢复上次会话的对话记忆
  /bench             性能基准（知识库/首字延迟/连接复用）
  /清空 /clear       清空本轮对话历史
  /状态 /status      显示当前模型与配置
  /退出 /exit        退出
直接输入问题或任务即可，例如：
  查一下这台机器磁盘占用情况，若有异常给出清理建议
  nginx 起不来怎么排查？
"""

HELP_EN = """Commands:
  /help              Show this help
  /model             Model provider manager (add / switch / remove / failover)
  /linux <keywords>  Query offline Linux knowledge base
  /resume            Restore last session memory
  /bench             Performance benchmark (KB / TTFB / connection reuse)
  /clear             Clear conversation history
  /status            Show current model & config
  /exit              Exit
Type a question or task directly, e.g.:
  check disk usage and suggest cleanup
  why won't nginx start?
"""


def help_text():
    return HELP_EN if i18n.get_lang() == "en" else HELP_TEXT


def choose_model(cfg):
    """模型提供商管理器：列出/切换/添加/删除/故障切换/测速（ab 与菜单共用）。"""
    while True:
        names = list(PRESETS.keys()) + [n for n in (cfg.get("providers") or {}) if n not in PRESETS]
        print("\n" + i18n.t("agent.mm_title"))
        for i, n in enumerate(names, 1):
            p = get_provider(cfg, n)
            mark = i18n.t("agent.mm_current") if n == cfg.get("active") else ""
            fb = i18n.t("agent.mm_fallback") if n in (cfg.get("fallback") or []) else ""
            print("  [%d] %-12s %-30s (%s)%s%s" % (i, n, p.get("model", ""), p.get("base_url", ""), mark, fb))
        print(i18n.t("agent.mm_menu"))
        print(i18n.t("agent.mm_menu2"))
        c = input(i18n.t("agent.mm_pick")).strip().lower()
        if c in (i18n.t("agent.mm_done"), ""):
            return
        if c == "s":
            k = input(i18n.t("agent.mm_switch_to")).strip()
            if k.isdigit() and 1 <= int(k) <= len(names):
                cfg["active"] = names[int(k) - 1]
                save_config(cfg)
                p = get_provider(cfg)
                print(i18n.t("agent.mm_switched") % (p["name"], p.get("model"), p.get("base_url")))
        elif c == "a":
            print(i18n.t("agent.mm_add_hint"))
            base = input(i18n.t("agent.mm_base")).strip()
            key = input(i18n.t("agent.mm_key")).strip()
            model = input(i18n.t("agent.mm_model")).strip()
            if not base or not model:
                print(i18n.t("agent.mm_need_base_model"))
                continue
            pid = input(i18n.t("agent.mm_pid")).strip() or "custom"
            pid = re.sub(r"[^a-z0-9_-]+", "-", pid.lower()).strip("-") or "custom"
            set_provider(cfg, pid, base, key, model)
            print(i18n.t("agent.mm_added") % (pid, model, base))
        elif c == "d":
            customs = [n for n in (cfg.get("providers") or {}) if n not in PRESETS]
            if not customs:
                print(i18n.t("agent.mm_no_custom"))
                continue
            k = input(i18n.t("agent.mm_del_which") % customs).strip()
            if k in customs:
                (cfg.get("providers") or {}).pop(k)
                if cfg.get("fallback") and k in cfg["fallback"]:
                    cfg["fallback"] = [n for n in cfg["fallback"] if n != k]
                if cfg.get("active") == k:
                    cfg["active"] = DEFAULT_ACTIVE
                save_config(cfg)
                print(i18n.t("agent.mm_deleted") % k)
            else:
                print(i18n.t("agent.mm_del_invalid"))
        elif c == "f":
            print(i18n.t("agent.mm_fb_hint") % ", ".join(names))
            raw = input(i18n.t("agent.mm_fb_prompt")).strip()
            fb = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip() in names]
            cfg["fallback"] = fb
            save_config(cfg)
            print(i18n.t("agent.mm_fb_set") % (fb or i18n.t("agent.mm_fb_none")))
        elif c == "t":
            print(i18n.t("agent.mm_testing"))
            ok, msg = test_provider(cfg)
            print((i18n.t("agent.mm_test_ok") % msg) if ok else (i18n.t("agent.mm_test_fail") % msg))


def show_status(cfg):
    p = get_provider(cfg)
    print("当前模型源: %s\n接口: %s\n模型: %s\n确认策略: %s\n配置文件: %s" % (
        p["name"], p.get("base_url"), p.get("model"), cfg.get("confirm"), CONFIG_PATH))


def repl(cfg, resume=False):
    print(BANNER)
    p = get_provider(cfg)
    print(i18n.t("agent.banner_model") % (p.get("model"), p.get("base_url")))
    print(help_text())
    history = []
    if resume:
        loaded = load_session()
        if loaded:
            history = loaded
            print(i18n.t("agent.banner_resume") % len(history))
    while True:
        try:
            text = input(i18n.t("agent.prompt")).strip()
        except (EOFError, KeyboardInterrupt):
            print(i18n.t("agent.bye"))
            return
        if not text:
            continue
        low = text.lower()
        if low in ("/exit", "/quit", "/退出", "/q"):
            save_session(history)
            print(i18n.t("agent.bye_saved"))
            return
        if low in ("/help", "/帮助", "?"):
            print(help_text())
            continue
        if low in ("/model", "/模型"):
            choose_model(cfg)
            p = get_provider(cfg)
            print("model: %s @ %s" % (p.get("model"), p.get("base_url")))
            continue
        if low.startswith("/linux"):
            q = text[6:].strip()
            print(linux_help(q) if q else "usage: /linux <keywords>")
            continue
        if low in ("/继续", "/resume"):
            loaded = load_session()
            if loaded:
                history = loaded
                print(i18n.t("agent.resumed") % len(history))
            else:
                print(i18n.t("agent.no_session"))
            continue
        if low in ("/bench", "/性能"):
            bench(cfg)
            continue
        if low in ("/clear", "/清空"):
            history = []
            print(i18n.t("agent.cleared"))
            continue
        if low in ("/status", "/状态"):
            show_status(cfg)
            continue
        try:
            _final, history = agent_loop(cfg, text, history)
            save_session(history)
        except KeyboardInterrupt:
            print(i18n.t("agent.interrupted"))
        except ApiError as e:
            print("✗ %s" % e)
        except Exception as e:
            print("✗ %s" % e)


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
    i18n.set_lang(os.environ.get("AGENTBOOT_LANG") or cfg.get("lang") or "zh")
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "chat"
    args = argv[1:]
    if cmd == "lang":
        want = args[0] if args else "zh"
        cfg["lang"] = "en" if want.lower().startswith("en") else "zh"
        save_config(cfg)
        i18n.set_lang(cfg["lang"])
        print("Language: %s" % ("English" if cfg["lang"] == "en" else "中文（默认）"))
        return
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
        final, _ = agent_loop(cfg, " ".join(args), stream=False)
        if final:
            print(final)
        return
    if cmd == "bench":
        bench(cfg)
        return
    if cmd == "chat":
        resume = "-c" in args or "--continue" in args
        if _is_interactive():
            repl(cfg, resume=resume)
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
