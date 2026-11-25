"""Offene Issues, PRs und Review-Anfragen über die GitHub-API."""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass, field

API = "https://api.github.com"


class GitHubError(Exception):
    pass


@dataclass
class Item:
    repo: str
    number: int
    title: str
    is_pr: bool
    url: str


@dataclass
class GitHubSummary:
    login: str
    open_total: int = 0
    open_items: list[Item] = field(default_factory=list)
    review_total: int = 0
    review_items: list[Item] = field(default_factory=list)
    unread_notifications: int | None = None


def get_token() -> str | None:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        token = result.stdout.strip()
        if result.returncode == 0 and token:
            return token
    return None


def parse_item(raw: dict) -> Item:
    # repository_url sieht so aus: https://api.github.com/repos/<owner>/<repo>
    repo = "/".join(raw.get("repository_url", "").split("/")[-2:])
    return Item(
        repo=repo,
        number=int(raw["number"]),
        title=raw.get("title", ""),
        is_pr="pull_request" in raw,
        url=raw.get("html_url", ""),
    )


def search(query: str, headers: dict, get_json, limit: int) -> tuple[int, list[Item]]:
    params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": max(1, limit)})
    data = get_json(f"{API}/search/issues?{params}", headers)
    return int(data.get("total_count", 0)), [parse_item(i) for i in data.get("items", [])[:limit]]


def fetch(cfg: dict, get_json, token: str | None = None) -> GitHubSummary:
    token = token or get_token()
    if not token:
        raise GitHubError("Kein Token gefunden. `gh auth login` ausführen oder GITHUB_TOKEN setzen.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    limit = int(cfg.get("max_items", 5))
    login = get_json(f"{API}/user", headers)["login"]
    summary = GitHubSummary(login=login)
    summary.open_total, summary.open_items = search(f"is:open archived:false user:{login}", headers, get_json, limit)
    summary.review_total, summary.review_items = search(f"is:open is:pr review-requested:{login}", headers, get_json, limit)
    try:
        notifications = get_json(f"{API}/notifications?per_page=50", headers)
        summary.unread_notifications = len(notifications) if isinstance(notifications, list) else None
    except Exception:  # noqa: BLE001 – Benachrichtigungen sind optional (Token braucht passenden Scope)
        summary.unread_notifications = None
    return summary
