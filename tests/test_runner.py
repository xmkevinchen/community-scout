from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from community_scout.files import read_json, read_jsonl
from community_scout.models import CommunityLead
from community_scout.runner import resume_run, search_communities


class StaticSource:
    def __init__(self, name: str, repository_url: str) -> None:
        self.name = name
        self.repository_url = repository_url
        self.attempts = 0

    def fetch(self, client: object, limit: int) -> list[CommunityLead]:
        self.attempts += 1
        return [
            CommunityLead(
                source=self.name,
                title=f"Lead from {self.name}",
                summary="fixture",
                repository_url=self.repository_url,
                community_url=f"https://example.test/{self.name}",
                source_ref=f"{self.name}:1",
            )
        ][:limit]


class BrokenSource:
    name = "broken"

    def fetch(self, client: object, limit: int) -> list[CommunityLead]:
        raise RuntimeError("fixture source failed")


class CountingUpstream:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_text(self, url: str, *, github_api: bool = False) -> str:
        self.calls.append(url)
        return "cached source response"


class FlakySource:
    name = "flaky"

    def __init__(self) -> None:
        self.attempts = 0

    def fetch(self, client: object, limit: int) -> list[CommunityLead]:
        self.attempts += 1
        raw = client.get_text("https://example.test/community.md")  # type: ignore[attr-defined]
        if self.attempts == 1:
            raise RuntimeError("failed after first download")
        return [
            CommunityLead(
                source=self.name,
                title="Recovered lead",
                summary=raw,
                repository_url="https://github.com/acme/recovered",
                community_url="https://example.test/community",
                source_ref="item:1",
            )
        ][:limit]


class RunnerTests(unittest.TestCase):
    def test_run_writes_files_and_deduplicates_repositories_with_mentions(self) -> None:
        first = StaticSource("first", "https://github.com/acme/shared")
        second = StaticSource("second", "https://github.com/acme/shared")
        registry = {"first": first, "second": second, "broken": BrokenSource()}

        with tempfile.TemporaryDirectory() as temp_dir:
            handoff = search_communities(
                "shared project",
                sources=["first", "second", "broken"],
                runs_dir=Path(temp_dir),
                limit_per_source=10,
                timeout=1,
                registry=registry,
            )

            self.assertEqual(handoff["status"], "degraded")
            run_dir = Path(str(handoff["run_directory"]))
            self.assertTrue((run_dir / "request.json").is_file())
            self.assertTrue((run_dir / "report.md").is_file())
            candidates = read_jsonl(run_dir / "candidates.jsonl")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["mention_count"], 2)
            self.assertEqual(len(candidates[0]["mentions"]), 2)

            manifest = read_json(run_dir / "manifest.json")
            self.assertEqual(manifest["candidate_count"], 1)
            self.assertEqual(manifest["content_trust"], "untrusted")
            broken_status = read_json(run_dir / "sources" / "broken.status.json")
            self.assertEqual(broken_status["status"], "unavailable")

    def test_resume_skips_ready_source_and_reuses_failed_source_download(self) -> None:
        ready = StaticSource("ready", "https://github.com/acme/ready")
        flaky = FlakySource()
        upstream = CountingUpstream()
        registry = {"ready": ready, "flaky": flaky}

        with tempfile.TemporaryDirectory() as temp_dir:
            first_handoff = search_communities(
                "recoverable run",
                sources=["ready", "flaky"],
                runs_dir=Path(temp_dir),
                limit_per_source=10,
                timeout=1,
                registry=registry,
                client_factory=lambda timeout: upstream,  # type: ignore[arg-type]
            )
            self.assertEqual(first_handoff["status"], "degraded")
            self.assertEqual(ready.attempts, 1)
            self.assertEqual(flaky.attempts, 1)
            self.assertEqual(upstream.calls, ["https://example.test/community.md"])

            run_dir = Path(str(first_handoff["run_directory"]))
            raw_files = list((run_dir / "sources" / "flaky" / "raw").glob("*.md"))
            self.assertEqual(len(raw_files), 1)

            resumed = resume_run(
                run_dir,
                registry=registry,
                client_factory=lambda timeout: upstream,  # type: ignore[arg-type]
            )

            self.assertEqual(resumed["status"], "success")
            self.assertEqual(ready.attempts, 1, "completed sources must not be fetched again")
            self.assertEqual(flaky.attempts, 2)
            self.assertEqual(
                upstream.calls,
                ["https://example.test/community.md"],
                "the response downloaded before failure must come from the file cache",
            )
            flaky_status = read_json(run_dir / "sources" / "flaky.status.json")
            self.assertEqual(flaky_status["attempts"], 2)
            self.assertEqual(flaky_status["cache_hits"], 1)
            self.assertEqual(len(read_jsonl(run_dir / "candidates.jsonl")), 2)


if __name__ == "__main__":
    unittest.main()
