# Claude Code Marketplace

Personal marketplace for Claude Code plugins.

## Structure

```
marketplace/
├── .claude-plugin/
│   └── marketplace.json   # Plugin registry
├── README.md              # This file
├── CONTRIBUTING.md        # Submission guidelines
├── LICENSE                # MIT license
└── plugins/
    ├── ai-herald/
    ├── claude-code-guide/
    ├── code-sentinel/
    ├── feedback-loop/
    ├── plan-guard/
    └── task-seeder/
```

## Available Plugins

### ai-herald

Watches every AI write, then announces attribution stats at commit time.

**Features:**
- Tracks AI-authored lines via Claude Code hooks
- Appends contribution stats to commit messages
- GitLab MR integration (title updates, auto-creation)
- Format attribution preservation (spotlessApply, prettier, black, etc.)
- Git diff-based tracking (only branch changes)
- Automatic housekeeping for stale tracking files

**[Full Documentation →](plugins/ai-herald/README.md)**

---

### claude-code-guide

Enforces use of official Claude Code docs before answering any questions about Claude Code settings, features, or behavior.

**Skills:** `claude-code-docs`

**[Full Documentation →](plugins/claude-code-guide/README.md)**

---

### feedback-loop

Monitors tool usage, prompts, and failures, then helps refine permissions, rules, and memory files based on real usage data.

**Skills:** `tool-permission-refiner`, `tool-rules-refiner`, `memory-refiner`

**Hooks:** `tool-detector` (PreToolUse), `prompt-detector` (UserPromptSubmit), `fail-detector` (PostToolUseFailure)

**Data directory:** `~/.claude/feedback-loop/` — `tool-detector-YYYY-MM.jsonl`, `prompt-detector-YYYY-Www.jsonl`, `fails.jsonl`

**[Full Documentation →](plugins/feedback-loop/README.md)**

---

### plan-guard

Enforces plan mode discipline, syncs plan files to project directories, and cleans up old plan files.

**Skills:** `cleanup-plans`

**Hooks:** `plan-mode-enforcer` (UserPromptSubmit), `copy-plan-on-change` + `copy-plan-on-exit` (PostToolUse)

**[Full Documentation →](plugins/plan-guard/README.md)**

---

### code-sentinel

Expert code review with layer-by-layer flow diagrams, model diff trees, and interactive GitLab MR comment resolution.

**Skills:** `code-review`, `mr-nitpick-sentinel`

**[Full Documentation →](plugins/code-sentinel/README.md)**

---

### task-seeder

Reminds the agent that a prompt covering more than one thing — especially anything needing exploration/research first — may be worth splitting into a `Task N: ...` breakdown via `TaskCreate`. Purely static (no model call, no heuristic gating); stays completely silent in plan mode, owned by `plan-guard`.

**Hooks:** `task-breakdown-drafter` (UserPromptSubmit)

**[Full Documentation →](plugins/task-seeder/README.md)**

## For Users

### Adding This Marketplace

```bash
claude plugin marketplace add https://github.com/EugeneMsv/claude-marketplace.git
```

### Installing Plugins

```bash
# Install ai-herald
claude plugin install ai-herald@eug-msv-claude-marketplace
```

## For Contributors

### Adding a Plugin

1. Create your plugin in `plugins/your-plugin-name/`
2. Add plugin manifest at `plugins/your-plugin-name/.claude-plugin/plugin.json`
3. Add entry to `.claude-plugin/marketplace.json`:

```json
{
  "name": "your-plugin",
  "source": "./plugins/your-plugin-name",
  "description": "Brief description",
  "version": "0.0.1",
  "author": {
    "name": "Your Name"
  },
  "category": "development",
  "tags": ["tag1", "tag2"]
}
```

4. Test locally
5. Submit pull request

## License

MIT
