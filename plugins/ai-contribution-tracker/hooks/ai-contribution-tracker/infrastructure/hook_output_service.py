"""Hook output service for user messages."""

import sys
import json
from typing import Optional


class HookOutputService:
    """Service for outputting user messages from hooks.

    Handles the JSON output format required by Claude Code hooks to show
    messages to users in transcript mode (Ctrl+R).
    """

    def __init__(self, version: str = "dev"):
        """Initialize with plugin version for prefix.

        Args:
            version: Plugin version string (e.g., "0.0.14" or "dev")
        """
        self._prefix = f"[ai-tracker:{version}]"

    def exit_with_success(self, message: Optional[str] = None):
        """Output success message and exit with code 0.

        Args:
            message: Optional message to display to user.
        """
        self._exit_with_message(message, 0)

    def exit_with_failure(self, message: Optional[str] = None):
        """Output failure message and exit with code 1.

        Args:
            message: Optional message to display to user.
        """
        self._exit_with_message(message, 1)

    def _exit_with_message(self, message: Optional[str], exit_code: int):
        """Output message and exit.

        Args:
            message: Optional message to display
            exit_code: Exit code to use
        """
        if message:
            prefixed_message = f"{self._prefix} {message}"

            output = {
                "systemMessage": prefixed_message
            }

            print(json.dumps(output))

        sys.exit(exit_code)
