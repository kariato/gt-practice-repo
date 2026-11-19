"""Render a Markdown report as standalone HTML (requires markdown-it-py).

Usage: python3 scripts/render_report_html.py reports/email_monitoring_final_report.md
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/kariato/GTPracticum/blob/main/'
CSS = '''
:root { color-scheme: light; --ink: #203046; --muted: #586a7d; --line: #dbe3ec; --accent: #195b85; }
* { box-sizing: border-box; }
body { margin: 0; background: #edf2f6; color: var(--ink); font: 16px/1.65 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.page { max-width: 1180px; margin: 0 auto; background: white; min-height: 100vh; padding: 36px 48px 80px; }
.topbar { display: flex; justify-content: space-between; gap: 20px; border-bottom: 2px solid var(--accent); padding-bottom: 14px; margin-bottom: 32px; font-size: .85rem; color: var(--muted); }
.topbar strong { text-transform: uppercase; letter-spacing: .12em; }
a { color: #145e91; text-underline-offset: 3px; }
h1, h2, h3 { line-height: 1.25; color: #102b45; scroll-margin-top: 20px; }
h1 { font-size: 2.45rem; letter-spacing: -.035em; max-width: 850px; margin: 0 0 24px; }
h2 { font-size: 1.6rem; border-top: 1px solid var(--line); padding-top: 30px; margin-top: 42px; }
h3 { font-size: 1.14rem; margin: 30px 0 12px; }
p { margin: 14px 0; }
li { margin: 8px 0; }
strong { font-weight: 650; }
nav { background: #f0f6fa; padding: 18px 24px; border-left: 4px solid var(--accent); margin: 28px 0 36px; }
nav h2 { margin: 0 0 8px; padding: 0; border: 0; font-size: 1rem; }
nav ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2px 25px; padding: 0; list-style: none; margin: 0; }
nav li { margin: 3px 0; font-size: .88rem; }
.table-wrap { overflow-x: auto; margin: 20px 0 24px; border: 1px solid var(--line); border-radius: 5px; }
table { width: 100%; border-collapse: collapse; font-size: .85rem; line-height: 1.45; }
th, td { padding: 11px 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: #173e5d; background: #edf4f9; font-weight: 650; }
tbody tr:nth-child(even) { background: #f8fafc; }
tbody tr:last-child td { border-bottom: 0; }
pre { overflow-x: auto; background: #f4f7fa; padding: 18px 20px; border: 1px solid var(--line); border-radius: 5px; font-size: .82rem; line-height: 1.55; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
p code, li code { font-size: .87em; background: #f0f3f6; padding: 1px 4px; border-radius: 3px; }
footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid var(--line); font-size: .85rem; color: var(--muted); }
@media (max-width: 760px) { .page { padding: 24px 18px 45px; } h1 { font-size: 1.9rem; } h2 { font-size: 1.35rem; } nav ul { grid-template-columns: 1fr; } table { min-width: 700px; } .topbar { display: block; } }
@media print { @page { margin: 15mm; } body { background: white; font-size: 10pt; } .page { margin: 0; padding: 0; max-width: none; } .topbar, nav { display: none; } h1 { font-size: 22pt; } h2 { font-size: 15pt; break-after: avoid; } h3 { break-after: avoid; } table { font-size: 8pt; } tr { break-inside: avoid; } thead { display: table-header-group; } .table-wrap { overflow: visible; } pre { white-space: pre-wrap; } a { color: inherit; } }
'''


def render(source):
    markdown = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = markdown.parse(source.read_text())
    headings = []
    ids = set()
    title = source.stem
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            label = tokens[i+1].content
            slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')
            original = slug
            suffix = 2
            while slug in ids:
                slug = f'{original}-{suffix}'
                suffix += 1
            ids.add(slug)
            token.attrSet('id', slug)
            if token.tag == 'h1':
                title = label
            elif token.tag == 'h2':
                headings.append((slug, label))
        for child in token.children or []:
            if child.type == 'link_open':
                target = child.attrGet('href')
                if target and not urlsplit(target).scheme and not target.startswith('#'):
                    relative = (source.parent / target).resolve().relative_to(ROOT)
                    child.attrSet('href', REPOSITORY + relative.as_posix())
    body = markdown.renderer.render(tokens, markdown.options, {})
    body = body.replace('<table>', '<div class="table-wrap"><table>').replace('</table>', '</table></div>')
    contents = '<nav aria-label="Report contents"><h2>Contents</h2><ul>' + ''.join(
        f'<li><a href="#{slug}">{html.escape(label)}</a></li>' for slug, label in headings) + '</ul></nav>'
    # Keep the title and report metadata above the contents.
    first_section = body.find('<h2')
    body = body[:first_section] + contents + body[first_section:]
    source_url = REPOSITORY + source.resolve().relative_to(ROOT).as_posix()
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main class="page">
<div class="topbar"><strong>Project closeout</strong><a href="{source_url}">Markdown source on GitHub</a></div>
<article>{body}</article>
<footer>Standalone report: text, tables, and styles are embedded for offline reading. Evidence links open the corresponding repository artifacts or external documentation.</footer>
</main>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    destination = args.source.with_suffix('.html')
    destination.write_text(render(args.source))
    print(f'Wrote {destination}')


if __name__ == '__main__':
    main()
