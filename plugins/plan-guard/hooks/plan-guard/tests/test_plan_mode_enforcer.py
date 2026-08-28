"""Tests for plan-mode-enforcer.py hook."""

import importlib.util
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))


def _load_hook_module():
    """Load plan-mode-enforcer.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / "plan-mode-enforcer.py"
    spec = importlib.util.spec_from_file_location("plan_mode_enforcer", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enforcer = _load_hook_module()


class _StubClient:
    """Fake AnthropicClient instance recording the kwargs complete() was called with."""

    def __init__(self, response_text=""):
        self.response_text = response_text
        self.received = None

    def complete(self, model, prompt, max_tokens, effort=None):
        self.received = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "effort": effort}
        return self.response_text


def test_buildRequirementsMessage_passesMediumEffort():
    """This is a "cheap classification-tier model" call per its own docstring -
    medium matches that intent instead of silently inheriting the API's "high"
    default."""
    stub_client = _StubClient()

    enforcer.build_requirements_message(stub_client, "some project context")

    assert stub_client.received["effort"] == "medium"


def test_buildRequirementsMessage_includesContextInPrompt():
    stub_client = _StubClient()

    enforcer.build_requirements_message(stub_client, "some project context")

    assert "some project context" in stub_client.received["prompt"]
