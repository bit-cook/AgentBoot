"""hermes uv 预置：包内布局无关提取的回归测试。

背景（v1.8.1 InstaBox 实测）：uv 0.12.13 的发行包把包内目录从旧布局
`<target>/uv` 改成了 `uv-<target>/uv`，AgentBoot 的 _hermes_uv_meta 却把
完整成员名硬编码成 `x86_64-unknown-linux-gnu/uv`，下载和 SHA 校验都过了之后
在 tarfile.extractfile 上 KeyError 崩栈，装机必败。修复：只要 basename，
按 basename 在包里找，新旧布局/根级平铺/zip 全兼容；找不到时干净报错回退
官方 postinstall（其 ensureUv 会自行下载）。
"""

import io
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import menu  # noqa: E402


def _make_tar_gz(path, entries):
    """entries: {成员名: 字节}；目录用 None 值表示。"""
    with tarfile.open(path, "w:gz") as t:
        for name, data in entries.items():
            if data is None:
                m = tarfile.TarInfo(name.rstrip("/") + "/")
                m.type = tarfile.DIRTYPE
                t.addfile(m)
                continue
            m = tarfile.TarInfo(name)
            m.size = len(data)
            t.addfile(m, io.BytesIO(data))


def _make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)


UV_BODY = b"#!/bin/sh\necho uv 0.12.13\n"


class ExtractUvBinaryLayoutTests(unittest.TestCase):
    """_extract_uv_binary 对 uv 发行包各种布局都必须取到 uv 本体。"""

    def test_new_prefixed_layout(self):
        """uv 0.12.13 起的布局：uv-<target>/uv（实测崩栈的布局）。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv-x86_64-unknown-linux-gnu.tar.gz")
            _make_tar_gz(arc, {
                "uv-x86_64-unknown-linux-gnu/": None,
                "uv-x86_64-unknown-linux-gnu/uvx": b"other",
                "uv-x86_64-unknown-linux-gnu/uv": UV_BODY,
                "uv-x86_64-unknown-linux-gnu/LICENSE": b"mit",
            })
            data, sample = menu._extract_uv_binary(arc, arc.split("/")[-1], "uv")
            self.assertEqual(data, UV_BODY)
            self.assertIsNone(sample)

    def test_legacy_layout(self):
        """旧布局 <target>/uv（修复前硬编码的成员名）仍受支持。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv-x86_64-unknown-linux-gnu.tar.gz")
            _make_tar_gz(arc, {
                "x86_64-unknown-linux-gnu/": None,
                "x86_64-unknown-linux-gnu/uv": UV_BODY,
            })
            data, _ = menu._extract_uv_binary(arc, "uv-x86_64-unknown-linux-gnu.tar.gz", "uv")
            self.assertEqual(data, UV_BODY)

    def test_flat_layout(self):
        """根级平铺：包内直接就是 uv。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv.tar.gz")
            _make_tar_gz(arc, {"uv": UV_BODY, "LICENSE": b"mit"})
            data, _ = menu._extract_uv_binary(arc, "uv.tar.gz", "uv")
            self.assertEqual(data, UV_BODY)

    def test_shallowest_match_wins(self):
        """新旧布局混放时取路径最浅的（平铺优于深层），且必须取 uv 本体。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv.tar.gz")
            _make_tar_gz(arc, {
                "uv": UV_BODY,
                "uv-x86_64-unknown-linux-gnu/uv": b"decoy",
            })
            data, _ = menu._extract_uv_binary(arc, "uv.tar.gz", "uv")
            self.assertEqual(data, UV_BODY)

    def test_windows_zip_layout(self):
        """Windows：uv-<target>/uv.exe（zip 内的前缀目录布局）。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv-x86_64-pc-windows-msvc.zip")
            _make_zip(arc, {
                "uv-x86_64-pc-windows-msvc/": "",
                "uv-x86_64-pc-windows-msvc/uv.exe": b"MZfake",
                "uv-x86_64-pc-windows-msvc/uvx.exe": b"other",
            })
            data, _ = menu._extract_uv_binary(arc, "uv-x86_64-pc-windows-msvc.zip", "uv.exe")
            self.assertEqual(data, b"MZfake")

    def test_missing_member_returns_none_with_samples(self):
        """找不到时返回 (None, 目录样本)——调用方据此干净报错，不崩栈。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv.tar.gz")
            _make_tar_gz(arc, {"some-dir/": None, "some-dir/readme": b"x"})
            data, sample = menu._extract_uv_binary(arc, "uv.tar.gz", "uv")
            self.assertIsNone(data)
            self.assertTrue(sample and "some-dir" in sample[0])

    def test_corrupt_archive_returns_none(self):
        """坏档不炸异常，返回 (None, 原因)。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv.tar.gz")
            with open(arc, "wb") as f:
                f.write(b"not a tarball at all")
            data, sample = menu._extract_uv_binary(arc, "uv.tar.gz", "uv")
            self.assertIsNone(data)
            self.assertTrue(sample)


class SeedUvRegressionTests(unittest.TestCase):
    """_seed_uv 端到端：新布局必须成功；缺成员必须干净失败（旧行为=KeyError 崩栈）。"""

    def _run_seed(self, archive_path, tmpdir):
        pkg_root = os.path.join(tmpdir, "pkg")
        os.makedirs(pkg_root, exist_ok=True)

        def fake_download(urls, dest):
            with open(archive_path, "rb") as src, open(dest, "wb") as out:
                out.write(src.read())
            return True

        import hashlib
        with open(archive_path, "rb") as f:
            real_sha = hashlib.sha256(f.read()).hexdigest()
        meta = ("0.12.13", ("uv-x86_64-unknown-linux-gnu.tar.gz", "uv"), real_sha)
        with mock.patch.object(menu, "_hermes_uv_meta", return_value=meta), \
                mock.patch.object(menu, "_download_mirror", side_effect=fake_download), \
                mock.patch.object(menu, "gh_mirrors", return_value=[]):
            return menu._seed_uv(pkg_root), pkg_root

    def test_seed_uv_succeeds_on_new_layout(self):
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv-x86_64-unknown-linux-gnu.tar.gz")
            _make_tar_gz(arc, {
                "uv-x86_64-unknown-linux-gnu/": None,
                "uv-x86_64-unknown-linux-gnu/uv": UV_BODY,
            })
            ok, pkg_root = self._run_seed(arc, d)
            self.assertTrue(ok)
            exe = os.path.join(pkg_root, ".uv_bin", "uv")
            self.assertTrue(os.path.exists(exe))
            with open(exe, "rb") as f:
                self.assertEqual(f.read(), UV_BODY)
            marker = json.load(open(os.path.join(pkg_root, ".uv_bin", "install.json")))
            self.assertEqual(marker["version"], "0.12.13")

    def test_seed_uv_fails_cleanly_when_member_missing(self):
        """旧代码在这里抛 KeyError 崩栈；修复后返回 False 且不产出半成品。"""
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "uv-x86_64-unknown-linux-gnu.tar.gz")
            _make_tar_gz(arc, {"unexpected-layout/": None, "unexpected-layout/readme": b"x"})
            ok, pkg_root = self._run_seed(arc, d)
            self.assertFalse(ok)
            self.assertFalse(os.path.exists(os.path.join(pkg_root, ".uv_bin", "uv")))
            # 下载的归档必须清掉，不给后续流程留半成品
            self.assertFalse(os.path.exists(
                os.path.join(pkg_root, ".uv_bin", "uv-x86_64-unknown-linux-gnu.tar.gz")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
