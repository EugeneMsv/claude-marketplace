# permissions-juditor

Before Claude Code shows you a permission prompt for a Bash command or an MCP tool call, calls Sonnet with a purpose-written security-classification prompt and lets it decide `allow` (auto-clear, no prompt), `ask` (prompt proceeds, with the model's reasoning attached), or `deny` (blocked, with a reason) — so genuinely safe commands stop interrupting you, while risky ones still get a human decision or are stopped outright.

## What It Does

### Hooks

| Hook | Event | Purpose |
|---|---|---|
| `security-judge` | `PermissionRequest` (`Bash`, `mcp__.*`) | Fires only when Claude Code actually needs a permission decision — never for a command/tool an existing `allow` rule already covers. Classifies watched commands and MCP tool calls via a forced Sonnet tool call and maps the result to a `PermissionRequest` decision. |

### Scope: env-var controlled, not config-bound

`hooks/claude.json` matches every `Bash` and `mcp__*` `PermissionRequest` — it does not filter by command prefix or tool name. Actual scope is controlled entirely inside `security-judge.py`, via `PERMISSIONS_JUDITOR_WATCHED_COMMANDS` — **one env var covers both Bash commands and MCP tool calls**, as a single comma-separated list of glob patterns:

| Value | Effect |
|---|---|
| *(unset)* | Default: covers `python3` only — **no MCP tool is scanned until you add one** |
| `python3,git push,npm install` | Comma-separated list — covers exactly those Bash prefixes, each entry auto-suffixed with `*` if it has none |
| `python3,mcp__atlassian__*` | Mix Bash prefixes and MCP tool-name globs freely in the same list — this example watches `python3` invocations AND any Atlassian MCP tool call |
| `mcp__atlassian__createJiraIssue` | An entry with no `*` still auto-suffixes one, but since MCP tool names have no further segments after the tool, this effectively pins one exact tool |
| `` *(empty string)* | Covers nothing — a live kill switch for the whole plugin |
| `python3 -m *` | An entry already containing `*` is used exactly as written, for a narrower match |

A Bash command is matched segment-by-segment (see below). An MCP tool call is matched as one whole `tool_name` string (e.g. `mcp__atlassian__search`) against the same pattern list — no segmentation needed, since a tool name has no pipeline/chain structure. Because this lives in the script rather than `hooks/claude.json`, changing scope takes effect on the very next call — no plugin edit, no `hooks/claude.json` edit, and no Claude Code restart (unlike `hooks/claude.json` itself, which is only read at session start).

### MCP tool calls: judged on their actual parameters, not just the tool name

For a watched MCP tool, the classification prompt embeds the tool name and its full JSON parameters (truncated past 2000 characters) — the model is explicitly instructed to dig into the parameters for the real risk signal, the same way it inspects a Bash command's arguments rather than just its interpreter name:

- A SQL/query-language parameter is read for its actual statement: `DROP`/`TRUNCATE`/`DELETE`, or an `UPDATE` with no (or an overly broad) `WHERE`, is **destructive → deny**, even if the tool is generically named `execute_query`. A plain `SELECT` is `allow`; a narrowly-scoped `INSERT`/`UPDATE` is `ask`.
- A read-only SQL query that scans a long time range — no date/timestamp filter at all, or one spanning multiple months or years — on what looks like a large table is `ask`, not `allow`: nothing is modified, but a full-range scan on a sizeable table is a real resource-cost risk worth a glance before it runs. A `LIMIT` clause does **not** change this — it bounds only the rows returned, not the range the engine scans to find them, so `... WHERE created_at >= '2020-01-01' LIMIT 100` is still `ask`.
- Querying a table's **partitions metadata** (Trino/Hive `"table$partitions"` syntax, e.g. `SELECT * FROM "orders$partitions"`) is `allow` even with no `WHERE` clause — it's a cheap catalog/metadata lookup, not a scan of the table's actual row data. Don't confuse this with the real cost driver above: a normal `SELECT` against the table itself filtered by a wide partition-key range still scans that whole range and is still `ask`.
- A **metrics/observability tool's time range** (e.g. Grafana's `from`/`to` or `start`/`end`) is the same resource-cost risk as a long SQL scan, even though the call is read-only. The model computes the actual span between the two bounds regardless of how it's expressed — a relative range (`now-30d`, `now-90d`) or a pair of explicit absolute dates more than a week apart (`"from": "2026-01-01", "to": "2026-02-15"`) are the same risk. About a week or less stays `allow`; anything longer is `ask` — scanning that much metrics/log data can overload the backend.
- A delete/remove-shaped action (by tool name or an explicit parameter) is **destructive → deny**, regardless of how small the target looks.
- A create/edit/send action (message text, ticket fields, document body) that doesn't destroy anything is `ask`, not `deny`.
- A message/content parameter being sent externally (Slack, email, a public page) is checked for sensitive data (credentials, internal identifiers, PII) leaving the organization — that shifts an otherwise-`ask` "send" action to `deny`.

