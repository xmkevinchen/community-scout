from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_codex_and_claude_manifests_share_plugin_identity(self) -> None:
        codex = json.loads((PROJECT_ROOT / ".codex-plugin" / "plugin.json").read_text())
        claude = json.loads((PROJECT_ROOT / ".claude-plugin" / "plugin.json").read_text())

        self.assertEqual(codex["name"], "community-scout")
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(codex["skills"], "./skills/")

    def test_repo_scoped_entries_resolve_to_the_canonical_skill(self) -> None:
        canonical = (PROJECT_ROOT / "skills" / "community-scout").resolve()
        codex_entry = (PROJECT_ROOT / ".agents" / "skills" / "community-scout").resolve()
        claude_entry = (PROJECT_ROOT / ".claude" / "skills" / "community-scout").resolve()

        self.assertEqual(codex_entry, canonical)
        self.assertEqual(claude_entry, canonical)
        self.assertTrue((canonical / "SKILL.md").is_file())
        self.assertTrue((canonical / "scripts" / "community_scout.py").is_file())


if __name__ == "__main__":
    unittest.main()
