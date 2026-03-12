#!/usr/bin/env python3
"""
AI Contribution Tracker - Write Pre Hook (PreToolUse Write)

Runs BEFORE a Write tool operation. Snapshots the existing file content to disk
so that ai-tracker-capture.py (PostToolUse) can compute which lines were removed
when the file is overwritten.

Hook Event: PreToolUse Write
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import HookRunner


class PreWriterHook(HookRunner):
    hook_name = 'WRITE-PRE'

    def _handle(self, provider: DependencyProvider, hook_output: HookOutputService) -> None:
        input_data = json.load(sys.stdin)
        file_path = input_data.get('tool_input', {}).get('file_path', '')

        if not file_path:
            hook_output.exit_with_success()

        provider.build_capture_service().store_pre_write_snapshot(file_path)


def main():
    """Snapshot existing file content before Write tool runs."""
    PreWriterHook().run()


if __name__ == '__main__':
    main()