Reference rules for MCP calls come from your own `~/.claude/settings.json` `permissions.allow`/`ask`/`deny` entries, filtered to `mcp__`-prefixed entries (Claude Code's raw tool-name format for MCP rules, e.g. `mcp__atlassian__createJiraIssue` — unlike Bash's `Bash(...)`-wrapped form). Each system prompt only ever carries the rules relevant to the call type being judged — a Bash command's prompt never sees MCP rules and vice versa — to keep it focused.

### Matching is segment-aware, not whole-string

A command like `cat data.json | python3 -` or `sudo python3 x.py` has `python3` as the *second* command, not the first token of the whole string. `security-judge.py` uses `shlex` (stdlib, no new dependency) with `punctuation_chars=True` to tokenize the command, splits it into pipeline/chain segments on `|`/`&`/`;`/`(`/`)`, skips a leading `VAR=value` assignment or a wrapper (`sudo`/`time`/`nice`/`nohup`) in each segment, and glob-matches every segment against the watched patterns. A pipe character inside a quoted argument (`python3 -c "print('a|b')"`) is correctly kept as part of that one token, not mistaken for a real pipeline boundary.

**Known ceiling:** `shlex` is a lexer, not a shell grammar parser. `$(...)` command substitution, here-docs, and control-flow keywords (`if`/`for`/`while`) can still hide a watched command from detection — e.g. `for f in a b; do grep ... "$f"; done` segments as `["do grep ... $f"]`, and `do` (not a stripped wrapper token) becomes the head, so a `grep*` pattern never matches. A narrow custom pattern like `python3 -m *` also won't match if flags are reordered or inserted before `-m` (e.g. `python3 -u -m foo`) — that's a property of glob matching itself, unrelated to segmentation, and doesn't affect the plain `python3` default entry.

### Optional: real shell-grammar segmentation via `PERMISSIONS_JUDITOR_SEGMENTER`

