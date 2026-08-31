#!/usr/bin/env python3
"""Fail a build unless every requested Agent/platform payload is complete."""

import json
from pathlib import Path
import sys


def npm_name(spec):
    if spec.startswith("@"):
        slash = spec.find("/")
        version = spec.find("@", slash + 1)
        return spec[:version] if version >= 0 else spec
    return spec.split("@", 1)[0]


def check_npm(stage, agent, platform_id):
    root = stage / "payloads" / "agents" / agent["id"] / platform_id
    package = root / "node_modules" / Path(*npm_name(agent["npm"]).split("/"))
    metadata_path = package / "package.json"
    if not metadata_path.is_file():
        return "missing package.json: %s" % metadata_path
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        bins = metadata.get("bin")
        if isinstance(bins, str):
            entry = bins
        elif isinstance(bins, dict):
            entry = bins.get(agent.get("bin")) or (next(iter(bins.values())) if len(bins) == 1 else None)
        else:
            entry = None
    except (OSError, ValueError, TypeError) as error:
        return "invalid package metadata %s: %s" % (metadata_path, error)
    if not entry or not (package / entry).is_file():
        return "missing npm bin entry for %s on %s" % (agent["id"], platform_id)
    if agent["id"] == "hermes" and not (root / "PACK_ROOT.txt").is_file():
        return "Hermes runtime was not completed on %s" % platform_id
    if agent["id"] == "opencode":
        binary = "opencode.exe" if platform_id.startswith("win-") else "opencode"
        for package_name in (agent.get("offline_binary_packages") or {}).get(platform_id, []):
            candidates = (
                root / "node_modules" / "opencode-ai" / "node_modules" / package_name / "bin" / binary,
                root / "node_modules" / package_name / "bin" / binary,
            )
            if not any(path.is_file() and path.stat().st_size > 10 * 1024 * 1024 for path in candidates):
                return "missing OpenCode native package %s on %s" % (package_name, platform_id)
    return None


def main():
    stage = Path(sys.argv[1]).resolve()
    platforms = [item for item in sys.argv[2].split(",") if item]
    requested = [item for item in sys.argv[3].split(",") if item]
    registry = json.loads((stage / "agents" / "registry.json").read_text(encoding="utf-8"))
    agents = {agent["id"]: agent for agent in registry["agents"]}
    errors = []
    platform_os = {"win-x64": "windows", "linux-x64": "linux", "linux-arm64": "linux",
                   "darwin-x64": "darwin", "darwin-arm64": "darwin"}
    for platform_id in platforms:
        node_dir = stage / "payloads" / "node" / platform_id
        if any(agents.get(aid, {}).get("method") == "npm" and aid != "opencode" for aid in requested) and not node_dir.is_dir():
            errors.append("missing Node runtime: %s" % platform_id)
        for aid in requested:
            agent = agents.get(aid)
            if not agent:
                errors.append("unknown requested Agent: %s" % aid)
            elif not agent.get("offline"):
                errors.append("%s is not marked offline-capable" % aid)
            elif agent.get("os") and platform_os.get(platform_id) not in agent["os"]:
                errors.append("%s does not support %s" % (aid, platform_id))
            elif aid == "coco":
                root = stage / "payloads" / "agents" / aid / platform_id
                for name in ("coco-0.8.0.tgz", "coco-0.8.0.tgz.sha256", "agnes.key"):
                    if not (root / name).is_file():
                        errors.append("missing CoCo %s on %s" % (name, platform_id))
                if not any(root.glob("node-v22.23.2-*.tar.gz")):
                    errors.append("missing CoCo Node runtime on %s" % platform_id)
            elif agent.get("method") == "npm":
                error = check_npm(stage, agent, platform_id)
                if error:
                    errors.append(error)
            else:
                errors.append("%s is not offline-buildable" % aid)
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        raise SystemExit(1)
    print("offline payload closure verified: %d agents x %d platforms" %
          (len(requested), len(platforms)))


if __name__ == "__main__":
    main()
