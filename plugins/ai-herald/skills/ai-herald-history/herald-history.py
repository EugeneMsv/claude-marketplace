#!/usr/bin/env python3
"""CLI entry point for querying AI Herald historical contribution stats."""

import argparse
import os
import sys
from pathlib import Path

# Resolve hooks path via CLAUDE_PLUGIN_ROOT (set when running as a plugin skill)
plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT')
if plugin_root:
    sys.path.insert(0, os.path.join(plugin_root, 'hooks', 'ai-herald'))
else:
    # Fallback for local development: resolve relative to this script
    _script_dir = Path(__file__).resolve().parent
    _hooks_path = _script_dir.parent.parent / 'hooks' / 'ai-herald'
    sys.path.insert(0, str(_hooks_path))

from infrastructure.dependency_provider import DependencyProvider  # noqa: E402


def main() -> None:
    """Query and print AI contribution history."""
    parser = argparse.ArgumentParser(
        description='AI Herald — historical AI contribution query'
    )
    parser.add_argument(
        '--since', default=None,
        help="Filter to records committed since (e.g. '30d', '4w', '3m', '2026-01-01')"
    )
    parser.add_argument(
        '--by', default='week', choices=['week', 'month', 'commit'],
        help='Grouping period (default: week)'
    )
    parser.add_argument(
        '--author', default=None,
        help='Filter by author email address'
    )
    parser.add_argument(
        '--format', dest='output_format', default='table',
        choices=['table', 'json', 'csv'],
        help='Output format (default: table)'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Shorthand for --format=json'
    )
    args = parser.parse_args()

    output_format = 'json' if args.json else args.output_format

    provider = DependencyProvider('HISTORY')
    result = provider.build_history_query_service().query(
        since=args.since,
        by=args.by,
        author=args.author,
        output_format=output_format,
    )
    print(result)


if __name__ == '__main__':
    main()
