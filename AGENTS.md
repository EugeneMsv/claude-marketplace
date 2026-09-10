# Repository maintenance

This repository distributes reusable agent plugins. Maintain the plugin source here; installed plugin caches are disposable deployment outputs, not the source of truth.

## Keep public content generic

Nothing added to code, tests, documentation, fixtures, examples, or comments may include a specific employer, internal system/project, or an individual's real name, username, email, or personal filesystem path. Use neutral placeholders. Product/runtime names needed to explain supported integrations are appropriate; private deployment details are not.

Before adding an example, check that it makes sense in an unrelated organization. Never copy personal settings, credentials, environment policies, or session logs into a published plugin.

## What is unique about this repository

- A plugin can support both Claude Code and Codex from the **same source directory**. Two manifests describe packaging; they do not justify two copies of the implementation.
- The migrated plugins are `code-sentinel`, `feedback-loop`, `permissions-juditor`, and `plan-guard`. Other plugins may still be Claude-only; do not assume repository-wide parity.
- Runtime integration differs even where capabilities look similar. Preserve each host's event semantics, permission model, storage paths, and tool availability.
- Installed plugins contain only their own subtree. They cannot import `../../common` or another plugin from this repository at runtime.

## Structure and ownership

| Location | Purpose |
|---|---|
| `.claude-plugin/marketplace.json` | Existing marketplace catalog and release metadata |
| `plugins/<name>/.claude-plugin/plugin.json` | Claude manifest |
| `plugins/<name>/.codex-plugin/plugin.json` | Codex manifest, where supported |
| `plugins/<name>/skills/<skill>/SKILL.md` | Shared skill entry point and common workflow |
| `references/claude.md`, `references/codex.md` beside a skill | Host-specific instructions, loaded only when needed |
| `plugins/<name>/hooks/claude.json`, `hooks/codex.json` | Complete per-host hook configurations |
| `plugins/<name>/hooks/<name>/` | Focused Python hook entry points and shared helpers |
| `common/` | Canonical shared Python modules and runtime documentation |
| `scripts/` | Repository maintenance/versioning tools and their tests |
| `.Codex/<skill-or-task>/` | Ignored temporary plans, reports, validation environments, and test artifacts |

Keep temporary artifacts out of commits and out of `.Codex/` root. See `common/README.md` for the runtime contract.

## Dual-runtime design rules

### Scripts and hooks

