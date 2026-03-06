"""Configuration infrastructure."""

import json
import os
from pathlib import Path
from typing import List, Set, Optional


class Configuration:
    """Configuration settings for AI contribution tracker.

    Immutable configuration object loaded from config.json.
    """

    def __init__(
        self,
        enabled: bool,
        base_branches: List[str],
        tracked_extensions: Set[str],
        enable_logging: bool,
        log_file: str,
        format_detection_enabled: bool = True,
        format_commands: List[str] = None,
        mr_title_update_enabled: bool = False,
        mr_description_update_enabled: bool = False,
        mr_auto_creation_enabled: bool = False,
        mr_labeling_enabled: bool = False,
        housekeeping_enabled: bool = False,
        housekeeping_stale_days: int = 7,
        housekeeping_max_files: int = 5,
        code_generated_patterns: Optional[Set[str]] = None
    ):
        """Initialize configuration.

        Args:
            enabled: Whether tracker is enabled
            base_branches: Priority list of base branches
            tracked_extensions: Set of file extensions to track
            enable_logging: Whether to enable logging
            log_file: Log file name
            format_detection_enabled: Whether format detection is enabled
            format_commands: List of formatter commands to detect
            mr_title_update_enabled: Whether MR title update on push is enabled
            mr_description_update_enabled: Whether MR description update on push is enabled
            mr_auto_creation_enabled: Whether draft MR auto-creation on push is enabled
            mr_labeling_enabled: Whether MR label with AI percentage is enabled
            housekeeping_enabled: Whether housekeeping is enabled
            housekeeping_stale_days: Days threshold for stale tracking files
            housekeeping_max_files: Max files to process per housekeeping run
            code_generated_patterns: Ant-style glob patterns for code-generated files
        """
        self._enabled = enabled
        self._base_branches = base_branches.copy()
        self._tracked_extensions = tracked_extensions.copy()
        self._enable_logging = enable_logging
        self._log_file = log_file
        self._format_detection_enabled = format_detection_enabled
        self._format_commands = format_commands.copy() if format_commands else []
        self._mr_title_update_enabled = mr_title_update_enabled
        self._mr_description_update_enabled = mr_description_update_enabled
        self._mr_auto_creation_enabled = mr_auto_creation_enabled
        self._mr_labeling_enabled = mr_labeling_enabled
        self._housekeeping_enabled = housekeeping_enabled
        self._housekeeping_stale_days = housekeeping_stale_days
        self._housekeeping_max_files = housekeeping_max_files
        self._code_generated_patterns: Set[str] = set(code_generated_patterns) if code_generated_patterns else set()

        # Environment variables can override
        self._disable_env = os.environ.get('DISABLE_AI_STATS', '0') == '1'
        self._detailed_env = os.environ.get('AI_STATS_DETAILED', '0') == '1'

    @property
    def enabled(self) -> bool:
        """Check if tracker is enabled (config + environment)."""
        return self._enabled and not self._disable_env

    @property
    def base_branches(self) -> List[str]:
        """Get base branches priority list."""
        return self._base_branches.copy()

    @property
    def tracked_extensions(self) -> Set[str]:
        """Get tracked file extensions."""
        return self._tracked_extensions.copy()

    @property
    def enable_logging(self) -> bool:
        """Check if logging is enabled."""
        return self._enable_logging

    @property
    def log_file(self) -> str:
        """Get log file name."""
        return self._log_file

    @property
    def detailed_stats(self) -> bool:
        """Check if detailed stats should be shown (from environment)."""
        return self._detailed_env

    @property
    def mr_title_update_enabled(self) -> bool:
        """Check if MR title update on push is enabled."""
        return self._mr_title_update_enabled

    @property
    def mr_description_update_enabled(self) -> bool:
        """Check if MR description update on push is enabled."""
        return self._mr_description_update_enabled

    @property
    def mr_auto_creation_enabled(self) -> bool:
        """Check if draft MR auto-creation on push is enabled."""
        return self._mr_auto_creation_enabled

    @property
    def mr_labeling_enabled(self) -> bool:
        """Check if MR label with AI percentage is enabled."""
        return self._mr_labeling_enabled

    @property
    def mr_features_enabled(self) -> bool:
        """Check if any MR feature is enabled (title, description, auto-creation, or labeling)."""
        return (
            self._mr_title_update_enabled
            or self._mr_description_update_enabled
            or self._mr_auto_creation_enabled
            or self._mr_labeling_enabled
        )

    @property
    def format_detection_enabled(self) -> bool:
        """Check if format detection is enabled."""
        return self._format_detection_enabled

    @property
    def format_commands(self) -> List[str]:
        """Get list of formatter commands to detect."""
        return self._format_commands.copy()

    @property
    def housekeeping_enabled(self) -> bool:
        """Check if housekeeping is enabled."""
        return self._housekeeping_enabled

    @property
    def housekeeping_stale_days(self) -> int:
        """Get stale days threshold for housekeeping."""
        return self._housekeeping_stale_days

    @property
    def housekeeping_max_files(self) -> int:
        """Get max files to process per housekeeping run."""
        return self._housekeeping_max_files

    @property
    def code_generated_patterns(self) -> Set[str]:
        """Get Ant-style glob patterns for code-generated files."""
        return self._code_generated_patterns.copy()

    def is_extension_tracked(self, extension: str) -> bool:
        """Check if a file extension is tracked.

        Args:
            extension: File extension (with leading dot)

        Returns:
            True if extension should be tracked
        """
        return extension.lower() in self._tracked_extensions

    def should_track_file(self, file_path: Path) -> bool:
        """Check if a file should be tracked based on its extension.

        Args:
            file_path: Path to file

        Returns:
            True if file should be tracked
        """
        return self.is_extension_tracked(file_path.suffix.lower())


