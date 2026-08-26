"""Shared markdown-to-HTML parsing primitives used by all report renderers."""

from __future__ import annotations

import html
import re

GOOGLE_FONTS_LINK = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@600;700;900&display=swap" rel="stylesheet">"""

BASIC_REPORT_CSS = """
    :root {
      --ink: #1c1712;
      --ink-soft: #5b5348;
      --paper: #faf6ee;
      --paper-card: #fffdf8;
      --line: #e6ddc9;
      --brass: #a97327;
      --brass-deep: #7c5419;
      --up: #b3261e;
      --down: #1f7a4d;
      --font-display: "Noto Serif TC", "Times New Text", serif;
      --font-body: "Noto Sans TC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    body {
      margin: 0;
      background:
        radial-gradient(ellipse 900px 480px at 12% -8%, rgba(169,115,39,.10), transparent 60%),
        var(--paper);
      color: var(--ink);
      font-family: var(--font-body);
      line-height: 1.7;
      -webkit-font-smoothing: antialiased;
    }
    main {
      max-width: 1040px;
      margin: 0 auto;
      padding: 34px 20px 64px;
      background: var(--paper-card);
      min-height: 100vh;
      border-left: 1px solid var(--line);
      border-right: 1px solid var(--line);
      box-shadow: 0 0 0 1px rgba(28,23,18,.02);
    }
    h1 {
      font-family: var(--font-display);
      font-weight: 900;
      font-size: 30px;
      letter-spacing: .01em;
      margin: 0 0 6px;
      color: var(--ink);
      position: relative;
      padding-bottom: 16px;
    }
    h1::after {
      content: "";
      position: absolute; left: 0; bottom: 0;
      width: 64px; height: 3px;
      background: linear-gradient(90deg, var(--brass), transparent);
      border-radius: 2px;
    }
    h2 {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 20px;
      letter-spacing: .01em;
      margin: 34px 0 12px;
      padding: 0 0 8px 14px;
      border-bottom: 1px solid var(--line);
      border-left: 3px solid var(--brass);
      color: #2a2115;
    }
    h3 { font-family: var(--font-display); font-weight: 700; font-size: 16px; margin: 22px 0 8px; color: #2a2115; }
    p { margin: 8px 0; color: var(--ink-soft); }
    ul { padding-left: 22px; margin: 8px 0 16px; }
    li { margin: 6px 0; color: var(--ink-soft); }
    .table-wrap { overflow-x: auto; margin: 12px 0 24px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper-card); }
    table { width: 100%; border-collapse: collapse; min-width: 860px; font-size: 13.5px; }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-variant-numeric: tabular-nums; }
    th { background: #f3ecdb; font-family: var(--font-mono); font-weight: 600; font-size: 11px; letter-spacing: .07em; text-transform: uppercase; color: var(--brass-deep); }
    tr:nth-child(even) td { background: #fbf8f1; }
    tr:last-child td { border-bottom: 0; }
    tr:hover td { background: #f6efdd; }
    strong { font-weight: 700; color: var(--ink); }
    code { font-family: var(--font-mono); background: #f1ead6; padding: 1px 5px; border-radius: 4px; font-size: .92em; }
    @media (max-width: 560px) {
      main { padding: 22px 14px 48px; border-left: 0; border-right: 0; }
      h1 { font-size: 24px; }
      h2 { font-size: 18px; }
    }
"""


def render_markdown_body(markdown: str) -> list[str]:
    body_lines = []
    in_list = False
    table_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body_lines.append("</ul>")
            in_list = False

    def flush_table() -> None:
        if table_lines:
            body_lines.append(markdown_table_to_html(table_lines))
            table_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            flush_table()
            close_list()
            continue
        if is_table_line(line):
            close_list()
            table_lines.append(line)
            continue
        flush_table()
        if is_supported_html_block(line):
            close_list()
            body_lines.append(line)
            continue
        if line.startswith("# "):
            close_list()
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            close_list()
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            close_list()
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{inline_markdown(line[2:])}</li>")
        else:
            close_list()
            body_lines.append(f"<p>{inline_markdown(line)}</p>")
    flush_table()
    close_list()
    return body_lines


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def markdown_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def is_supported_html_block(line: str) -> bool:
    normalized = line.strip().lower()
    if not (normalized.startswith("<") and normalized.endswith(">")):
        return False
    allowed_prefixes = (
        "<table",
        "</table",
        "<tr",
        "</tr",
        "<td",
        "</td",
        "<th",
        "</th",
        "<thead",
        "</thead",
        "<tbody",
        "</tbody",
        "<strong",
        "</strong",
        "<br",
        "<div",
        "</div",
        "<section",
        "</section",
        "<details",
        "</details",
        "<summary",
        "</summary",
        "<article",
        "</article",
        "<ul",
        "</ul",
        "<li",
        "</li",
        "<code",
        "</code",
        "<h1",
        "</h1",
        "<h2",
        "</h2",
        "<h3",
        "</h3",
        "<p",
        "</p",
    )
    return normalized.startswith(allowed_prefixes)


def markdown_table_to_html(lines: list[str]) -> str:
    rows = [split_table_row(line) for line in lines]
    if len(rows) >= 2 and all(is_separator_cell(cell) for cell in rows[1]):
        header = rows[0]
        body = rows[2:]
    else:
        header = []
        body = rows
    parts = ['<div class="table-wrap"><table>']
    if header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{inline_markdown(cell)}</th>" for cell in header)
        parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body:
        parts.append("<tr>")
        parts.extend(f"<td>{inline_markdown(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator_cell(cell: str) -> bool:
    normalized = cell.strip().replace(":", "").replace("-", "")
    return normalized == ""
