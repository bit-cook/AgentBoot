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


def page_shell(lang: str, title: str, description: str, body: str, toc: str, depth: str) -> str:
    nav = "".join('<a class="nav-link" href="%s">%s</a>' % (href, label) for href, label in NAV[lang])
    home = "../index.html" if depth == "en" else "index.html"
    prefix = "../" if depth == "en" else ""
    canonical = "https://osome.work/AgentBoot/docs/%s" % ("en/install-guide.html" if depth == "en" else "install-guide.html")
    if lang == "en":
        crumb = '<a href="%sindex.html">Home</a><span class="crumb-sep">/</span><span class="crumb-current">Docs</span>' % prefix
        intro = "Everything you need to install, configure, and troubleshoot AgentBoot."
    else:
        crumb = '<a href="%sindex.html">首页</a><span class="crumb-sep">/</span><span class="crumb-current">文档</span>' % prefix
        intro = "安装、配置与故障排查——你需要知道的一切都在这里。"
    layout = "doc-layout" if toc else "doc-layout doc-layout-wide"
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
    <header class="doc-hero">
      <div class="shell">
        <nav class="doc-crumb" aria-label="Breadcrumb">%s</nav>
        <h1 class="doc-title">%s</h1>
        <p class="doc-intro">%s</p>
      </div>
    </header>
    <main id="main" class="shell %s">
%s
      <article class="doc-content">
%s
      </article>
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
       home, nav, crumb, title, intro, layout, toc, body, home)


