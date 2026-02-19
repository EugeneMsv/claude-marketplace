"""Tests for Configuration MR title update settings."""

import json
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.configuration import Configuration, ConfigurationLoader


class TestConfigurationMrTitleUpdate:
    """Tests for mr_title_update_enabled property."""

    def test_mr_title_update_enabled_default_is_false(self):
        """Given no mr config, mr_title_update_enabled defaults to False."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
        )
        assert config.mr_title_update_enabled is False

    def test_mr_title_update_enabled_when_set_true(self):
        """Given mr_title_update_enabled=True, property returns True."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
            mr_title_update_enabled=True,
        )
        assert config.mr_title_update_enabled is True


class TestConfigurationLoaderMr:
    """Tests for ConfigurationLoader loading MR settings."""

    def test_load_with_mr_section_enabled(self, tmp_path):
        """Given config with mr.titleUpdateEnabled=true, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"titleUpdateEnabled": True},
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_title_update_enabled is True

    def test_load_with_mr_section_disabled(self, tmp_path):
        """Given config with mr.titleUpdateEnabled=false, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"titleUpdateEnabled": False},
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_title_update_enabled is False

    def test_load_without_mr_section_defaults_to_false(self, tmp_path):
        """Given config without mr section, defaults to False."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_title_update_enabled is False

    def test_default_config_has_mr_section(self):
        """DEFAULT_CONFIG includes mr.titleUpdateEnabled=False."""
        assert 'mr' in ConfigurationLoader.DEFAULT_CONFIG
        assert ConfigurationLoader.DEFAULT_CONFIG['mr']['titleUpdateEnabled'] is False


class TestConfigurationMrDescriptionUpdate:
    """Tests for mr_description_update_enabled property."""

    def test_mr_description_update_enabled_default_is_false(self):
        """Given no mr config, mr_description_update_enabled defaults to False."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
        )
        assert config.mr_description_update_enabled is False

    def test_mr_description_update_enabled_when_set_true(self):
        """Given mr_description_update_enabled=True, property returns True."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
            mr_description_update_enabled=True,
        )
        assert config.mr_description_update_enabled is True


class TestConfigurationLoaderMrDescriptionUpdate:
    """Tests for ConfigurationLoader loading mr.descriptionUpdateEnabled."""

    @pytest.mark.parametrize("value,expected", [
        (True, True),
        (False, False),
    ])
    def test_load_with_description_update_field(self, tmp_path, value, expected):
        """Given config with mr.descriptionUpdateEnabled, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"descriptionUpdateEnabled": value},
        }))
        config = ConfigurationLoader.load(config_file)
        assert config.mr_description_update_enabled is expected

    def test_load_without_description_update_defaults_to_false(self, tmp_path):
        """Given config without descriptionUpdateEnabled field, defaults to False."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"titleUpdateEnabled": True},
        }))
        config = ConfigurationLoader.load(config_file)
        assert config.mr_description_update_enabled is False

    def test_default_config_has_description_update_field(self):
        """DEFAULT_CONFIG includes mr.descriptionUpdateEnabled=False."""
        assert ConfigurationLoader.DEFAULT_CONFIG['mr']['descriptionUpdateEnabled'] is False


class TestConfigurationMrAutoCreation:
    """Tests for mr_auto_creation_enabled property."""

    def test_mr_auto_creation_enabled_default_is_false(self):
        """Given no mr config, mr_auto_creation_enabled defaults to False."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
        )
        assert config.mr_auto_creation_enabled is False

    def test_mr_auto_creation_enabled_when_set_true(self):
        """Given mr_auto_creation_enabled=True, property returns True."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
            mr_auto_creation_enabled=True,
        )
        assert config.mr_auto_creation_enabled is True


class TestConfigurationLoaderMrAutoCreation:
    """Tests for ConfigurationLoader loading MR auto-creation settings."""

    def test_load_with_auto_creation_enabled(self, tmp_path):
        """Given config with mr.autoCreationEnabled=true, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"autoCreationEnabled": True},
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_auto_creation_enabled is True

    def test_load_with_auto_creation_disabled(self, tmp_path):
        """Given config with mr.autoCreationEnabled=false, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"autoCreationEnabled": False},
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_auto_creation_enabled is False

    def test_load_without_auto_creation_defaults_to_false(self, tmp_path):
        """Given config without autoCreationEnabled field, defaults to False."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"titleUpdateEnabled": True},
        }))

        config = ConfigurationLoader.load(config_file)
        assert config.mr_auto_creation_enabled is False

    def test_default_config_has_auto_creation_field(self):
        """DEFAULT_CONFIG includes mr.autoCreationEnabled=False."""
        assert 'mr' in ConfigurationLoader.DEFAULT_CONFIG
        assert ConfigurationLoader.DEFAULT_CONFIG['mr']['autoCreationEnabled'] is False


