---
name: msv-memory-refiner
description: This skill should be used when the user asks to "refine memory", "improve memory files", "update memory", "analyze learnings", "suggest memory improvements", "optimize memory", or requests analysis of conversation patterns to improve Claude Code's memory. Analyzes conversation history and existing memory files to suggest specific, actionable improvements.
allowed-tools: Read, Grep, Glob
disable-model-invocation: true
---

# Memory Refiner

## Purpose

This skill analyzes conversation history and existing memory files to identify patterns, learnings, and user preferences, then suggests specific improvements to memory files. The goal is to help memory files evolve based on actual usage patterns, making Claude Code progressively more aligned with user needs.

## When to Use

Invoke this skill when:
- Conversation reveals repeated corrections or preferences
- User explicitly requests memory analysis or refinement
- After completing complex tasks to capture learnings
- Memory files may be outdated or incomplete
- Identifying conflicts or gaps in existing memory

## Core Analysis Workflow

### Phase 1: Discovery

Analyze recent conversation history to identify:

**Explicit Preferences:**
- Direct statements: "I prefer X", "Always do Y", "Never do Z"
- Tool preferences: "Use grep instead of ripgrep"
- Style preferences: "Keep responses concise", "Explain your reasoning"

**Implicit Patterns:**
- Repeated corrections on same topic
- Consistent workflow sequences
- Tool usage patterns
- Error handling preferences
- Testing approaches

**Workflow Optimizations:**
- Successful task completion patterns
- Effective tool combinations
- Time-saving shortcuts discovered
- Automation opportunities

Examine at least 10-20 recent exchanges. Look for patterns that appear 2+ times.

### Phase 2: Memory Audit

Read and analyze all memory files:

**Common memory locations:**
- `~/.claude/CLAUDE.md` - Global instructions
- `~/.claude/CLAUDE.local.md` - Personal customizations
- `~/.claude/*.md` - Domain-specific files (Java-codestyle.md, etc.)
- `.claude/**/*.md` - Project-specific memory
- `CLAUDE.md` - Project-specific memory
- `~/.skills/**/*.md` - skills memory
- `~/.agents/**/*.md` - agents memory
- `~/.claude/rules/*.md` - agents memory


**Audit checklist:**
- Categorize existing content (coding standards, tools, workflows, preferences)
- Identify gaps (patterns from conversation not captured)
- Detect conflicts (contradictory instructions)
- Flag outdated information (tool usage has evolved)
- Note redundancies (same instruction in multiple places)

### Phase 3: Synthesis

Match conversation learnings to memory structure:

**Gap Analysis:**
- What learnings are missing from memory?
- Which patterns occur frequently but aren't documented?
- Are tool preferences captured?
- Do workflow patterns have guidance?

**Conflict Resolution:**
- Where do memory files contradict conversation behavior?
- Are there conflicting instructions across files?
- Which source is more current/accurate?

**Prioritization:**
- High impact: Frequently occurring patterns
- Medium impact: Occasional but important preferences
- Low impact: One-off situations

### Phase 4: Suggestion

Generate specific, actionable improvement suggestions:

**Suggestion Format:**

```markdown
## Suggested Improvements

### 1. [Category] - [Brief Description]

**File:** `path/to/file.md`
**Priority:** High/Medium/Low
**Type:** Addition/Modification/Removal

**Current State:**
[Show existing content or note if missing]

**Proposed Change:**
[Show exact text to add/modify/remove]

**Rationale:**
[Explain why based on conversation evidence]
- Evidence 1: [Quote or reference from conversation]
- Evidence 2: [Additional supporting evidence]

**Impact:**
[Describe expected improvement]
```

**Example:**

```markdown
### 1. Tool Preference - Prefer Grep over direct ripgrep

**File:** `~/.claude/CLAUDE.local.md`
**Priority:** High
**Type:** Addition

**Current State:**
No grep/ripgrep preference documented.

**Proposed Change:**
Add to Tools Mapping section:
```
- Use `Grep` tool for content search (NOT grep or rg commands directly)
- Grep tool has optimized permissions and access
```

**Rationale:**
User corrected direct ripgrep usage 3 times in last session, consistently asking to use Grep tool instead.
- "Use the Grep tool, not rg command"
- "Please use Grep tool for searching"
- "Don't use ripgrep directly"

**Impact:**
Eliminates repeated corrections, aligns with user's established workflow preference.
```

## Output Guidelines

**Be Compact:**
- Proposed changes must be as short as possible — one line preferred
- No examples inside the proposed change unless essential
- Cut rationale to one sentence + one evidence quote max
- Skip the Impact field unless it adds something non-obvious

**Be Specific:**
- Quote exact file paths
- Show precise text changes
- Reference specific conversation moments

**Be Actionable:**
- Provide ready-to-apply changes
- No vague suggestions like "consider improving"
- Include exact wording for additions

**Be Justified:**
- Every suggestion needs conversation evidence
- Explain why the change matters
- Show frequency or impact

**Be Organized:**
- Group by file or category
- Order by priority
- Separate additions from modifications from removals

## Key Principles

**Evidence-Based:**
- Never suggest changes without conversation evidence
- Require 2+ instances for pattern recognition
- Explicit statements override implicit patterns

**Non-Conflicting:**
- Check for contradictions with existing memory
- Propose conflict resolution when found
- Maintain consistency across memory files

**User-Centric:**
- Capture user's actual behavior, not ideal behavior
- Reflect user's language and terminology
- Respect user's workflow, don't impose "best practices"

**Maintainable:**
- Suggest clear, understandable additions
- Avoid overly complex rules
- Keep memory files scannable

**Scope-Appropriate (priority order):**
- **Highest priority**: `~/.claude/rules/*.md` — topic-specific rule files (coding, git, tools, workflows); add/update rules here first
- **Global file**: `~/.claude/CLAUDE.local.md` — general preferences and cross-cutting instructions
- **Auto-memory**: project-specific `.claude/memory/*.md` is secondary; if an entry is generic enough to apply across projects, promote it to `rules/` or `CLAUDE.local.md` instead
- Domain-specific → `~/.claude/[domain].md`
- Standards/policies → `~/.claude/CLAUDE.md` (warn: managed file, do not edit directly)

## Implementation Steps

1. **Read conversation history** - Use context from current session
2. **Read memory files** - Use Read tool for all .claude/*.md files
3. **Identify patterns** - Look for repetition, corrections, preferences
4. **Audit memory** - Check for gaps, conflicts, outdated info
5. **Generate suggestions** - Follow format above with evidence
6. **Present for review** - User decides which suggestions to apply

## Validation

Before presenting suggestions:
- ✓ Each suggestion has conversation evidence
- ✓ File paths are correct and accessible
- ✓ No conflicts with existing memory (or conflict noted)
- ✓ Changes are specific and actionable
- ✓ Priority reflects frequency/impact
- ✓ Rationale is clear and justified

## Common Pitfalls to Avoid

**Don't:**
- Suggest based on single occurrence
- Propose vague improvements without specifics
- Ignore existing memory content
- Create redundant entries
- Suggest changes to managed files without warning
- Propose "best practices" that contradict user behavior

**Do:**
- Base everything on evidence
- Show exact changes
- Check for conflicts
- Organize by priority
- Respect user's established patterns
- Keep suggestions focused and actionable

## Follow-Up

After user reviews suggestions:
- Apply approved changes to memory files
- Verify changes don't introduce conflicts
- Confirm changes are properly formatted
- Test that memory loads correctly
