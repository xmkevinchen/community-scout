from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Protocol
from urllib.parse import parse_qs, unquote, urlparse

from .http import HttpClient
from .models import CommunityLead


GITHUB_REPO_RE = re.compile(
    r"https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")


def normalize_repository_url(url: str) -> str | None:
    match = GITHUB_REPO_RE.search(unquote(url))
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo").removesuffix(".git")
    if repo.lower() in {"issues", "pulls", "stargazers", "topics"}:
        return None
    return f"https://github.com/{owner}/{repo}"


def unwrap_target_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    target = query.get("target")
    return unquote(target[0]) if target else url


def clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip(" |:-\t")


def extract_repository_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in GITHUB_REPO_RE.finditer(text):
        normalized = normalize_repository_url(match.group(0))
        if normalized and normalized not in urls:
            urls.append(normalized)
    return urls


class CommunitySource(Protocol):
    name: str

    def fetch(self, client: HttpClient, limit: int) -> list[CommunityLead]: ...


def parse_hellogithub_markdown(markdown: str, *, community_url: str, source_ref: str) -> list[CommunityLead]:
    leads: list[CommunityLead] = []
    category = ""
    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            category = clean_markdown(heading.group(1)).removesuffix("项目").strip()
            continue
        if not re.match(r"^\s*\d+[、.]", line):
            continue
        link = MARKDOWN_LINK_RE.search(line)
        if not link:
            continue
        repository_url = normalize_repository_url(unwrap_target_url(link.group(2)))
        if not repository_url:
            continue
        remainder = line[link.end() :]
        summary = clean_markdown(remainder.lstrip("）：): "))
        leads.append(
            CommunityLead(
                source="hellogithub",
                title=clean_markdown(link.group(1)),
                summary=summary,
                repository_url=repository_url,
                community_url=community_url,
                source_ref=source_ref,
                category=category,
            )
        )
    return leads


def parse_awesome_markdown(markdown: str, *, community_url: str, source_ref: str) -> list[CommunityLead]:
    leads: list[CommunityLead] = []
    category = ""
    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            category = clean_markdown(heading.group(1))
            continue
        if not line.lstrip().startswith("-"):
            continue
        link = MARKDOWN_LINK_RE.search(line)
        if not link:
            continue
        repository_url = normalize_repository_url(link.group(2))
        if not repository_url:
            continue
        summary = clean_markdown(line[link.end() :])
        leads.append(
            CommunityLead(
                source="guangguang",
                title=clean_markdown(link.group(1)),
                summary=summary,
                repository_url=repository_url,
                community_url=community_url,
                source_ref=source_ref,
                category=category,
            )
        )
    return leads


class HelloGitHubSource:
    name = "hellogithub"
    contents_url = "https://api.github.com/repos/521xueweihan/HelloGitHub/contents/content"

    def fetch(self, client: HttpClient, limit: int) -> list[CommunityLead]:
        entries = client.get_json(self.contents_url, github_api=True)
        if not isinstance(entries, list):
            raise ValueError("HelloGitHub content listing was not an array")

        volumes: list[tuple[int, dict[str, Any]]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            match = re.fullmatch(r"HelloGitHub(\d+)\.md", str(entry.get("name", "")))
            if match and entry.get("download_url"):
                volumes.append((int(match.group(1)), entry))
        volumes.sort(reverse=True, key=lambda item: item[0])

        leads: list[CommunityLead] = []
        for _, entry in volumes:
            markdown = client.get_text(str(entry["download_url"]))
            source_ref = str(entry.get("path", entry["name"]))
            community_url = str(entry.get("html_url") or entry["download_url"])
            leads.extend(
                parse_hellogithub_markdown(
                    markdown,
                    community_url=community_url,
                    source_ref=source_ref,
                )
            )
            if len(leads) >= limit:
                break
        return leads[:limit]


class GitHubDailySource:
    name = "githubdaily"
    issues_url = "https://api.github.com/repos/GitHubDaily/GitHubDaily/issues"
    own_repository = "https://github.com/GitHubDaily/GitHubDaily"

    def fetch(self, client: HttpClient, limit: int) -> list[CommunityLead]:
        per_page = min(max(limit, 1), 100)
        url = f"{self.issues_url}?state=all&sort=updated&direction=desc&per_page={per_page}"
        issues = client.get_json(url, github_api=True)
        if not isinstance(issues, list):
            raise ValueError("GitHubDaily issue listing was not an array")

        leads: list[CommunityLead] = []
        for issue in issues:
            if not isinstance(issue, dict) or "pull_request" in issue:
                continue
            body = str(issue.get("body") or "")
            repository_urls = [
                repo for repo in extract_repository_urls(body) if repo != self.own_repository
            ]
            for repository_url in repository_urls:
                leads.append(
                    CommunityLead(
                        source=self.name,
                        title=clean_markdown(str(issue.get("title") or repository_url.rsplit("/", 1)[-1])),
                        summary=clean_markdown(body)[:2000],
                        repository_url=repository_url,
                        community_url=str(issue.get("html_url") or self.issues_url),
                        source_ref=f"issue:{issue.get('number', 'unknown')}",
                        category="community submission",
                        published_at=str(issue.get("created_at")) if issue.get("created_at") else None,
                    )
                )
                if len(leads) >= limit:
                    return leads
        return leads


class GuangguangSource:
    name = "guangguang"
    raw_url = "https://raw.githubusercontent.com/Wechat-ggGitHub/Awesome-GitHub-Repo/main/README.md"
    community_url = "https://github.com/Wechat-ggGitHub/Awesome-GitHub-Repo"

    def fetch(self, client: HttpClient, limit: int) -> list[CommunityLead]:
        markdown = client.get_text(self.raw_url)
        leads = parse_awesome_markdown(
            markdown,
            community_url=self.community_url,
            source_ref="README.md",
        )
        return leads[:limit]


SOURCE_REGISTRY: dict[str, CommunitySource] = {
    source.name: source
    for source in (HelloGitHubSource(), GitHubDailySource(), GuangguangSource())
}


def with_capture_time(leads: list[CommunityLead], captured_at: str) -> list[CommunityLead]:
    return [replace(lead, captured_at=captured_at) for lead in leads]
