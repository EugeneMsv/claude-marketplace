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
└── plugins/               # Plugin directory
    └── ai-contribution-tracker/
```

## Available Plugins

### ai-contribution-tracker

Automatically tracks AI vs human contributions in your codebase.

**Features:**
- Tracks AI-authored lines via Claude Code hooks
- Appends contribution stats to commit messages
- GitLab MR integration (title updates, auto-creation)
- Format attribution preservation (spotlessApply, prettier, black, etc.)
- Git diff-based tracking (only branch changes)
- Automatic housekeeping for stale tracking files

**[Full Documentation →](plugins/ai-contribution-tracker/README.md)**

## For Users

### Adding This Marketplace

```bash
claude plugin marketplace add https://github.com/EugeneMsv/claude-marketplace.git
```

### Installing Plugins

```bash
# Install ai-contribution-tracker
claude plugin install ai-contribution-tracker@eug-msv-claude-marketplace
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
