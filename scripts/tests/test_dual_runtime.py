"""Package contracts and version synchronization; no real repository commits."""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ["code-sentinel", "feedback-loop", "permissions-juditor", "plan-guard"]


@pytest.mark.parametrize("name", PLUGINS)
def test_manifests_share_identity_and_skills(name):
    root = ROOT / "plugins" / name
    claude = json.loads((root / ".claude-plugin/plugin.json").read_text())
    codex = json.loads((root / ".codex-plugin/plugin.json").read_text())
    assert claude["name"] == codex["name"] == name
    assert claude["version"] == codex["version"]
    assert (root / codex.get("skills", "skills")).exists() if name != "permissions-juditor" else True
    for skill in (root / "skills").glob("*/SKILL.md"):
        for runtime in ["claude", "codex"]:
            assert f"references/{runtime}.md" in skill.read_text()
            assert (skill.parent / "references" / f"{runtime}.md").is_file()


@pytest.mark.parametrize("name", PLUGINS[1:])
def test_shared_runtime_is_packaged_identically(name):
    assert (ROOT / "common/agent_runtime.py").read_bytes() == (ROOT / "plugins" / name / "hooks" / name / "agent_runtime.py").read_bytes()


def test_codex_default_hook_events_are_supported():
    supported = {"PreToolUse", "PermissionRequest", "PostToolUse", "UserPromptSubmit", "Stop", "SessionStart", "SessionEnd", "PreCompact", "PostCompact", "SubagentStart", "SubagentStop", "Interrupt"}
    for name in PLUGINS[1:]:
        plugin = ROOT / "plugins" / name
        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text())
        config = json.loads((plugin / manifest.get("hooks", "hooks/hooks.json")).read_text())
        assert set(config["hooks"]) <= supported


def test_feedback_platform_hooks_are_complete_and_separate():
    root = ROOT / "plugins/feedback-loop"
    assert not (root / "hooks/hooks.json").exists()
    expected = {"claude": {"UserPromptSubmit", "PreToolUse", "PostToolUseFailure"},
                "codex": {"UserPromptSubmit", "PreToolUse", "PostToolUse"}}
    detector = {"UserPromptSubmit": "prompt", "PreToolUse": "tool", "PostToolUse": "fail", "PostToolUseFailure": "fail"}
    for runtime, events in expected.items():
        manifest = json.loads((root / f".{runtime}-plugin/plugin.json").read_text())
        assert manifest["hooks"] == f"./hooks/{runtime}.json"
        config = json.loads((root / manifest["hooks"]).read_text())
        assert set(config["hooks"]) == events
        variable = "CLAUDE_PLUGIN_ROOT" if runtime == "claude" else "PLUGIN_ROOT"
        for event, groups in config["hooks"].items():
            assert len(groups) == 1 and len(groups[0]["hooks"]) == 1
            command = groups[0]["hooks"][0]["command"]
            assert "${" + variable + "}" in command
            assert command.endswith(f"/{detector[event]}-detector.py\"")
            assert (root / "hooks/feedback-loop" / (detector[event] + "-detector.py")).is_file()


def test_commit_helper_syncs_both_versions(tmp_path):
    def run(*args):
        return subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=True)
    run("git", "init", "-q")
    plugin = tmp_path / "plugins/example"
    for host in ["claude", "codex"]:
        directory = plugin / f".{host}-plugin"
        directory.mkdir(parents=True)
        (directory / "plugin.json").write_text(json.dumps({"name": "example", "version": "1.2.3"}))
    market = tmp_path / ".claude-plugin/marketplace.json"
    market.parent.mkdir()
    market.write_text(json.dumps({"name": "example-market", "version": "1.0.0", "plugins": [{"name": "example", "version": "1.2.3"}]}))
    run("git", "add", ".")
    run("bash", str(ROOT / "scripts/bump-plugin-versions.sh"), "--dry-run")
    assert json.loads((plugin / ".codex-plugin/plugin.json").read_text())["version"] == "1.2.3"
    run("bash", str(ROOT / "scripts/bump-plugin-versions.sh"))
    for host in ["claude", "codex"]:
        assert json.loads((plugin / f".{host}-plugin/plugin.json").read_text())["version"] == "1.2.4"
    assert json.loads(market.read_text())["plugins"][0]["version"] == "1.2.4"


@pytest.mark.parametrize("name", PLUGINS[1:])
def test_all_hook_plugins_have_explicit_platform_configs(name):
    root = ROOT / "plugins" / name
    assert not (root / "hooks/hooks.json").exists()
    for runtime, variable in [("claude", "CLAUDE_PLUGIN_ROOT"), ("codex", "PLUGIN_ROOT")]:
        manifest = json.loads((root / f".{runtime}-plugin/plugin.json").read_text())
        assert manifest["hooks"] == f"./hooks/{runtime}.json"
        config = json.loads((root / manifest["hooks"]).read_text())
        for groups in config["hooks"].values():
            for group in groups:
                for handler in group["hooks"]:
                    assert "${" + variable + "}" in handler["command"]
                    assert ".sh" not in handler["command"]
                    assert "python3 " in handler["command"]
