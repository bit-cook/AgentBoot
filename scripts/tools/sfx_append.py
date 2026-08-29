#!/usr/bin/env python3
"""把 gzip 包以 base64 形式追加到自解压 sh 脚本末尾（build-offline 用）"""
import base64
import sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "ab") as f:
        f.write(base64.b64encode(data))
        f.write(b"\n")
    print("sfx payload appended: %d -> %d bytes" % (len(data), len(data) * 4 // 3 + 4))


if __name__ == "__main__":
    main()
