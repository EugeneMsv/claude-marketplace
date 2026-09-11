#!/usr/bin/env python3
"""Archive old plans using the explicitly selected host's storage rules."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks/plan-guard"))
from plan_storage import archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("age", nargs="?", default="2w")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(f"Plans selected: {archive(args.age, args.dry_run)}")
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
