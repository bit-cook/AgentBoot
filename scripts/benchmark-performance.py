#!/usr/bin/env python3
"""Deterministic AgentBoot performance benchmark (stdlib only).

This benchmark intentionally excludes public-network latency. It measures the
fixed cost AgentBoot controls: process startup, menu readiness, local model
request handling, install orchestration, and critical-page transfer size.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


class ModelHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = json.dumps({
            "choices": [{"message": {"content": "ok", "tool_calls": []}}]
        }, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


@contextmanager
def model_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def write_config(home: Path, port: int | None = None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    config = {
        "active": "bench" if port else "agnes",
        "providers": ({
            "bench": {
                "base_url": "http://127.0.0.1:%d/v1" % port,
                "api_key": "",
                "model": "bench",
            }
        } if port else {}),
        "confirm": "safe",
        "max_steps": 1,
        "lang": "zh",
    }
    (home / "config.json").write_text(json.dumps(config), encoding="utf-8")


def elapsed_ms(command: list[str], env: dict[str, str], stdin: bytes | None = None) -> float:
    start = time.perf_counter()
    subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=stdin,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=15,
    )
    return (time.perf_counter() - start) * 1000.0


def median_command(command, env, runs, stdin=None) -> float:
    elapsed_ms(command, env, stdin)
    values = [elapsed_ms(command, env, stdin) for _ in range(runs)]
    return statistics.median(values)


def fake_toolchain(root: Path) -> Path:
    binary = root / "fake-bin"
    binary.mkdir()
    node = binary / "node"
    npm = binary / "npm"
    node.write_text("#!/bin/sh\nprintf 'v22.23.2\\n'\n", encoding="utf-8")
    npm.write_text(
        "#!/bin/sh\n"
        "prefix=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = --prefix ]; then shift; prefix=$1; fi\n"
        "  shift\n"
        "done\n"
        "[ -n \"$prefix\" ] || exit 2\n"
        "mkdir -p \"$prefix/bin\"\n"
        "printf '#!/bin/sh\\nexit 0\\n' > \"$prefix/bin/codex\"\n"
        "chmod +x \"$prefix/bin/codex\"\n",
        encoding="utf-8",
    )
    node.chmod(0o755)
    npm.chmod(0o755)
    return binary


def clean_install_home(root: Path) -> None:
    for name in ("agentboot-home", "home"):
        shutil.rmtree(root / name, ignore_errors=True)
        (root / name).mkdir()
    write_config(root / "agentboot-home")


def install_metric(root: Path, runs: int) -> float:
    binary = fake_toolchain(root)
    env = dict(os.environ)
    env.update({
        "AGENTBOOT_HOME": str(root / "agentboot-home"),
        "AGENTBOOT_MIRROR": "off",
        "HOME": str(root / "home"),
        "PATH": str(binary) + os.pathsep + env.get("PATH", ""),
    })
    command = [PYTHON, "core/menu.py", "install", "codex"]
    values = []
    for index in range(runs + 1):
        clean_install_home(root)
        value = elapsed_ms(command, env)
        if index:
            values.append(value)
    return statistics.median(values)


def homepage_bytes() -> int:
    paths = (
        ROOT / "pages" / "index.html",
        ROOT / "pages" / "assets" / "site.css",
        ROOT / "pages" / "assets" / "site.js",
    )
    return sum(len(gzip.compress(path.read_bytes(), compresslevel=9)) for path in paths)


def measure(runs: int) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="agentboot-perf-") as tmp:
        root = Path(tmp)
        home = root / "agentboot-home"
        write_config(home)
        env = dict(os.environ)
        env.update({"AGENTBOOT_HOME": str(home), "AGENTBOOT_MIRROR": "off"})

        ab_version = median_command([PYTHON, "core/agent.py", "version"], env, runs)
        menu_version = median_command([PYTHON, "core/menu.py", "version"], env, runs)
        menu_ready = median_command([PYTHON, "core/menu.py"], env, runs, b"0\n")

        with model_server() as port:
            write_config(home, port)
            agent_run = median_command(
                [PYTHON, "core/agent.py", "run", "ping"], env, runs)

        install = install_metric(root, max(3, runs // 2))

    return {
        "startup_ms": round(statistics.fmean((ab_version, menu_version, menu_ready)), 3),
        "ab_version_ms": round(ab_version, 3),
        "menu_version_ms": round(menu_version, 3),
        "menu_ready_ms": round(menu_ready, 3),
        "agent_run_ms": round(agent_run, 3),
        "install_ms": round(install, 3),
        "homepage_gzip_bytes": float(homepage_bytes()),
    }


def score(metrics: dict[str, float], baseline: dict[str, float]) -> float:
    keys = ("startup_ms", "agent_run_ms", "install_ms", "homepage_gzip_bytes")
    return round(100.0 * statistics.fmean(metrics[key] / baseline[key] for key in keys), 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=9)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs must be at least 3")

    metrics = measure(args.runs)
    output = {"metrics": metrics}
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))["metrics"]
        output["score"] = score(metrics, baseline)
    else:
        output["score"] = 100.0
    if args.write_baseline:
        args.write_baseline.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