class TestConfigurationMrLabeling:
    """Tests for mr_labeling_enabled property."""

    @pytest.mark.parametrize("value,expected", [
        (True, True),
        (False, False),
    ])
    def test_mr_labeling_enabled_reflects_init_value(self, value, expected):
        """Given mr_labeling_enabled set to value, property returns expected."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
            mr_labeling_enabled=value,
        )
        assert config.mr_labeling_enabled is expected

    def test_mr_labeling_enabled_default_is_false(self):
        """Given no mr_labeling_enabled arg, defaults to False."""
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=False,
            log_file="test.log",
        )
        assert config.mr_labeling_enabled is False


class TestConfigurationLoaderMrLabeling:
    """Tests for ConfigurationLoader loading mr.labelingEnabled."""

    @pytest.mark.parametrize("labeling_value,expected", [
        (True, True),
        (False, False),
    ])
    def test_load_with_labeling_enabled_field(self, tmp_path, labeling_value, expected):
        """Given config with mr.labelingEnabled, loads correctly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"labelingEnabled": labeling_value},
        }))
        config = ConfigurationLoader.load(config_file)
        assert config.mr_labeling_enabled is expected

    def test_load_without_labeling_field_defaults_to_false(self, tmp_path):
        """Given config without labelingEnabled field, defaults to False."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".py"],
            "enable_logging": False,
            "log_file": "test.log",
            "mr": {"titleUpdateEnabled": True},
        }))
        config = ConfigurationLoader.load(config_file)
        assert config.mr_labeling_enabled is False

    def test_default_config_has_labeling_field(self):
        """DEFAULT_CONFIG includes mr.labelingEnabled=False."""
        assert ConfigurationLoader.DEFAULT_CONFIG['mr']['labelingEnabled'] is False


class TestConfigResolveConfigPath:
    """Tests for ConfigurationLoader.resolve_config_path()."""

    def test_resolve_config_path_returns_global_path(self, tmp_path, monkeypatch):
        """Given GLOBAL_DIR set, resolve_config_path returns config.json in that dir."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        result = ConfigurationLoader.resolve_config_path()
        assert result == tmp_path / 'config.json'

    def test_resolve_config_path_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """Given non-existent GLOBAL_DIR, resolve_config_path creates it."""
        new_dir = tmp_path / 'non-existent' / 'nested'
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', new_dir)
        ConfigurationLoader.resolve_config_path()
        assert new_dir.exists()

    def test_resolve_config_path_idempotent_when_dir_exists(self, tmp_path, monkeypatch):
        """Given existing GLOBAL_DIR, resolve_config_path succeeds without error."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        result1 = ConfigurationLoader.resolve_config_path()
        result2 = ConfigurationLoader.resolve_config_path()
        assert result1 == result2


class TestConfigResolveLogPath:
    """Tests for ConfigurationLoader.resolve_log_path()."""

    def test_resolve_log_path_returns_path_in_global_dir(self, tmp_path, monkeypatch):
        """Given config with log_file, resolve_log_path returns it in GLOBAL_DIR."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=True,
            log_file="ai-tracker.log",
        )
        result = ConfigurationLoader.resolve_log_path(config)
        assert result == tmp_path / 'ai-tracker.log'

    def test_resolve_log_path_with_custom_log_file_name(self, tmp_path, monkeypatch):
        """Given config with custom log_file, resolve_log_path uses that name."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        config = Configuration(
            enabled=True,
            base_branches=["main"],
            tracked_extensions={".py"},
            enable_logging=True,
            log_file="custom.log",
        )
        result = ConfigurationLoader.resolve_log_path(config)
        assert result == tmp_path / 'custom.log'


class TestConfigLoadGlobalResolution:
    """Tests for ConfigurationLoader.load() with global resolution."""

    def test_load_without_args_uses_global_path(self, tmp_path, monkeypatch):
        """Given no args, load() uses resolve_config_path and creates default."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        config = ConfigurationLoader.load()
        assert config.enabled is True
        assert (tmp_path / 'config.json').exists()

    def test_load_with_explicit_path_ignores_global(self, tmp_path, monkeypatch):
        """Given explicit config_path, load() uses it instead of global."""
        global_dir = tmp_path / 'global'
        global_dir.mkdir()
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', global_dir)

        local_config = tmp_path / 'local' / 'config.json'
        local_config.parent.mkdir()
        local_config.write_text(json.dumps({
            "enabled": False,
            "base_branches": ["develop"],
            "tracked_extensions": [".kt"],
            "enable_logging": False,
            "log_file": "test.log",
        }))

        config = ConfigurationLoader.load(local_config)
        assert config.enabled is False
        assert config.base_branches == ["develop"]

    def test_load_without_args_reads_existing_global_config(self, tmp_path, monkeypatch):
        """Given existing global config, load() reads it correctly."""
        monkeypatch.setattr(ConfigurationLoader, 'GLOBAL_DIR', tmp_path)
        config_file = tmp_path / 'config.json'
        config_file.write_text(json.dumps({
            "enabled": True,
            "base_branches": ["main"],
            "tracked_extensions": [".java"],
            "enable_logging": True,
            "log_file": "custom.log",
            "mr": {"titleUpdateEnabled": True},
        }))

        config = ConfigurationLoader.load()
        assert config.mr_title_update_enabled is True
        assert config.enable_logging is True
        assert ".java" in config.tracked_extensions


