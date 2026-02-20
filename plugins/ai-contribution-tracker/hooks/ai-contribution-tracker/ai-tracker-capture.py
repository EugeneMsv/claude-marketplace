#!/usr/bin/env python3
"""
AI Contribution Tracker - Capture Hook (PostToolUse Write/Edit)

Records AI-authored line hashes to track AI vs human contributions.
Part of the ai-contribution-tracker system.
"""

import sys
import json
from pathlib import Path

# Add script directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


def main():
    """Main hook execution."""
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider('CAPTURE')

    try:
        hook_input = json.load(sys.stdin)
        tool_name = hook_input.get('tool_name')
        tool_input = hook_input.get('tool_input', {})

        # Early exit: only handle Write and Edit
        if tool_name not in ['Write', 'Edit']:
            hook_output.exit_with_success()

        if not provider.config().enabled:
            provider.logger().info("AI tracker disabled in config")
            hook_output.exit_with_success()

        service = provider.build_capture_service()

        if tool_name == 'Write':
            success = service.process_write(tool_input)
        else:
            success = service.process_edit(tool_input)

        if provider.config().enable_logging:
            if success:
                provider.logger().info("Successfully processed tool use")
            else:
                provider.logger().info("Skipped (not applicable)")

        if success:
            file_path = tool_input.get('file_path', '')
            if file_path:
                file_name = Path(file_path).name
                hook_output.exit_with_success(f"✓ AI contribution tracked: {file_name}")

    except Exception as e:
        # Never block operations - silently fail
        try:
            if provider.config().enable_logging:
                provider.logger().error(f"Hook failed: {e}", exc_info=True)
        except:
            pass

    hook_output.exit_with_success()


if __name__ == '__main__':
    main()
