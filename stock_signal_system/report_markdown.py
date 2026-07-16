"""Shared markdown-to-HTML parsing primitives used by all report renderers."""

from __future__ import annotations

import html
import re

BASIC_REPORT_CSS = """
    body { margin: 0; background: #f6f7f9; color: #202124; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; line-height: 1.7; }
    main { max-width: 1040px; margin: 0 auto; padding: 28px 18px 56px; background: #fff; min-height: 100vh; }
    h1 { font-size: 28px; margin: 0 0 20px; }
    h2 { font-size: 21px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
    h3 { font-size: 18px; margin: 22px 0 8px; }
    p { margin: 8px 0; }
    ul { padding-left: 22px; margin: 8px 0 16px; }
    li { margin: 5px 0; }
    .table-wrap { overflow-x: auto; margin: 10px 0 22px; border: 1px solid #e5e7eb; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; min-width: 860px; font-size: 14px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }
    th { background: #f8fafc; font-weight: 700; color: #111827; }
    tr:nth-child(even) td { background: #fbfcfd; }
    tr:last-child td { border-bottom: 0; }
    strong { font-weight: 700; }
    @media (max-width: 560px) { main { padding: 20px 14px 44px; } h1 { font-size: 23px; } h2 { font-size: 19px; } }
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
