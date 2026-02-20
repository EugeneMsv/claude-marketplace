"""Common hook execution wrapper for AI contribution tracker hooks."""

from typing import Callable

from infrastructure.configuration import ConfigurationLoader
from infrastructure.dependency_provider import DependencyProvider
from infrastructure.hook_output_service import HookOutputService


def run_hook(
    hook_name: str,
    handler: Callable[[DependencyProvider, HookOutputService], None]
) -> None:
    """Run a hook handler with standard setup, error handling, and exit.

    Sets up version, hook_output, and provider, then delegates to handler.
    On exception, logs the error (if logging is enabled) and exits cleanly.
    SystemExit and KeyboardInterrupt are never swallowed — they propagate.

    Args:
        hook_name: Identifier used as logger prefix (e.g. 'CAPTURE', 'INJECT')
        handler: Callable that receives (provider, hook_output) and performs
                 the hook's business logic. May call hook_output.exit_with_success()
                 directly for early exits.
    """
    version = ConfigurationLoader.resolve_plugin_version()
    hook_output = HookOutputService(version)
    provider = DependencyProvider(hook_name)

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
