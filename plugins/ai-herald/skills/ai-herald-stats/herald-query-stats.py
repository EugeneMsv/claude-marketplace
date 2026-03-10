#!/usr/bin/env python3
"""CLI entry point for querying AI Herald contribution stats on demand."""

import json
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
    """Query and print current branch AI contribution statistics."""
    use_json = '--json' in sys.argv

    provider = DependencyProvider('QUERY')

    if not provider.config().enabled:
        print("AI Herald is disabled.")
        return

    branch = provider.git_repo().get_current_branch()
    if not branch:
        print("Not in a git repository or could not determine current branch.")
        return

    stats = provider.build_query_stats_service().calculate_current_stats()

    if stats is None:
        print(f"Branch: {branch}")
        print("No tracking data available for current branch.")
        return

    if use_json:
        data = stats.to_dict()
        data['branch'] = branch
        print(json.dumps(data, indent=2))
    else:
        print(f"Branch: {branch}")
        print(stats.format_description())


if __name__ == '__main__':
    main()
