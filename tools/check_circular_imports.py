#!/usr/bin/env python3
"""Pre-commit hook wrapper that detects circular imports while ignoring
intra-package cycles (e.g. commands/__init__.py ↔ commands/audio.py)."""

import re
import subprocess
import sys


def main():
    result = subprocess.run(
        ["circular-import-precommit", *sys.argv[1:]],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return 0

    real_groups = []
    for block in re.split(r"(?=Group \d+:)", result.stdout):
        if not block.strip() or not block.startswith("Group"):
            continue

        match = re.search(r"Representative cycle:\s*\n\s*(.+)", block)
        if not match:
            real_groups.append(block)
            continue

        chain = [m.strip() for m in match.group(1).split("->")]
        top_packages = {mod.split(".")[0] for mod in chain}
        if len(top_packages) == 1:
            continue

        real_groups.append(block)

    if not real_groups:
        return 0

    print(f"Found {len(real_groups)} circular import group(s):\n")
    for group in real_groups:
        print(group)
    return 1


if __name__ == "__main__":
    sys.exit(main())