DOC_CSS = """/* Documentation pages: rich typography for rendered markdown. */
:root { --doc-max: 46rem; }

/* ---------- 文档头 ---------- */
.doc-hero {
  background:
    radial-gradient(60rem 20rem at 15% -10rem, var(--sun-soft), transparent 60%),
    linear-gradient(180deg, var(--soft), var(--paper));
  border-bottom: 1px solid var(--line);
  padding: 2.6rem 0 2.2rem;
}
.doc-crumb { display: flex; gap: 0.45rem; align-items: center; font-size: 0.85rem; color: var(--muted, #5b6b62); margin-bottom: 0.9rem; }
.doc-crumb a { color: var(--green-dark); text-decoration: none; }
.doc-crumb a:hover { text-decoration: underline; }
.crumb-sep { color: var(--line); }
.crumb-current { color: var(--muted, #5b6b62); }
.doc-title {
  font-family: var(--display);
  font-size: clamp(1.9rem, 1.4rem + 1.8vw, 2.6rem);
  line-height: 1.15; letter-spacing: -0.01em;
  margin: 0 0 0.6rem; color: var(--ink, #14261d);
}
.doc-intro { margin: 0; color: var(--muted, #5b6b62); font-size: 1.02rem; max-width: 40rem; }

/* ---------- 双栏布局 ---------- */
.doc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 2.2rem;
  padding: 2.4rem 0 4rem;
  align-items: start;
}
.doc-layout:has(.doc-toc) { grid-template-columns: 15rem minmax(0, 1fr); }
@media (max-width: 60rem) {
  .doc-layout:has(.doc-toc) { grid-template-columns: minmax(0, 1fr); }
}

/* ---------- 目录侧栏 ---------- */
.doc-toc {
  position: sticky; top: 5.2rem;
  border-left: 2px solid var(--line);
  padding-left: 1.1rem;
  max-height: calc(100vh - 7rem);
  overflow-y: auto;
  font-size: 0.86rem;
}
.toc-title {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--muted, #5b6b62);
  margin: 0 0 0.7rem;
}
.doc-toc ul { list-style: none; margin: 0; padding: 0; }
.doc-toc li { margin: 0; }
.toc-item a {
  display: block; padding: 0.28rem 0.4rem;
  color: var(--muted, #5b6b62); text-decoration: none;
  border-radius: 6px; line-height: 1.45;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.toc-item a:hover { color: var(--green-dark); background: var(--green-soft); }
.toc-h3 a { padding-left: 1.15rem; font-size: 0.82rem; }

/* ---------- 正文 ---------- */
.doc-content { min-width: 0; max-width: var(--doc-max); }
.doc-content > h1 { display: none; } /* 标题已在 hero 展示 */
.doc-content h2 {
  font-family: var(--display);
  font-size: 1.5rem; line-height: 1.3;
  margin: 2.6rem 0 1rem; padding-top: 1.6rem;
  border-top: 1px solid var(--line);
  color: var(--ink, #14261d);
  scroll-margin-top: 5rem;
}
.doc-content h2:first-child { margin-top: 0; padding-top: 0; border-top: none; }
.doc-content h3 {
  font-family: var(--display);
  font-size: 1.16rem; margin: 1.9rem 0 0.65rem;
  color: var(--ink, #14261d); scroll-margin-top: 5rem;
}
.doc-content h4 { font-size: 0.98rem; margin: 1.5rem 0 0.5rem; scroll-margin-top: 5rem; }
.doc-content p { margin: 0 0 1.05rem; line-height: 1.78; color: var(--body-ink, #26332c); }
.doc-content ul, .doc-content ol { margin: 0 0 1.15rem; padding-left: 1.5rem; line-height: 1.78; color: var(--body-ink, #26332c); }
.doc-content li { margin: 0.32rem 0; }
.doc-content li::marker { color: var(--green); }
.doc-content strong { color: var(--ink, #14261d); }
.doc-content hr { border: none; height: 1px; background: var(--line); margin: 2.4rem 0; }

/* 标题悬浮锚点 */
.heading-anchor {
  margin-left: 0.45rem; font-weight: 400;
  color: var(--green); opacity: 0; text-decoration: none;
  transition: opacity 120ms ease;
}
h2:hover .heading-anchor, h3:hover .heading-anchor, .heading-anchor:focus { opacity: 0.65; }
.heading-anchor:hover { opacity: 1 !important; }

/* ---------- 链接 ---------- */
.doc-content a { color: var(--green-dark); text-decoration: none; border-bottom: 1px solid color-mix(in srgb, var(--green) 35%, transparent); transition: border-color 120ms ease, color 120ms ease; }
.doc-content a:hover { color: var(--green); border-bottom-color: var(--green); }

/* ---------- 行内代码 ---------- */
.doc-content code {
  background: var(--green-soft); color: var(--green-dark);
  padding: 0.12rem 0.38rem; border-radius: 6px;
  font-family: var(--mono); font-size: 0.86em;
  border: 1px solid color-mix(in srgb, var(--green) 18%, transparent);
}

/* ---------- 代码块 ---------- */
.doc-content pre {
  margin: 0 0 1.3rem; padding: 1.05rem 1.2rem;
  background: var(--code, #10251d); color: #d9ece2;
  border-radius: 14px; overflow-x: auto;
  font-size: 0.84rem; line-height: 1.65;
  border: 1px solid color-mix(in srgb, #0c3a28 55%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.doc-content pre code { background: none; border: none; padding: 0; color: inherit; font-size: inherit; }
.doc-content pre::-webkit-scrollbar { height: 8px; }
.doc-content pre::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.18); border-radius: 4px; }

/* ---------- 引用块（提示框） ---------- */
.doc-content blockquote {
  margin: 0 0 1.3rem; padding: 0.9rem 1.15rem;
  background: linear-gradient(180deg, var(--sun-soft), color-mix(in srgb, var(--sun-soft) 45%, var(--paper)));
  border: 1px solid color-mix(in srgb, var(--sun) 45%, transparent);
  border-left: 4px solid var(--sun);
  border-radius: 4px 12px 12px 4px;
  color: #5c4a12;
}
.doc-content blockquote p { margin: 0; color: inherit; }
.doc-content blockquote code { background: rgba(255, 216, 77, 0.28); border-color: transparent; color: #6b5416; }

/* ---------- 表格 ---------- */
.doc-content .table-scroll {
  margin: 0 0 1.4rem; border: 1px solid var(--line);
  border-radius: 14px; overflow: auto; background: var(--surface);
  box-shadow: 0 1px 2px rgba(20, 38, 29, 0.04);
}
.doc-content table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.doc-content thead th {
  position: sticky; top: 0; z-index: 1;
  background: var(--soft); color: var(--ink, #14261d);
  font-family: var(--display); font-size: 0.78rem;
  letter-spacing: 0.04em; text-transform: uppercase;
  text-align: left; padding: 0.7rem 0.95rem;
  border-bottom: 1px solid var(--line); white-space: nowrap;
}
.doc-content tbody td { padding: 0.68rem 0.95rem; border-bottom: 1px solid var(--line); vertical-align: top; }
.doc-content tbody tr:last-child td { border-bottom: none; }
.doc-content tbody tr:nth-child(even) { background: color-mix(in srgb, var(--soft) 45%, var(--surface)); }
.doc-content tbody tr:hover { background: var(--green-soft); }
.doc-content td code { font-size: 0.82em; }

/* ---------- 深色偏好 ---------- */
@media (prefers-color-scheme: dark) {
  .doc-hero { background: linear-gradient(180deg, #12281e, #0e211a); }
  .doc-title, .doc-content h2, .doc-content h3, .doc-content strong { color: #eaf4ee; }
  .doc-content p, .doc-content li { color: #c3d4ca; }
  .doc-crumb, .toc-title, .doc-intro, .crumb-current { color: #8fa89b; }
  .doc-content .table-scroll { background: #12281e; border-color: #1f3a2e; }
  .doc-content thead th { background: #17352a; color: #eaf4ee; border-color: #1f3a2e; }
  .doc-content tbody td { border-color: #1f3a2e; }
  .doc-content tbody tr:nth-child(even) { background: #143025; }
  .doc-content tbody tr:hover { background: #1a3d2f; }
  .doc-content h2 { border-color: #1f3a2e; }
  .doc-toc { border-color: #1f3a2e; }
}
"""


