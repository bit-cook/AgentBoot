#!/usr/bin/env python3
"""Create one ZIP archive from a directory without reopening/truncating it."""

from pathlib import Path
import sys
import zipfile


def main():
    output = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    prefix = sys.argv[3] if len(sys.argv) > 3 else root.name
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(prefix) / path.relative_to(root)).as_posix())
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit("ZIP creation produced no output")


if __name__ == "__main__":
    main()
