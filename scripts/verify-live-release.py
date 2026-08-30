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


def fetch(url, headers=None, expected_status=200):
    request_headers = {"User-Agent": "AgentBoot-release-check/1.1"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != expected_status:
            raise RuntimeError("%s returned HTTP %s" % (url, response.status))
        return response.read(), response.headers


def verify_origin(origin):
    shell = fetch(origin + "/install.sh")[0].decode("utf-8")
    ps1 = fetch(origin + "/install.ps1")[0].decode("utf-8-sig")
    if 'TAG="%s"' % TAG not in shell or "$Tag       = '%s'" % TAG not in ps1:
        raise RuntimeError("%s installers are not %s" % (origin, TAG))
    for filename in ("agentboot-online-%s.tar.gz" % TAG, "agentboot-online-%s.zip" % TAG):
        asset = (fetch(origin + "/rel/" + filename)[0] if "boot.ide.pub" in origin
                 else fetch(origin + "/" + filename)[0])
        sidecar = (fetch(origin + "/rel/" + filename + ".sha256")[0] if "boot.ide.pub" in origin
                   else fetch(origin + "/" + filename + ".sha256")[0])
        expected = sidecar.decode("ascii").split()[0]
        actual = hashlib.sha256(asset).hexdigest()
        if actual != expected:
            raise RuntimeError("%s checksum mismatch via %s" % (filename, origin))
    if "boot.ide.pub" in origin:
        range_body, range_headers = fetch(
            origin + "/rel/agentboot-online-%s.tar.gz" % TAG,
            headers={"Range": "bytes=0-99"}, expected_status=206)
        if len(range_body) != 100 or not range_headers.get("Content-Range", "").startswith("bytes 0-99/"):
            raise RuntimeError("Worker Range forwarding is not ready")


def main():
    health = json.loads(fetch("https://boot.ide.pub/health")[0])
    if health.get("tag") != TAG or not health.get("ok"):
        raise RuntimeError("Worker health is not ready for %r: %r" % (TAG, health))
    verify_origin("https://boot.ide.pub")
    verify_origin("https://bit-cook.github.io/AgentBoot")
    print("live release verified:", TAG)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("live release verification failed:", error, file=sys.stderr)
        raise SystemExit(1)
