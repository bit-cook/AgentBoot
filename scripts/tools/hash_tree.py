#!/usr/bin/env python3
"""Write deterministic SHA-256 entries for every file below a directory."""

import hashlib
from pathlib import Path
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    platform_id = sys.argv[3] if len(sys.argv) > 3 else None
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.resolve() != output:
            relative_payload = path.relative_to(root)
            if platform_id:
                parts = relative_payload.parts
                include = ((len(parts) >= 2 and parts[0] == "node" and parts[1] == platform_id) or
                           (len(parts) >= 3 and parts[0] == "agents" and parts[2] == platform_id) or
                           (parts and parts[0] == "python" and platform_id == "win-x64"))
                if not include:
                    continue
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            lines.append("%s  %s" % (digest, path.relative_to(root.parent).as_posix()))
    output.write_text("\n".join(lines) + "\n", encoding="ascii")
    if not lines:
        raise SystemExit("no payload files to hash")


if __name__ == "__main__":
    main()
