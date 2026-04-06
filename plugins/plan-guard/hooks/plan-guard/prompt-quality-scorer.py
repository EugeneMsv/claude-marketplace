#!/usr/bin/env python3
"""UserPromptSubmit hook — scores incoming prompt quality when in plan mode."""

import json
import os
import sys

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

Output format (strict — no preamble, no extra text):
Score: <N>/100
<One sentence on the most impactful missing principle>. <One sentence on the second most impactful missing principle or how to improve the weakest area>.

PROMPT TO EVALUATE:
{prompt}
"""


def call_anthropic(prompt_text: str) -> str:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    response = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(prompt=prompt_text)}],
    )
    block = response.content[0]
    if not hasattr(block, "text"):
        return ""
    return block.text.strip()  # type: ignore[union-attr]


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


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(json.dumps({"systemMessage": "[prompt-scorer] No API key detected, skipping"}))
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
        raw = call_anthropic(prompt_text)
        score_label, feedback = parse_response(raw)
        system_message = f"[prompt-scorer] Score: {score_label} — {feedback}"
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"systemMessage": f"[prompt-scorer] error: {e}"}))
        return

    print(json.dumps({"systemMessage": system_message}))


if __name__ == "__main__":
    main()
