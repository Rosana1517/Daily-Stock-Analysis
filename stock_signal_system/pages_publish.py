from __future__ import annotations

import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublishResult:
    repo_dir: Path
    report_name: str
    committed: bool
    pushed: bool
    url: str | None = None


def publish_report_to_pages(
    report_html_path: Path,
    repo_dir: Path,
    public_base_url: str | None = None,
    repo_url: str = "https://github.com/Rosana1517/Daily-Stock-Analysis.git",
) -> PublishResult:
    report_html_path = report_html_path.resolve()
    repo_dir = repo_dir.resolve()
    if not report_html_path.exists():
        raise FileNotFoundError(f"Report HTML does not exist: {report_html_path}")

    _ensure_repo(repo_dir, repo_url)
    reports_dir = repo_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    target = reports_dir / report_html_path.name
    if report_html_path != target.resolve():
        shutil.copy2(report_html_path, target)

    index_path = repo_dir / "index.html"
    index_path.write_text(_build_index(reports_dir), encoding="utf-8")
    (repo_dir / ".nojekyll").write_text("", encoding="utf-8")

    _git(repo_dir, "add", "index.html", ".nojekyll", f"reports/{report_html_path.name}")
    if not _has_staged_changes(repo_dir):
        return PublishResult(
            repo_dir=repo_dir,
            report_name=report_html_path.name,
            committed=False,
            pushed=False,
            url=_public_url(public_base_url, report_html_path.name),
        )

    _git(repo_dir, "commit", "-m", f"Publish stock signal report {report_html_path.stem[-10:]}")
    _git(repo_dir, "push")
    return PublishResult(
        repo_dir=repo_dir,
        report_name=report_html_path.name,
        committed=True,
        pushed=True,
        url=_public_url(public_base_url, report_html_path.name),
    )


def _ensure_repo(repo_dir: Path, repo_url: str) -> None:
    if (repo_dir / ".git").exists():
        if os.getenv("GITHUB_ACTIONS") == "true":
            return
        _git(repo_dir, "pull", "--ff-only")
        return
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", repo_url, str(repo_dir)], check=True)


def _git(repo_dir: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo_dir, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _has_staged_changes(repo_dir: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=repo_dir,
        text=True,
        capture_output=True,
    )
    return result.returncode == 1


def _build_index(reports_dir: Path) -> str:
    links = []
    for path in sorted(reports_dir.glob("stock_signals_*.html"), reverse=True):
        label = path.stem.replace("stock_signals_", "每日選股觀察報告 - ")
        links.append(f'      <li><a href="reports/{path.name}">{label}</a></li>')
    list_items = "\n".join(links) or "      <li>尚無報告</li>"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Stock Analysis</title>
  <style>
    body {{ margin: 0; background: #f6f7f9; color: #202124; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; line-height: 1.7; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 32px 18px; background: #fff; min-height: 100vh; }}
    h1 {{ font-size: 28px; margin: 0 0 16px; }}
    a {{ color: #0b57d0; }}
  </style>
</head>
<body>
  <main>
    <h1>Daily Stock Analysis</h1>
    <p>每日選股觀察報告索引。</p>
    <ul>
{list_items}
    </ul>
  </main>
</body>
</html>
"""


def _public_url(public_base_url: str | None, report_name: str) -> str | None:
    if not public_base_url:
        return None
    return f"{public_base_url.rstrip('/')}/{report_name}"