class TestResolvePluginVersion:
    """Tests for ConfigurationLoader.resolve_plugin_version()."""

    def test_returns_version_from_plugin_json(self, tmp_path, monkeypatch):
        """Given CLAUDE_PLUGIN_ROOT with valid plugin.json, returns version."""
        plugin_dir = tmp_path / '.claude-plugin'
        plugin_dir.mkdir()
        (plugin_dir / 'plugin.json').write_text(json.dumps({
            "name": "test-plugin",
            "version": "1.2.3",
        }))
        monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))

        assert ConfigurationLoader.resolve_plugin_version() == "1.2.3"

    def test_returns_dev_when_env_not_set(self, monkeypatch):
        """Given no CLAUDE_PLUGIN_ROOT env var, returns 'dev'."""
        monkeypatch.delenv('CLAUDE_PLUGIN_ROOT', raising=False)
        assert ConfigurationLoader.resolve_plugin_version() == "dev"

    def test_returns_dev_when_plugin_json_missing(self, tmp_path, monkeypatch):
        """Given CLAUDE_PLUGIN_ROOT without plugin.json, returns 'dev'."""
        monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))
        assert ConfigurationLoader.resolve_plugin_version() == "dev"

    def test_returns_dev_when_plugin_json_malformed(self, tmp_path, monkeypatch):
        """Given CLAUDE_PLUGIN_ROOT with invalid JSON, returns 'dev'."""
        plugin_dir = tmp_path / '.claude-plugin'
        plugin_dir.mkdir()
        (plugin_dir / 'plugin.json').write_text("not json")
        monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))

        assert ConfigurationLoader.resolve_plugin_version() == "dev"

    def test_returns_dev_when_version_field_missing(self, tmp_path, monkeypatch):
        """Given plugin.json without version field, returns 'dev'."""
        plugin_dir = tmp_path / '.claude-plugin'
        plugin_dir.mkdir()
        (plugin_dir / 'plugin.json').write_text(json.dumps({
            "name": "test-plugin",
        }))
        monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))

        assert ConfigurationLoader.resolve_plugin_version() == "dev"
