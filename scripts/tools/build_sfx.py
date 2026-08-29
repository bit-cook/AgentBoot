#!/usr/bin/env python3
"""生成 POSIX 自解压安装器（sfx.sh）
用法：python build_sfx.py <offline.tar.gz> <输出.sh>
"""
import base64
import sys

HEADER = """#!/bin/sh
# AgentBoot 离线自解压安装器：目标机器无需任何解压软件，直接运行
#   sh __SFXNAME__
set -eu
SKIP=$(awk '/^__AGENTBOOT_PAYLOAD_BELOW__$/{print NR+1; exit}' "$0")
tmp="$(mktemp -d 2>/dev/null || echo /tmp/agentboot-sfx-$$)"
mkdir -p "$tmp"
echo "==> AgentBoot 离线自解压安装：解压中，请稍候 …"
tail -n +"$SKIP" "$0" | {{ base64 -d 2>/dev/null || base64 -D 2>/dev/null || openssl base64 -d -A; }} | tar -xzf - -C "$tmp"
exec sh "$tmp/AgentBoot/install-offline.sh" "$@"
__AGENTBOOT_PAYLOAD_BELOW__
"""


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        payload = base64.b64encode(f.read())
    with open(dst, "wb") as f:
        f.write(HEADER.replace("__SFXNAME__", dst.replace("\\", "/").split("/")[-1]).encode("utf-8"))
        f.write(payload)
        f.write(b"\n")
    print("sfx: %s (%.0f MB)" % (dst, len(payload) / 1048576.0))


if __name__ == "__main__":
    main()
