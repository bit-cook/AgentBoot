#!/usr/bin/env python3
"""Render the canonical Markdown docs into static HTML pages for the site.

The documentation lives in the repository root as Markdown (README.md,
README.en.md, 安装指南.md, docs/en/install-guide.md).  The site used to link
straight to GitHub for these; this renderer produces standalone HTML pages
that reuse the site's own CSS so the docs read as part of the product.

Pure standard library: no markdown package is installed on the release
runner, and adding one would need a lockfile bump for zero benefit.  The
renderer supports exactly the constructs the four canonical docs use
(headings, tables, fenced code, lists, bold, inline code, links, blockquotes,
and raw HTML anchors).  scripts/sync-web-assets.py copies the output into the
worker bundle; tests/test_docs_pages.py guards structure and drift.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "pages" / "docs"

# source -> (output, lang, title, description)
DOCS = {
    "安装指南.md": ("install-guide.html", "zh-CN", "安装指南",
                   "一键安装 · 离线部署 · 自定义构建 · 模型配置 · 故障排查"),
    "docs/en/install-guide.md": ("en/install-guide.html", "en", "Install Guide",
                                 "One-command install · offline deployment · custom builds · models · troubleshooting"),
    "README.md": ("readme.html", "zh-CN", "项目说明",
                  "功能总览 · 支持的 Agent · 内置保底 Agent · 卸载与安全说明"),
    "README.en.md": ("en/readme.html", "en", "Project README",
                     "Feature overview · supported agents · built-in fallback agent · uninstall and security notes"),
}

NAV = {
    "zh-CN": [("index.html", "首页"), ("install-guide.html", "安装指南"),
              ("readme.html", "项目说明"), ("../en/install-guide.html", "EN")],
    "en": [("../index.html", "Home"), ("install-guide.html", "Install Guide"),
           ("readme.html", "Project README"), ("../install-guide.html", "中文")],
}

CSS_VERSION = "1.7.3"


def slugify(text: str) -> str:
    """GitHub-compatible-ish anchor slug for heading ids."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*_\[\]()#!.,:;/\\\"']", "", text)
    text = text.strip().lower().replace(" ", "-")
    return text or "section"


def inline(text: str) -> str:
    """Render inline markdown: code, bold, links.  Escape everything else."""
    # Protect inline code first so its content is not further transformed.
    codes: list[str] = []

    def stash(match: re.Match) -> str:
        codes.append(match.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash, text)
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)), text)
    text = re.sub(r"\x00(\d+)\x00",
                  lambda m: "<code>%s</code>" % codes[int(m.group(1))].replace("&", "&amp;").replace("<", "&lt;"), text)
    return text


def render_table(rows: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if len(rows) > 2 else []
    out = ['<div class="table-scroll" role="region" tabindex="0"><table class="agent-table">']
    out.append("<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % inline(c) for c in header))
    out.append("<tbody>")
    for row in body:
        out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in row))
    out.append("</tbody></table></div>")
    return "".join(out)


