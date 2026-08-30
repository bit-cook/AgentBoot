#!/usr/bin/env python3
"""Verify published Pages and Worker surfaces agree with VERSION and checksums."""

import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
TAG = "v" + VERSION


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "AgentBoot-release-check/1.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError("%s returned HTTP %s" % (url, response.status))
        return response.read()


def verify_origin(origin):
    shell = fetch(origin + "/install.sh").decode("utf-8")
    ps1 = fetch(origin + "/install.ps1").decode("utf-8-sig")
    if 'TAG="%s"' % TAG not in shell or "$Tag       = '%s'" % TAG not in ps1:
        raise RuntimeError("%s installers are not %s" % (origin, TAG))
    for filename in ("agentboot-online-%s.tar.gz" % TAG, "agentboot-online-%s.zip" % TAG):
        asset = fetch(origin + "/rel/" + filename) if "boot.ide.pub" in origin else fetch(origin + "/" + filename)
        sidecar = (fetch(origin + "/rel/" + filename + ".sha256") if "boot.ide.pub" in origin
                   else fetch(origin + "/" + filename + ".sha256"))
        expected = sidecar.decode("ascii").split()[0]
        actual = hashlib.sha256(asset).hexdigest()
        if actual != expected:
            raise RuntimeError("%s checksum mismatch via %s" % (filename, origin))


def main():
    health = json.loads(fetch("https://boot.ide.pub/health"))
    if health.get("tag") != TAG:
        raise RuntimeError("Worker health tag is %r, expected %r" % (health.get("tag"), TAG))
    verify_origin("https://boot.ide.pub")
    verify_origin("https://bit-cook.github.io/AgentBoot")
    print("live release verified:", TAG)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("live release verification failed:", error, file=sys.stderr)
        raise SystemExit(1)
