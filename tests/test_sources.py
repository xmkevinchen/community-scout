from __future__ import annotations

import unittest

from community_scout.sources import (
    extract_repository_urls,
    normalize_repository_url,
    parse_awesome_markdown,
    parse_hellogithub_markdown,
)


class SourceParserTests(unittest.TestCase):
    def test_hellogithub_extracts_redirect_target_and_category(self) -> None:
        markdown = """
### Python 项目
1、[Example](https://hellogithub.com/periodical/statistics/click?target=https://github.com/acme/example)：一个支持中文搜索的工具。

### 其它
2、[Second](https://github.com/acme/second)：第二个项目。
"""

        leads = parse_hellogithub_markdown(
            markdown,
            community_url="https://example.test/volume/1",
            source_ref="content/HelloGitHub1.md",
        )

        self.assertEqual(len(leads), 2)
        self.assertEqual(leads[0].repository_url, "https://github.com/acme/example")
        self.assertEqual(leads[0].category, "Python")
        self.assertIn("中文搜索", leads[0].summary)
        self.assertEqual(leads[1].category, "其它")

    def test_awesome_parser_keeps_heading_as_category(self) -> None:
        markdown = """
### AI Agent
- [Scout](https://github.com/acme/scout) - 多来源社区发现工具。
- [Website](https://example.com/not-a-repo) - 不是 repository。
"""

        leads = parse_awesome_markdown(
            markdown,
            community_url="https://example.test/community",
            source_ref="README.md",
        )

        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].title, "Scout")
        self.assertEqual(leads[0].category, "AI Agent")
        self.assertEqual(leads[0].summary, "多来源社区发现工具。")

    def test_repository_normalization_removes_subpaths_and_git_suffix(self) -> None:
        self.assertEqual(
            normalize_repository_url("https://github.com/acme/scout/tree/main/docs"),
            "https://github.com/acme/scout",
        )
        self.assertEqual(
            normalize_repository_url("https://github.com/acme/scout.git"),
            "https://github.com/acme/scout",
        )

    def test_extract_repository_urls_deduplicates(self) -> None:
        text = "See https://github.com/acme/scout and https://github.com/acme/scout/issues/2"
        self.assertEqual(extract_repository_urls(text), ["https://github.com/acme/scout"])


if __name__ == "__main__":
    unittest.main()