- Use `AGENT_RUNTIME=claude|codex` for explicit runtime selection. Otherwise `PLUGIN_ROOT` identifies Codex; absent that, default to Claude. Reject invalid explicit values.
- Do not detect Codex from `CLAUDE_PLUGIN_ROOT`: Codex also provides it for compatibility. Runtime selection does not select the model/API provider.
- Each hook-bearing migrated plugin has one complete JSON per runtime, explicitly selected by its manifest. Do not leave a default `hooks/hooks.json` beside these files: avoid implicit merging and duplicate execution.
- Use the platform's root variable in its JSON: `CLAUDE_PLUGIN_ROOT` for Claude, `PLUGIN_ROOT` for Codex. Quote paths.
- Invoke Python entry points directly. Do not add shell wrappers that merely forward to Python.
- Keep entry points focused by responsibility, such as fail/prompt/tool detection or plan synchronization. Give reusable modules descriptive names. A module containing handler execution should be named as a runner, not only as logging I/O.
- Share runtime detection, persistence, and other common behavior. Add runtime branches/adapters only for actual differences.
- Honor `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, and, for Codex plugin data, `PLUGIN_DATA` as implemented by `agent_runtime.py`. Never write state into an installed plugin cache.
- Installing a plugin must not silently change global permissions, replace reviewer policy, or trust its own hooks.

### Skills and documentation

- Keep common reasoning and workflow in SKILL.md. Add two references only where the hosts differ; load exactly the current host's reference.
- Use actual available tools. Do not tell Codex to call Claude-only task/planning tools, or assume either host exposes every tool named in an example.
- Keep native configuration formats separate: Claude settings JSON is not Codex TOML or executable shell rules.
- Treat AGENTS.md guidance as behavioral instructions, not enforced permissions. Do not edit internal memory databases as a substitute for supported memory/instruction configuration.
- Update the plugin README, affected references, and troubleshooting instructions whenever entry points, paths, events, or behavior change. Remove stale shell examples after a Python conversion.

### Differences that must remain explicit

- **Code Sentinel:** skills-only; no hook runner/configuration is needed.
- **Feedback Loop:** Claude failures use PostToolUseFailure; Codex failures are inspected from PostToolUse results. Three Python detectors share hook_runner.py and agent_runtime.py. Prompts and commands can contain private content; keep logs local and respect configured logging controls.
- **Permissions Juditor:** both hosts run the same custom Anthropic classifier and read Claude settings.json for prompt rules/autoMode prose. Keep this policy source independent of runtime selection until explicitly asked to split it. Runtime adapters only map hook responses and log paths. Codex ask returns no override and resumes its configured approval flow.
- **Plan Guard:** Claude synchronizes global plan files and associated project copies. Codex saves explicit update_plan snapshots; do not claim to capture all narrative plans. Cleanup archives recoverably and never overwrites a plan. The optional prompt scorer still uses Anthropic when enabled in either host.
- Current Python adapters require Python 3.11+; locking uses Unix/macOS fcntl. Do not claim Windows compatibility without implementation and tests.

## Shared modules

Edit canonical files under `common/`, then synchronize their existing vendored copies. The synchronization script only updates plugins that already contain a copy; add a copy explicitly when introducing a new consumer.

Preview with `bash scripts/sync-shared-files.sh --dry-run`. A real run writes **and stages** changed copies, so do not run it when staging is not authorized. Verify packaged copies are byte-identical to the canonical source. Never solve import errors with runtime imports outside the plugin subtree.

## Work and release sequence

1. Inspect git status, staged changes, the current branch, and affected files. Preserve unrelated and user-staged changes.
2. Use a feature branch for implementation. When asked to checkpoint existing work first, finish that separately before migration edits.
3. Implement plugins one at a time; add affected tests during each change. Keep all migration changes uncommitted until the complete requested scope is in place and checks pass.
4. Review the complete diff, including new files, removed entry points, and documentation. Validate both hosts and distinguish fixture tests from live host acceptance.
5. Commit/push only when authorized. A request to review or discuss changes is not permission to commit, install, or publish.
6. After an authorized install/update, verify loading in a fresh host session. Codex hook trust is a separate user decision; do not bypass it.

### Versioning

`scripts/bump-plugin-versions.sh` examines staged plugin changes, bumps the Claude manifest, synchronizes the Codex manifest when present, updates catalog entries, and bumps marketplace metadata. It writes **and stages** files. Preview with `bash scripts/bump-plugin-versions.sh --dry-run` after intentional staging.

The local pre-commit hook currently invokes this script; `.git/hooks` is not versioned, so verify wiring on a fresh clone rather than assuming it exists. Maintenance scripts require Git, jq, Python, and a Bash version supporting `mapfile` (Bash 4+). Do not manually double-bump versions when the hook will do it. Inspect the final commit to confirm both manifests and the catalog agree.

## Verification

Use an isolated Python environment with pytest, PyYAML for the Codex metadata/skill validators, and bashlex when testing the optional classifier parser. Keep the environment under `.Codex/` and do not add dependencies to published plugin source just for tests.

Run the combined migrated-plugin suite from the repository root:

```bash
python3 -m pytest -q -p no:cacheprovider --basetemp .Codex/validation/tests plugins/feedback-loop/hooks/feedback-loop/tests plugins/permissions-juditor/hooks/permissions-juditor/tests plugins/plan-guard/hooks/plan-guard/tests scripts/tests/test_dual_runtime.py
```

Also run `git diff --check`, validate affected Claude manifests with `claude plugin validate plugins/<name>`, and use the available Codex manifest/skill validators. Some bundled Codex validators predate explicit manifest hook paths; verify the current host contract and test those paths separately rather than removing supported functionality just to satisfy a stale validator.

Tests must:
- Isolate configuration, plugin data, logs, and plan directories from real user state.
- Set `GIT_CEILING_DIRECTORIES` for temporary projects inside this repository so Git cannot resolve them to the parent marketplace. Use explicitly initialized test repositories when testing Git-root behavior.
- Never contact live model APIs, production services, or install/trust plugins as an incidental test step. Stub external classifiers and use controlled hook payloads.
- Cover runtime selection, event routing, failed/no-op inputs, storage isolation, and changed behavior in both hosts.
- Verify archival preserves content, handles name collisions, and leaves recent/unrelated plans alone.
- Check both manifests, shared-module copies, referenced files, and future version synchronization.

Report exact checks run, failures/skips, and whether live installation was tested. Passing fixture tests does not prove a plugin is installed, trusted, or active.
