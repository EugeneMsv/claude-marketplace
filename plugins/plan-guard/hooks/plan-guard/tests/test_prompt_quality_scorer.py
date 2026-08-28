"""Tests for prompt-quality-scorer.py hook."""

import importlib.util
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(HOOK_DIR))


def _load_hook_module():
    """Load prompt-quality-scorer.py via importlib (hyphen in name)."""
    hook_path = HOOK_DIR / "prompt-quality-scorer.py"
    spec = importlib.util.spec_from_file_location("prompt_quality_scorer", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scorer = _load_hook_module()


class _StubClient:
    """Fake AnthropicClient instance recording the kwargs complete() was called with."""

    def __init__(self, response_text=""):
        self.response_text = response_text
        self.received = None

    def complete(self, model, prompt, max_tokens, effort=None):
        self.received = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "effort": effort}
        return self.response_text


def test_scorePrompt_passesMediumEffort():
    """Explicit rather than inherited from the client's own default, so this
    hook's cost/latency behavior is visible at the call site."""
    stub_client = _StubClient()

    scorer.score_prompt(stub_client, "add a login form")

    assert stub_client.received["effort"] == "medium"


def test_scorePrompt_includesPromptTextInSentToModel():
    stub_client = _StubClient()

    scorer.score_prompt(stub_client, "add a login form")

    assert "add a login form" in stub_client.received["prompt"]
