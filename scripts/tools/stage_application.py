#!/usr/bin/env python3
"""Copy the explicit AgentBoot application allowlist into a staging directory."""

from pathlib import Path
import shutil
import sys


FILES = (
    "VERSION", "LICENSE", "CHANGELOG.md", "README.md", "README.en.md", "install.sh", "install.bat", "安装指南.md",
    "agents/registry.json", "core/agent.py", "core/i18n.py", "core/menu.py",
    "docs/en/install-guide.md", "docs/zh/安装指南.md",
    "scripts/build-offline.ps1", "scripts/build-offline.sh", "scripts/build-online.py",
    "scripts/install-offline.ps1", "scripts/install-offline.sh", "scripts/install.ps1", "scripts/verify-live-release.py",
    "scripts/tools/build_sfx.py", "scripts/tools/hash_tree.py", "scripts/tools/seed_uv_generic.py",
    "scripts/tools/sfx_append.py", "scripts/tools/stage_application.py",
    "scripts/tools/validate_offline_payload.py", "scripts/tools/zip_tree.py",
    "tools/linux-kb/基础命令.md", "tools/linux-kb/故障排查.md", "tools/linux-kb/服务管理.md",
    "tools/linux-kb/用户与权限.md", "tools/linux-kb/磁盘存储.md", "tools/linux-kb/系统信息.md",
    "tools/linux-kb/终端技巧.md", "tools/linux-kb/网络配置.md", "tools/linux-kb/软件包管理.md",
)


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
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    print("staged explicit application allowlist:", destination)


if __name__ == "__main__":
    main()
