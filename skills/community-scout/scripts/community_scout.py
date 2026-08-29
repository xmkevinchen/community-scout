#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[3]
    source_root = plugin_root / "src"
    package_root = source_root / "community_scout"
    if not package_root.is_dir():
        print(
            f"Community Scout package not found at {package_root}. "
            "Run this launcher from the installed community-scout plugin.",
            file=sys.stderr,
        )
        return 2
    sys.path.insert(0, str(source_root))
    from community_scout.cli import main as cli_main

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