| Value | Effect |
|---|---|
| *(unset)* / `shlex` | Default — the flat punctuation-token segmenter described above, unchanged. |
| `bashlex` | Parses the command with [bashlex](https://github.com/idank/bashlex) (real bash grammar) instead — correctly walks into `for`/`if`/`while`/`until`/`case` bodies, subshells `(...)`, and `$(...)`/backtick command substitution, closing most of the "known ceiling" gap above. Falls back to the `shlex` segmenter on any failure (bashlex not installed, or a parse error on malformed bash) — segmenter choice never causes this hook to raise. |

**`bashlex` mode's own ceiling:** bashlex doesn't implement `$((...))` arithmetic expansion at all — `bashlex.parse()` raises `NotImplementedError` on it, not a graceful partial parse. Confirmed live (2026-08-28): a `while`/`until` loop with a `$((i+1))` counter in its body silently fell back to the `shlex` segmenter for the *entire* command, reproducing the exact `for`-loop false negative this mode exists to fix (`grep`/`rg` inside the loop body went undetected). Any watched command sharing a script with `$((...))` anywhere — not just near the watched command itself — degrades the same way, with nothing in `decisions.jsonl` distinguishing it from a genuinely unwatched command. `for`/`if`/subshells/`case`/command-substitution were all separately verified live and work correctly.

`bashlex` is a third-party dependency, so it's opt-in and lazily imported — the plugin stays stdlib-only unless you set this. `hooks/claude.json` invokes this script as bare `python3` on `PATH`, shared across every install of this plugin, so it can't hardcode a personal venv path; a Homebrew/system `python3` is typically "externally managed" (PEP 668) and refuses `pip install` even with `--user`. To enable `bashlex` mode without touching system packages, install it into an isolated venv at the conventional path this hook checks automatically if the plain `import bashlex` fails:

```bash
python3 -m venv ~/.claude/permissions-juditor/venv
~/.claude/permissions-juditor/venv/bin/pip install bashlex
```

Then set `PERMISSIONS_JUDITOR_SEGMENTER=bashlex` (e.g. in the `env` block of `~/.claude/settings.json`). No `hooks/claude.json` edit or Claude Code restart needed — same live-reload property as `PERMISSIONS_JUDITOR_WATCHED_COMMANDS`.

### Reference rules from your own settings — non-binding except deny

The classification prompt embeds your existing `~/.claude/settings.json` `permissions.allow`/`ask`/`deny` rules, filtered to `Bash`-prefixed entries only. The model is explicitly instructed:

- **Deny rules are authoritative** — a match (or functional equivalent) forces `deny`.
- **Ask and allow rules are context only**, not a rulebook to replicate — the model is told to prefer `allow` when genuinely confident a command is safe, even if a static `ask` rule would have caught it, but never to stretch to `allow` out of real uncertainty. Security comes first; reducing prompts is the secondary goal.

### Auto-mode context — an additional suggestion alongside each rule

If your `~/.claude/settings.json` has an `autoMode` section (the prose instructions Claude Code's own built-in auto-mode classifier uses), it's read via `load_auto_mode_context()` and attached as one extra line under each of the three rule categories above — not a separate section the model has to cross-reference on its own:

| `autoMode` key | Attached under | Weight |
|---|---|---|
| `hard_deny` | Deny rules | Authoritative — same as a deny-rule match |
| `soft_deny` | Ask rules | Authoritative for `ask` — same as an ask-rule match |
| `allow` | Allow rules | Context only, same non-binding treatment as the allow rules themselves |
| `environment` | Its own line, before "How to use this reference" | Background — used to judge whether a hostname/GCP project/login-path/path named in the command is production or non-production |

The literal `"$defaults"` placeholder entry (Claude Code substitutes this for its own built-in defaults at classification time) is filtered out before the prompt is built — it would be meaningless as literal text outside Claude Code's own classifier. Missing file, missing `autoMode` key, or malformed JSON all resolve to empty lists, same fail-open behavior as the Bash-rules reference above.

### Decision policy

- **allow** — safe/read-only/benign local operations: pure computation, printing, reading files you already have, running your own scripts.
- **ask** — genuinely ambiguous, or a real-but-bounded side effect worth a glance: writing local files, installing packages, opening a local network listener.
- **deny** — destructive, exfiltrates data, escalates privileges, disables security controls, obfuscates its own behavior, or targets credentials/sensitive paths.

The full prompt (including few-shot examples) lives in `SYSTEM_TEMPLATE` (static instructions + reference rules — sent as the request's cached system prompt) and `USER_TEMPLATE` (just `cwd`/command — the part that changes every call) in `security-judge.py`, and is easily edited.

## Model Resolution

1. `PERMISSIONS_JUDITOR_MODEL` — if set, used as-is. This hook's own override, for swapping in a different model *family* entirely (e.g. `claude-haiku-4-5` for lower latency) rather than pinning a dated alias within Sonnet. Takes priority over everything below.
2. `ANTHROPIC_DEFAULT_SONNET_MODEL` — if set, used as-is (useful on Bedrock/Vertex deployments where the bare alias may not be enabled).
3. `claude-sonnet-5` — the undated alias, used when neither env var above is set.

Switching model is a real classification-quality tradeoff, not just a latency one — benchmarked live against this hook's own prompt (60 commands, Haiku effort=high vs Sonnet effort=medium): 88% decision agreement, but the one disagreement that mattered was Haiku declining to honor an authoritative deny-rule match (downgraded `rm -rf` under a matched deny rule to `ask`) — the one instruction this prompt marks non-negotiable. Weigh that against the latency win (Haiku warm-cache: ~1.5–1.9s vs Sonnet: ~2.0–4.5s) before switching.

## Effort Resolution

This hook blocks Claude Code's permission dialog, so latency is a real cost — but so is under-reasoning on an obfuscated or adversarial command. `output_config.effort` is set explicitly per call:

1. `PERMISSIONS_JUDITOR_EFFORT` — if set to one of `max`/`xhigh`/`high`/`medium`/`low`, used as-is. An unset or unrecognized value falls back to the default below rather than raising.
2. `medium` — the default, balancing latency against reasoning depth on obfuscated/adversarial commands. Lower it to `low` for faster/cheaper calls if you're confident in the classifier on your workload; raise it toward `high` for more scrutiny at the cost of latency.

The request's static instructions and reference-rules block (everything except `cwd`/the command itself) are also sent as a `cache_control: ephemeral` system prompt, so repeated invocations within the cache TTL skip re-processing that prefix. Measured, that prefix is effectively free: dropping all 22,826 characters of it changed p50 by ~73ms, non-monotonically (a 6,000-character prompt measured *faster* than none at all), so the variation is noise. **Trimming the prompt is not a latency lever** — don't spend effort there.

## Rationale Output — `PERMISSIONS_JUDITOR_REASONING_ENABLED`

Whether the model states a rationale next to its verdict. `true` (the default) or `false`; only an explicit, case-insensitive `false` disables it, so a typo keeps the more informative mode rather than silently stripping every explanation.

| Setting | Schema sent | p50 | Message on ask/deny |
|---|---|---|---|
| `true` (default) | `reasoning`, then `decision` | ~1890ms | the model's own reason |
| `false` | `decision` only | ~1430ms | a fixed placeholder |

When enabled, the rationale is ordered **before** the verdict, and that ordering is load-bearing rather than cosmetic: structured-output arguments are generated in schema property order — verified directly by streaming the raw `input_json_delta` fragments — so putting the rationale first makes the verdict conditioned on it. The reverse order is what this hook originally shipped and is strictly worse: the verdict is already committed by the time the rationale is generated, so it pays full decode cost for narration that cannot affect the decision. That reversed shape is deliberately not offered as an option.

Disabling costs ~460ms less at **no measurable accuracy cost** (36 real commands x 3 passes: self-agreement 30/36 rationale-first vs 27/36 verdict-first, a 3-command gap that is not significant at that sample size). What it does cost is the explanation: `deny` is ~1% and `ask` ~11% of verdicts, so you pay the ~460ms on 100% of calls to get a real reason on the ~12% where one is actually surfaced.

### Where the time actually goes

Decomposed live, so latency work targets the right thing. For a ~1720ms call:

| Component | Cost | Reducible by |
|---|---|---|
| local work (segmenting, settings, prompt build) | ~1ms | nothing left |
| dns + tcp + tls | ~160ms | only a persistent connection |
| cached system prefix | ~0ms | nothing — not a lever |
| decode (token generation) | ~50-160ms | the rationale switch |
| everything else (TTFT: queue + prefill) | ~1300ms+ | not reachable client-side |

Time-to-first-token is ~91% of the call, which is why output-shrinking and prompt-trimming both underdeliver relative to intuition.

## Credential Resolution

This hook calls the public Messages API directly via the shared `anthropic_client.py`, so it needs a credential of its own:

1. `HOOKS_LLM_URL` + `HOOKS_LLM_AUTH_TOKEN`, both required together — an explicit, portable endpoint+credential configuration you set yourself (e.g. via a `env` block in `~/.claude/settings.json`), naming exactly which endpoint and bearer token every hook using the shared client should call. Takes priority over everything below, and doesn't depend on Claude Code's internal, undocumented Keychain storage format. Setting only one of the two is treated as neither being set.
2. `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` env vars, if either is set.
3. On macOS, the OAuth access token Claude Code itself stores in the login Keychain under the service name `Claude Code-credentials` — used only if unexpired. This lets subscription/OAuth-authenticated users get a working hook without exporting a separate credential.

If none resolve, the hook silently no-ops (logged as `skip_no_credentials`) rather than prompting for a key.

## Failure Handling

Failures split on whether the hook actually meant to judge the call.

**Out of scope, or not configured to run** — malformed hook input, an unsupported tool, an unwatched command/tool, or missing credentials — falls through to `{}`, no decision override. The call proceeds through Claude Code's normal permission flow exactly as if this plugin weren't installed.

**A watched call it meant to judge but couldn't** — network failure, HTTP error, or an unexpected/invalid model response — returns an explicit `ask` carrying the reason it failed. `{}` is not safe here: if the user's own `permissions.allow` rules already cover that command, falling through auto-approves it with *no judgment at all*, which is precisely the case this hook exists to catch.

Note the Codex consequence: Codex has no `ask` behavior, so its adapter maps `ask` to `deny` (see [codex.md](codex.md)). Under Codex a transient network error on a watched command therefore *blocks* it rather than deferring. That is deliberate — Codex's fallback is an automatic reviewer that could approve an unjudged call — but it makes retry-on-transient-failure more important there than on Claude.

**A watched Bash command longer than `MAX_COMMAND_CHARS` (15,000)** is denied without a model call at all, with a message telling the caller to split it. Judging only the readable prefix would be a bypass rather than a truncation: a benign prefix would clear a destructive tail the model never saw. Over-long MCP parameters (past `MAX_MCP_PARAMS_CHARS`, 18,000) instead escalate an `allow` to `ask`, since a single large SQL statement cannot be "split" the way a shell command can. Both caps are sized above the largest values observed across real session transcripts, so neither path fires routinely.

## Decision Log

Every invocation — not just the ones that reach a real classification — appends one JSONL line to `~/.claude/permissions-juditor/decisions.jsonl`, for both Bash and MCP:

```json
{"timestamp": "2026-08-24T15:44:23", "session_id": "...", "tool_name": "Bash", "command": "python3 -c \"print(1)\"", "cwd": "/path", "outcome": "decided", "decision": "allow", "total_ms": 1841, "http_ms": 1788, "reasoning": "Pure computation with no I/O."}
{"timestamp": "2026-08-24T15:45:10", "session_id": "...", "tool_name": "mcp__atlassian__getConfluencePage", "command": "MCP tool `mcp__atlassian__getConfluencePage` invoked with parameters: {\"pageId\": \"123456\"}", "cwd": "/path", "outcome": "decided", "decision": "allow", "total_ms": 1156, "http_ms": 1103, "reasoning": "Read-only page fetch."}
```

`command` holds the Bash command text or, for an MCP call, the rendered `MCP tool \`X\` invoked with parameters: ...` subject. `outcome` is one of `decided`, `skip_unwatched_command`, `skip_no_credentials`, `skip_unsupported_tool`, `skip_empty_command`, or `error` (with an `error` field describing what failed). This is the plugin's audit trail — always on, not gated behind a debug flag.

Two latency fields, present on `decided` and `error` outcomes, because the gap between them is the actionable part:

| Field | Covers |
|---|---|
| `http_ms` | the API call alone — the HTTP round-trip to the model |
| `total_ms` | everything since the hook module was imported: watched-pattern matching, `settings.json` reads, prompt construction, and the API call |

Measured on real traffic, the round-trip is ~94-99% of `total_ms`, so the two normally sit within a few ms of each other; a widening gap means local work (the lazy `bashlex` venv import is the only candidate large enough to notice). `http_ms` is `null` when no request was made — the over-length deny path, or a failure before the request went out. `total_ms` excludes the interpreter's own startup before the module loads (~25-30ms), which isn't observable from inside the hook.

`http_ms` replaced the earlier `elapsed_ms`, which covered the same span under the old name — lines written before that change still carry `elapsed_ms`, so a script computing percentiles across the cutover has to accept both keys.

## Installation

```bash
claude plugin install permissions-juditor@eug-msv-claude-marketplace
```

Hooks load only at session start — restart Claude Code after installing or after changing `hooks/claude.json` for the change to take effect. Changing `PERMISSIONS_JUDITOR_WATCHED_COMMANDS` does not require a restart.
