#!/usr/bin/env python3
"""UserPromptSubmit hook — scores incoming prompt quality when in plan mode.

Disabled by default (costs an extra model call per prompt); set
PLAN_GUARD_PROMPT_SCORER_ENABLED=1 to opt in.
"""

import json
import os
import sys

from anthropic_client import AnthropicClient

PROMPT_TEMPLATE = """\
You are an expert prompt engineer with deep experience evaluating prompt quality for AI-assisted \
software planning. A software engineer has just submitted a prompt to enter plan mode, where an AI \
will produce a detailed implementation plan.

Your task: score the prompt and identify its weakest points.

Think through each principle before scoring (reason first, then conclude):

Evaluate the prompt against these 6 principles of effective prompting:
1. Context — Does it state what is wanted, why, and who the author is (background, expertise, use)?
2. Examples — Does it provide example outputs or diverse cases to guide the response (few-shot)?
3. Constraints — Does it define format, length, language, tone, or style explicitly?
4. Steps — For complex tasks, does it break the work into explicit steps (chain-of-thought)?
5. Think-first — Does it ask the AI to reason before acting for more thorough responses?
6. Role — Does it define the AI's persona, expertise level, or communication style?

Output format (strict — no preamble, no extra text  ):
Score: <N>/100
<One sentence on the most impactful missing principle>. <One sentence on the second most impactful missing principle or how to improve the weakest area>.

PROMPT TO EVALUATE:
{prompt}
"""


def score_prompt(client: AnthropicClient, prompt_text: str) -> str:
    """Evaluate the prompt with a higher-tier model for nuanced judgment."""
    # ANTHROPIC_MODEL is a CLI alias ("opus"), not a real model id — resolve a concrete one.
    model = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")
    return client.complete(
        model=model,
        prompt=PROMPT_TEMPLATE.format(prompt=prompt_text),
        max_tokens=400,
        # Explicit rather than relying on the client's own default, so this
        # hook's behavior is visible here rather than inherited silently.
        effort="medium",
    )


def parse_response(raw: str) -> tuple[str, str]:
    """Return (score_label, feedback) from Claude's response."""
    lines = raw.strip().splitlines()
    score_label = "?/100"
    feedback_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("score:"):
            score_label = stripped.split(":", 1)[1].strip()
        elif stripped:
            feedback_lines.append(stripped)

    feedback = " ".join(feedback_lines)
    return score_label, feedback


def scorer_enabled() -> bool:
    """Opt-in: every prompt scored costs an extra model call, so default off."""
    return os.environ.get("PLAN_GUARD_PROMPT_SCORER_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    if not scorer_enabled():
        print("{}")
        return

    if not AnthropicClient.has_credentials():
        print(json.dumps({"systemMessage": "[prompt-scorer] No credentials detected, skipping"}))
        return

    hook_input = json.load(sys.stdin)

    if hook_input.get("permission_mode") != "plan":
        print("{}")
        return

    prompt_text = hook_input.get("prompt", "").strip()
    if not prompt_text:
        print("{}")
        return

    try:
        raw = score_prompt(AnthropicClient.from_env(), prompt_text)
        score_label, feedback = parse_response(raw)
        system_message = f"[prompt-scorer] Score: {score_label} — {feedback}"
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"systemMessage": f"[prompt-scorer] error: {e}"}))
        return

    print(json.dumps({"systemMessage": system_message}))


if __name__ == "__main__":
    main()
