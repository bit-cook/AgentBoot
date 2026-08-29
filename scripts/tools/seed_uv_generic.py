#!/usr/bin/env python3
"""为 hermes-agent 包预置 uv（通用版）：从包内 uv-installer.js 解析版本/校验，
从镜像下载 uv，写入 .uv_bin + marker，使 postinstall 跳过 GitHub 直连下载。
用法：python seed_uv_generic.py <hermes-agent 包根目录>
"""
import json
import os
import re
import sys
import tarfile
import urllib.request
import zipfile

MIRRORS = ["", "https://gh-proxy.com/", "https://ghfast.top/"]


def main():
    pkg = sys.argv[1]
    text = open(os.path.join(pkg, "lib", "uv-installer.js"), encoding="utf-8").read()
    version = re.search(r'UV_VERSION\s*=\s*"([^"]+)"', text).group(1)
    if sys.platform == "win32":
        target = "aarch64-pc-windows-msvc" if "arm" in os.environ.get("PROCESSOR_ARCHITECTURE", "X86").lower() else "x86_64-pc-windows-msvc"
        asset = "uv-%s.zip" % target
        member = "uv.exe"
    elif sys.platform == "darwin":
        arch = "aarch64-apple-darwin" if os.uname().machine == "arm64" else "x86_64-apple-darwin"
        asset = "uv-%s.tar.gz" % arch
        member = asset.replace(".tar.gz", "") + "/uv"
    else:
        arch = "aarch64-unknown-linux-gnu" if os.uname().machine == "aarch64" else "x86_64-unknown-linux-gnu"
        asset = "uv-%s.tar.gz" % arch
        member = asset.replace(".tar.gz", "") + "/uv"
    sha = re.search(r'"%s":\s*"([0-9a-f]{64})"' % re.escape(asset), text).group(1)

    uv_dir = os.path.join(pkg, ".uv_bin")
    exe = os.path.join(uv_dir, "uv.exe" if sys.platform == "win32" else "uv")
    marker = os.path.join(uv_dir, "install.json")
    if os.path.exists(marker) and os.path.exists(exe):
        try:
            m = json.load(open(marker, encoding="utf-8"))
            if m.get("version") == version and m.get("sha256") == sha:
                print("uv already seeded")
                return
        except Exception:
            pass

    base = "https://github.com/astral-sh/uv/releases/download/%s/%s" % (version, asset)
    archive = os.path.join(uv_dir, asset)
    os.makedirs(uv_dir, exist_ok=True)
    for p in MIRRORS:
        url = p + base
        try:
            print("downloading", url)
            req = urllib.request.Request(url, headers={"User-Agent": "AgentBoot/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(archive, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            break
        except Exception as e:
            print("  failed:", e)
    else:
        raise SystemExit("uv download failed from all sources")

    if asset.endswith(".zip"):
        data = zipfile.ZipFile(archive).read(member)
    else:
        data = tarfile.open(archive, "r:gz").extractfile(member).read()
    with open(exe, "wb") as f:
        f.write(data)
    if sys.platform != "win32":
        os.chmod(exe, 0o755)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"version": version, "asset": asset, "sha256": sha}, f, indent=2)
    os.remove(archive)
    print("uv seeded: %d bytes" % len(data))


if __name__ == "__main__":
    main()
