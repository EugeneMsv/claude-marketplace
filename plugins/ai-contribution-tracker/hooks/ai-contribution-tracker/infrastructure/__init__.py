"""Infrastructure layer for AI Contribution Tracker.

This package contains classes that interact with external systems:
- Git (via subprocess)
- File system (for persistence)
- Configuration files
"""

from infrastructure.configuration import Configuration, ConfigurationLoader
from infrastructure.git_repository import GitRepository
from infrastructure.tracking_repository import TrackingRepository

__all__ = [
    'Configuration',
    'ConfigurationLoader',
    'GitRepository',
    'TrackingRepository',
]