def collect_toc(body: str, lang: str) -> str:
    """Build a sticky sidebar TOC from the rendered h2/h3 headings."""
    import re as _re
    entries = []
    for m in _re.finditer(r'<h([23]) id="([^"]+)"[^>]*>(.*?)</h\1>', body, _re.S):
        level, hid, text = m.group(1), m.group(2), m.group(3)
        plain = _re.sub(r'<a class="heading-anchor"[^>]*>#</a>', "", text)
        plain = _re.sub(r"<[^>]+>", "", plain).strip()
        if not plain:
            continue
        entries.append((level, hid, plain))
    if len(entries) < 3:
        return ""
    label = "本页目录" if lang != "en" else "On this page"
    items = []
    for level, hid, plain in entries:
        cls = "toc-item toc-h%s" % level
        items.append('<li class="%s"><a href="#%s">%s</a></li>' % (cls, hid, plain))
    return ('<aside class="doc-toc" aria-label="%s"><p class="toc-title">%s</p>'
            "<ul>%s</ul></aside>" % (label, label, "".join(items)))


def add_heading_anchors(body: str) -> str:
    """Append hover anchor links to h2/h3 headings."""
    import re as _re
    def repl(m: "_re.Match") -> str:
        hid = m.group(2)
        return (m.group(0)[:-len("</h%s>" % m.group(1))]
                + '<a class="heading-anchor" href="#%s" aria-label="Permalink">#</a></h%s>'
                % (hid, m.group(1)))
    return _re.sub(r'<h([23]) id="([^"]+)"[^>]*>.*?</h\1>', repl, body, flags=_re.S)


def render(source: Path, output: str, lang: str, title: str, description: str) -> str:
    text = source.read_text(encoding="utf-8")
    body = add_heading_anchors(render_blocks(text.splitlines()))
    toc = collect_toc(body, lang)
    depth = "en" if lang == "en" else "zh"
    return page_shell(lang, title, description, body, toc, depth)


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