def render_blocks(lines: list[str]) -> str:
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # Raw HTML anchor lines pass through (they carry section ids).
        if stripped.startswith("<a id="):
            out.append(stripped)
            i += 1
            continue
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith("```"):
            i += 1
            code: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence
            out.append("<pre><code>%s</code></pre>"
                       % "\n".join(code).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue
        if stripped.startswith("|"):
            rows: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            hid = slugify(text)
            out.append("<h%d id=\"%s\">%s</h%d>" % (level, hid, inline(text), level))
            i += 1
            continue
        if stripped.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % inline(" ".join(quote)))
            continue
        if re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while i < n:
                s = lines[i].strip()
                if re.match(r"^[-*]\s+", s):
                    items.append(re.sub(r"^[-*]\s+", "", s))
                    i += 1
                elif (items and s and lines[i][:1] in (" ", "\t")
                      and not re.match(r"^(#{1,6}\s|\||```|>|<a id=|<)", s)):
                    items[-1] += " " + s  # lazy continuation
                    i += 1
                else:
                    break
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline(c) for c in items))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(c) for c in items))
            continue
        # Paragraph: gather until blank or a block starter.
        para: list[str] = []
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|\||```|>|<a id=|<div|</)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para)))
        else:
            # A block starter we do not consume (e.g. raw <div>) passes through.
            out.append(line)
            i += 1
    return "\n".join(out)


def page_shell(lang: str, title: str, description: str, body: str, depth: str) -> str:
    nav = "".join('<a class="nav-link" href="%s">%s</a>' % (href, label) for href, label in NAV[lang])
    home = "../index.html" if depth == "en" else "index.html"
    # en pages live one directory deeper; zh pages sit directly under docs/.
    prefix = "../" if depth == "en" else ""
    canonical = "https://osome.work/AgentBoot/docs/%s" % ("en/install-guide.html" if depth == "en" else "install-guide.html")
    return """<!doctype html>
<html lang="%s">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="%s" />
    <meta name="theme-color" content="#fffdf5" />
    <meta name="color-scheme" content="light" />
    <title>%s · AgentBoot</title>
    <link rel="canonical" href="%s" />
    <link rel="icon" href="%sassets/favicon.svg?v=%s&b=2" type="image/svg+xml" />
    <link rel="stylesheet" href="%sassets/site.css?v=%s&b=4" />
    <link rel="stylesheet" href="%sassets/docs.css?v=%s" />
  </head>
  <body>
    <a class="skip-link" href="#main">跳到主要内容</a>
    <nav class="site-nav shell" aria-label="主导航">
      <a class="brand" href="%s" aria-label="AgentBoot">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>AgentBoot</span>
      </a>
      <div class="nav-links">%s</div>
    </nav>
    <main id="main" class="shell doc-page">
%s
    </main>
    <footer class="site-footer shell">
      <div class="footer-row">
        <div>
          <a class="brand" href="%s"><span class="brand-mark" aria-hidden="true"></span><span>AgentBoot</span></a>
          <p class="footer-note">MIT License · <a href="https://github.com/bit-cook/AgentBoot">GitHub</a> · <a href="https://github.com/bit-cook/AgentBoot/releases">Releases</a></p>
        </div>
        <div class="footer-links">
          <a href="https://boot.ide.pub/health">健康检查</a>
          <a href="https://bit-cook.github.io/AgentBoot/">Pages 镜像</a>
        </div>
      </div>
    </footer>
  </body>
</html>
""" % (lang, description.replace('"', "&quot;"), title, canonical,
       prefix, CSS_VERSION, prefix, CSS_VERSION, prefix, CSS_VERSION,
       home, nav, body, home)


DOC_CSS = """/* Documentation pages: typography for rendered markdown. */
.doc-page { padding: 2.5rem 0 4rem; max-width: 56rem; }
.doc-page h1 { font-size: 2.1rem; line-height: 1.2; margin: 0 0 1.2rem; }
.doc-page h2 { font-size: 1.45rem; margin: 2.4rem 0 0.9rem; padding-top: 1.2rem; border-top: 1px solid var(--line); }
.doc-page h3 { font-size: 1.15rem; margin: 1.8rem 0 0.6rem; }
.doc-page h4 { font-size: 1rem; margin: 1.4rem 0 0.5rem; }
.doc-page p { margin: 0 0 1rem; line-height: 1.75; }
.doc-page ul, .doc-page ol { margin: 0 0 1.1rem; padding-left: 1.4rem; line-height: 1.75; }
.doc-page li { margin: 0.3rem 0; }
.doc-page blockquote { margin: 0 0 1.1rem; padding: 0.8rem 1.1rem; background: var(--soft); border-left: 3px solid var(--green); border-radius: 0 var(--radius, 10px) var(--radius, 10px) 0; }
.doc-page blockquote p { margin: 0; }
.doc-page pre { margin: 0 0 1.2rem; padding: 1rem 1.1rem; background: #10231b; color: #e7f5ec; border-radius: 12px; overflow-x: auto; font-size: 0.86rem; line-height: 1.6; }
.doc-page pre code { background: none; padding: 0; color: inherit; font-size: inherit; }
.doc-page code { background: var(--green-soft); color: var(--green-dark); padding: 0.1rem 0.35rem; border-radius: 6px; font-size: 0.88em; }
.doc-page a { color: var(--green-dark); }
.doc-page hr { border: none; border-top: 1px solid var(--line); margin: 2rem 0; }
.doc-page .table-scroll { margin: 0 0 1.2rem; }
.doc-page table { width: 100%; }
"""


def render(source: Path, output: str, lang: str, title: str, description: str) -> str:
    text = source.read_text(encoding="utf-8")
    body = render_blocks(text.splitlines())
    depth = "en" if lang == "en" else "zh"
    return page_shell(lang, title, description, body, depth)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify generated pages are up to date without writing")
    args = parser.parse_args()

    outputs: dict[Path, str] = {}
    for source, (output, lang, title, description) in DOCS.items():
        path = ROOT / source
        if not path.exists():
            print("missing source: %s" % source, file=sys.stderr)
            return 1
        outputs[OUTPUT_DIR / output] = render(path, output, lang, title, description)

    css_path = OUTPUT_DIR / "assets" / "docs.css"
    outputs[css_path] = DOC_CSS

    stale = [p for p, content in outputs.items()
             if not p.exists() or p.read_text(encoding="utf-8") != content]
    if args.check:
        if stale:
            print("docs pages are stale: %s" % ", ".join(str(p.relative_to(ROOT)) for p in stale), file=sys.stderr)
            print("run: python3 scripts/render-docs.py", file=sys.stderr)
            return 1
        print("docs pages are up to date (%d files)" % len(outputs))
        return 0

    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("rendered %d doc files into pages/docs/" % len(outputs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
