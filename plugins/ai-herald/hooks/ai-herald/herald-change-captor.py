#!/usr/bin/env python3
"""
AI Contribution Tracker - Capture Hook (PostToolUse Write/Edit)

Records AI-authored line hashes to track AI vs human contributions.
Part of the ai-contribution-tracker system.
"""

import json
import sys
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService
from infrastructure.hook_runner import HookRunner


class ChangeCaptorHook(HookRunner):
    hook_name = 'CAPTURE'

    def _handle(self, provider: DependencyProvider, hook_output: HookOutputService) -> None:
        hook_input = json.load(sys.stdin)
        tool_name = hook_input.get('tool_name')
        tool_input = hook_input.get('tool_input', {})

        if tool_name not in ['Write', 'Edit']:
            hook_output.exit_with_success()

        service = provider.build_capture_service()

        if tool_name == 'Write':
            success = service.process_write(tool_input)
        else:
            success = service.process_edit(tool_input)

        if success:
            file_path = tool_input.get('file_path', '')
            if file_path:
                file_name = Path(file_path).name
                hook_output.exit_with_success(f"✓ AI contribution tracked: {file_name}")


def main():
    """Main hook execution."""
    ChangeCaptorHook().run()


if __name__ == '__main__':
    main()
