#!/usr/bin/env python3
"""Copy the explicit AgentBoot application allowlist into a staging directory."""

from pathlib import Path
import shutil
import sys


FILES = ("VERSION", "LICENSE", "CHANGELOG.md", "README.md", "README.en.md",
         "install.sh", "install.bat", "安装指南.md")
DIRECTORIES = ("agents", "core", "docs", "scripts", "tools")


def reject_symlinks(path):
    if path.is_symlink():
        raise SystemExit("release source contains symlink: %s" % path)
    if path.is_dir():
        for child in path.iterdir():
            reject_symlinks(child)


def main():
    source = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise SystemExit("missing or unsafe release file: %s" % path)
        shutil.copy2(path, destination / name)
    for name in DIRECTORIES:
        path = source / name
        if not path.is_dir():
            raise SystemExit("missing release directory: %s" % path)
        reject_symlinks(path)
        shutil.copytree(path, destination / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules", "dist", "payloads"))
    print("staged explicit application allowlist:", destination)


if __name__ == "__main__":
    main()
