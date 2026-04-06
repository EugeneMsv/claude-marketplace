---
name: claude-code-docs
description: >
  This skill should be used when the user asks about Claude Code settings, Claude Code features,
  Claude Code configuration, or Claude Code behavior — including questions like "how to enable X
  in Claude Code", "what is the setting for X", "does Claude Code support X", "why doesn't X
  work in Claude Code", or reports a Claude Code bug. MUST be triggered before answering any
  Claude Code docs or settings question. Do NOT trigger for general coding or non-Claude-Code topics.
fork: true
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch
---

# Claude Code Documentation Guide

Answer Claude Code questions exclusively from official sources. Never rely on training
knowledge alone — Claude Code evolves rapidly and docs are the ground truth.

## Mandatory Research Protocol

Before answering any Claude Code question, fetch at least one official source. Follow this
priority order:

### 1. Official Docs (primary source)

Fetch the most relevant docs page first:

```
https://code.claude.com/docs/en/
```

Key sections:
- `/settings` — settings.json keys, user vs project config, env vars
- `/hooks` — hook events, schema, examples
- `/mcp` — MCP server setup and configuration
- `/slash-commands` — built-in and custom commands
- `/ide-integrations` — VS Code, JetBrains setup
- `/permissions` — allow/deny/ask permission system
- `/plugins` — plugin architecture, skills, agents
- `/keybindings` — keyboard shortcuts and customization
- `/cli` — CLI flags and invocation

Construct the URL as: `https://code.claude.com/docs/en/<section>`

### 2. CHANGELOG (for version-specific questions)

When the question may be version-dependent:

```
https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
```

Use to confirm when a feature was introduced, find the exact setting key name, or verify if a bug was fixed.

### 3. GitHub Issues (for bugs and known problems)

When the user reports something not working:

```
https://github.com/anthropics/claude-code/issues
```

Append `?q=<keywords>` to filter. Use to find existing bug reports, workarounds, or feature requests.

## Answer Format

1. Fetch the relevant docs URL first via WebFetch
2. Cite the source URL in the answer
3. Use exact setting keys and values from docs — never paraphrase from memory
4. If not found in docs: check CHANGELOG, then GitHub issues, then explicitly state what could not be verified

## Handling "Doesn't Work" Reports

1. Fetch docs for the setting to confirm the exact key name and expected behavior
2. Check CHANGELOG for recent changes to that feature
3. Search GitHub issues for the symptom
4. Present findings with links — do not guess

## Critical Rule

Do NOT answer Claude Code settings or feature questions from training memory. Key names,
config locations, and feature availability change between releases. Always fetch first.
