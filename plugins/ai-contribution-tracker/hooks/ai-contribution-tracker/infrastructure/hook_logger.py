"""Hook logger utility with prefix and traceId support."""

import logging
import uuid
from pathlib import Path
from typing import Tuple


class HookLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that injects hook_name and trace_id into log messages."""

    def process(self, msg, kwargs):
        """Add extra context to log records."""
        return f"[{self.extra['hook_name']}:{self.extra['trace_id']}] {msg}", kwargs


def setup_hook_logger(
    hook_name: str,
    log_file: Path,
    enable_logging: bool
) -> Tuple[logging.Logger, str]:
    """Setup logger with hook prefix and traceId.

    Args:
        hook_name: Hook identifier (e.g., 'CAPTURE', 'INJECT', 'FORMAT-PRE', 'FORMAT-POST')
        log_file: Path to log file
        enable_logging: Whether logging is enabled

    Returns:
        Tuple of (configured logger adapter, trace_id)
    """
    # Generate unique traceId for this execution
    trace_id = uuid.uuid4().hex[:8]

    # Setup base logging configuration
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO if enable_logging else logging.CRITICAL + 1,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    # Get base logger
    base_logger = logging.getLogger(f'ai-tracker-{hook_name.lower()}')

    # Wrap in adapter with extra context
    logger = HookLoggerAdapter(
        base_logger,
        {'hook_name': hook_name, 'trace_id': trace_id}
    )

    return logger, trace_id
