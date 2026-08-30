#!/usr/bin/env python3
"""Build reproducible AgentBoot online tar/zip packages for GitHub Pages."""

import gzip
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TAG = "v1.0.0"
OUTPUTS = {
    "tar": ROOT / "pages" / ("agentboot-online-%s.tar.gz" % TAG),
    "zip": ROOT / "pages" / ("agentboot-online-%s.zip" % TAG),
}
TOP_LEVEL = (
    ".gitattributes", ".gitignore", "CHANGELOG.md", "LICENSE", "README.md",
    "README.en.md", "install.bat", "install.sh", "安装指南.md",
)
DIRECTORIES = ("agents", "cloudflare", "core", "docs", "scripts", "tools")
SKIP_PARTS = {"__pycache__", "node_modules", "payloads", "dist"}


def package_files():
    files = []
    for name in TOP_LEVEL:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for dirname in DIRECTORIES:
        for path in (ROOT / dirname).rglob("*"):
            rel = path.relative_to(ROOT)
            if path.is_file() and not (set(rel.parts) & SKIP_PARTS) and path.suffix != ".pyc":
                files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def build_tar(files, output):
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as raw:
        raw_path = Path(raw.name)
    try:
        with tarfile.open(raw_path, "w", format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                arcname = Path("AgentBoot") / path.relative_to(ROOT)
                info = archive.gettarinfo(str(path), arcname.as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
        with raw_path.open("rb") as source, output.open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
    finally:
        raw_path.unlink(missing_ok=True)


def build_zip(files, output):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            arcname = (Path("AgentBoot") / path.relative_to(ROOT)).as_posix()
            info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
            mode = path.stat().st_mode & 0o777
            info.external_attr = (mode or 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)


def main():
    files = package_files()
    if not files:
        raise SystemExit("no package files found")
    OUTPUTS["tar"].parent.mkdir(parents=True, exist_ok=True)
    build_tar(files, OUTPUTS["tar"])
    build_zip(files, OUTPUTS["zip"])
    for output in OUTPUTS.values():
        print("built %s (%d bytes, %d files)" % (output.relative_to(ROOT), output.stat().st_size, len(files)))


if __name__ == "__main__":
    main()
