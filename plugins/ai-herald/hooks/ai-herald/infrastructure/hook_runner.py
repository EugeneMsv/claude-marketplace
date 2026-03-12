"""Common hook execution wrapper for AI contribution tracker hooks."""

import json
import sys
from typing import Any, Callable, ClassVar, Dict, List, Optional

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


# Type alias for module-level command handler functions
CommandHandler = Callable[[DependencyProvider, str], Optional[Any]]


class HookRunner:
    """Base class for all AI herald hooks.

    Subclasses declare ``hook_name`` and implement ``_handle``.
    ``run()`` is the universal entry point that wires into ``_run_hook``.
    """

    hook_name: ClassVar[str]

    def run(self) -> None:
        """Universal entry point — runs the hook lifecycle."""
        self._run_hook(self._handle)

    def _run_hook(
        self,
        handler: Callable[[DependencyProvider, HookOutputService], None]
    ) -> None:
        """Run a hook handler with standard setup, error handling, and exit.

        Sets up version, hook_output, and provider, then delegates to handler.
        On exception, logs the error (if logging is enabled) and exits cleanly.
        SystemExit and KeyboardInterrupt are never swallowed — they propagate.

        Args:
            handler: Callable that receives (provider, hook_output) and performs
                     the hook's business logic. May call hook_output.exit_with_success()
                     directly for early exits.
        """
        version = ConfigurationLoader.resolve_plugin_version()
        hook_output = HookOutputService(version)
        provider = DependencyProvider(self.hook_name)

        try:
            if not provider.config().enabled:
                hook_output.exit_with_success()
            handler(provider, hook_output)
        except Exception as e:
            try:
                if provider.config().enable_logging:
                    provider.logger().error(f"Hook failed: {e}", exc_info=True)
            except Exception:
                pass  # logger itself failed — cannot do more

        hook_output.exit_with_success()

    def _handle(self, provider: DependencyProvider, hook_output: HookOutputService) -> None:
        raise NotImplementedError


class CommandHookRunner(HookRunner):
    """Base class for Bash+DetectedCommand hooks.

    Subclasses declare ``command_handlers`` mapping DetectedCommand values to
    instance method handlers with signature ``(self, provider, command) -> Optional[Any]``.
    Override ``on_result`` for post-dispatch logic (e.g. formatting output messages).
    """

    command_handlers: ClassVar[Dict]

    def _handle(self, provider: DependencyProvider, hook_output: HookOutputService) -> None:
        command = json.load(sys.stdin).get('tool_input', {}).get('command', '')
        detector = provider.bash_command_detector()

        # Ordered git subcommands (commit, push, merge, rebase by position in command)
        detected: List = list(detector.detect_commands_ordered(command))
        # Supplement: non-position-ordered handlers (e.g. CODE_FORMATTER, BASH_FILE_DELETION)
        for cmd in detector.detect_commands(command) & set(self.command_handlers):
            if cmd not in detected:
                detected.append(cmd)

        if not any(cmd in self.command_handlers for cmd in detected):
            hook_output.exit_with_success()

        result = None
        for cmd in detected:
            handler = self.command_handlers.get(cmd)
            if handler is not None:
                provider.logger().info(f"{cmd.value} detected")
                r = handler(self, provider, command)
                if r is not None:
                    result = r
        self.on_result(provider, hook_output, result)

    def on_result(self, provider: DependencyProvider, hook_output: HookOutputService, result: Any) -> None:
        """Override to add post-dispatch logic. Default: exit cleanly."""
        hook_output.exit_with_success()
