"""Audit the Git index or list application-only source handoff files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from msh_distribution import is_application_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List source handoff files, including eligible new sources")
    parser.add_argument("--json", action="store_true", help="ASCII-safe JSON for PowerShell source handoffs")
    args = parser.parse_args()
    command = ["git", "-C", str(ROOT), "ls-files", "-z", "--cached"]
    if args.list:
        command.extend(["--others", "--exclude-standard"])
    paths = sorted(set(subprocess.check_output(command).decode("utf-8").strip("\0").split("\0")))
    if args.list:
        included = [path for path in paths if path and is_application_file(path) and (ROOT / path).is_file()]
        if args.json:
            print(json.dumps(included, ensure_ascii=True))
        else:
            for path in included:
                print(path)
        return 0
    forbidden = [path for path in paths if path and not is_application_file(path)]
    if forbidden:
        print("Files outside the application-only policy remain in the Git index:")
        print("\n".join(forbidden))
        return 1
    print(f"PASS: {len(paths)} indexed paths contain application sources/assets/docs only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