class ConfigurationLoader:
    """Loads configuration from config.json file."""

    GLOBAL_DIR = Path.home() / '.claude' / 'ai-herald'

    DEFAULT_CONFIG = {
        'enabled': True,
        'base_branches': ['main', 'master', 'develop'],
        'tracked_extensions': [
            '.java', '.kt', '.kts', '.scala',
            '.py', '.js', '.ts', '.tsx', '.jsx',
            '.go', '.rs', '.c', '.cpp', '.h', '.hpp',
            '.sql', '.yml', '.yaml', '.json', '.xml',
            '.properties', '.toml', '.sh', '.bash', ".feature"
        ],
        'enable_logging': False,
        'log_file': 'ai-herald.log',
        'format_detection': {
            'enabled': True,
            'commands': [
                'spotlessApply',
                'prettier',
                'ruff',
                'eslint.*--fix',
                'gofmt',
                'rustfmt',
                'clang-format'
            ]
        },
        'mr': {
            'titleUpdateEnabled': False,
            'descriptionUpdateEnabled': False,
            'autoCreationEnabled': False,
            'labelingEnabled': False
        },
        'housekeeping': {
            'enabled': False,
            'staleDaysThreshold': 7,
            'maxFilesPerRun': 5
        },
        'code_generated_patterns': [
            '**/generated/**',
            '**/__generated__/**',
            '**/gen/**',
            '**/*.generated.ts',
            '**/*.generated.js',
            '**/*.generated.java',
            '**/*.pb.go',
            '**/*_pb2.py',
            '**/*_pb2_grpc.py',
            '**/build/generated/**',
            '**/target/generated-sources/**'
        ]
    }

    @staticmethod
    def resolve_plugin_version() -> str:
        """Resolve plugin version from CLAUDE_PLUGIN_ROOT metadata.

        Reads version from ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json.
        Falls back to "dev" when not installed as plugin or on any error.

        Returns:
            Version string (e.g., "0.0.14") or "dev"
        """
        plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT')
        if not plugin_root:
            return 'dev'
        try:
            plugin_json = Path(plugin_root) / '.claude-plugin' / 'plugin.json'
            with open(plugin_json, 'r') as f:
                return json.load(f).get('version', 'dev')
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IOError):
            return 'dev'

    @staticmethod
    def resolve_config_path() -> Path:
        """Resolve global config path, creating directory if needed.

        Returns:
            Path to config.json in global directory
        """
        global_dir = ConfigurationLoader.GLOBAL_DIR
        global_dir.mkdir(parents=True, exist_ok=True)
        return global_dir / 'config.json'

    @staticmethod
    def resolve_log_path(config: Configuration) -> Path:
        """Resolve log file path in global directory.

        Args:
            config: Configuration object with log_file name

        Returns:
            Path to log file in global directory
        """
        return ConfigurationLoader.GLOBAL_DIR / config.log_file

    @staticmethod
    def _merge_defaults(user: dict, defaults: dict) -> tuple:
        """Recursively fill missing keys in user config from defaults.

        Only adds keys absent from user config. Existing values (including
        False, None, [], {}) are never modified.

        Args:
            user: User's config dict (modified in place)
            defaults: Default config dict to fill from

        Returns:
            Tuple of (merged_dict, was_changed) where was_changed indicates
            whether any keys were added.
        """
        changed = False
        for key, default_value in defaults.items():
            if key not in user:
                user[key] = default_value
                changed = True
            elif isinstance(default_value, dict) and isinstance(user[key], dict):
                _, nested_changed = ConfigurationLoader._merge_defaults(user[key], default_value)
                changed = changed or nested_changed
        return user, changed

    @staticmethod
    def load(config_path: Path = None) -> Configuration:
        """Load configuration from file, creating default if missing.

        If the file exists but is missing keys present in DEFAULT_CONFIG,
        those keys are filled with defaults and the file is updated on disk.
        Existing values are never modified.

        Args:
            config_path: Path to config.json. If None, uses global path.

        Returns:
            Configuration object
        """
        if config_path is None:
            config_path = ConfigurationLoader.resolve_config_path()

        # Create default if missing
        if not config_path.exists():
            ConfigurationLoader.create_default(config_path)

        # Load from file
        try:
            with open(config_path, 'r') as f:
                config_dict = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config_dict = ConfigurationLoader.DEFAULT_CONFIG

        # Forward-fill any missing keys from defaults and persist if changed
        config_dict, was_changed = ConfigurationLoader._merge_defaults(
            config_dict, ConfigurationLoader.DEFAULT_CONFIG
        )
        if was_changed:
            try:
                with open(config_path, 'w') as f:
                    json.dump(config_dict, f, indent=2)
            except IOError:
                pass  # Silently fail if can't write

        # Load format detection settings with defaults
        default_format = ConfigurationLoader.DEFAULT_CONFIG['format_detection']
        format_detection = config_dict.get('format_detection', default_format)
        format_enabled = format_detection.get('enabled', default_format['enabled'])
        format_commands = format_detection.get('commands', default_format['commands'])

        # Load MR settings with defaults
        default_mr = ConfigurationLoader.DEFAULT_CONFIG['mr']
        mr_config = config_dict.get('mr', default_mr)
        mr_title_update_enabled = mr_config.get('titleUpdateEnabled', default_mr['titleUpdateEnabled'])
        mr_description_update_enabled = mr_config.get('descriptionUpdateEnabled', default_mr['descriptionUpdateEnabled'])
        mr_auto_creation_enabled = mr_config.get('autoCreationEnabled', default_mr['autoCreationEnabled'])
        mr_labeling_enabled = mr_config.get('labelingEnabled', default_mr['labelingEnabled'])

        # Load housekeeping settings with defaults
        default_housekeeping = ConfigurationLoader.DEFAULT_CONFIG['housekeeping']
        housekeeping_config = config_dict.get('housekeeping', default_housekeeping)
        housekeeping_enabled = housekeeping_config.get('enabled', default_housekeeping['enabled'])
        housekeeping_stale_days = housekeeping_config.get('staleDaysThreshold', default_housekeeping['staleDaysThreshold'])
        housekeeping_max_files = housekeeping_config.get('maxFilesPerRun', default_housekeeping['maxFilesPerRun'])

        default_code_gen_patterns = ConfigurationLoader.DEFAULT_CONFIG['code_generated_patterns']
        code_generated_patterns = set(config_dict.get('code_generated_patterns', default_code_gen_patterns))

        return Configuration(
            enabled=config_dict.get('enabled', ConfigurationLoader.DEFAULT_CONFIG['enabled']),
            base_branches=config_dict.get('base_branches', ConfigurationLoader.DEFAULT_CONFIG['base_branches']),
            tracked_extensions=set(config_dict.get('tracked_extensions', ConfigurationLoader.DEFAULT_CONFIG['tracked_extensions'])),
            enable_logging=config_dict.get('enable_logging', ConfigurationLoader.DEFAULT_CONFIG['enable_logging']),
            log_file=config_dict.get('log_file', ConfigurationLoader.DEFAULT_CONFIG['log_file']),
            format_detection_enabled=format_enabled,
            format_commands=format_commands,
            mr_title_update_enabled=mr_title_update_enabled,
            mr_description_update_enabled=mr_description_update_enabled,
            mr_auto_creation_enabled=mr_auto_creation_enabled,
            mr_labeling_enabled=mr_labeling_enabled,
            housekeeping_enabled=housekeeping_enabled,
            housekeeping_stale_days=housekeeping_stale_days,
            housekeeping_max_files=housekeeping_max_files,
            code_generated_patterns=code_generated_patterns
        )

    @staticmethod
    def create_default(config_path: Path) -> None:
        """Create default config.json file.

        Args:
            config_path: Path where config.json should be created
        """
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(ConfigurationLoader.DEFAULT_CONFIG, f, indent=2)
        except IOError:
            pass  # Silently fail if can't create
