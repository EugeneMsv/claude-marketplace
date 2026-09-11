# Codex integration

- Artifact directory: `.Codex/mr-nitpick-sentinel/`, unless repository instructions override it. Resolve `<artifact-dir>` before using commands.
- Use available shell/file tools and `rg` for bounded inspection; use apply_patch for code edits. Do not call Claude-only Read, TaskCreate, or ExitPlanMode tools.
- Use update_plan if exposed, otherwise a concise Markdown checklist. Built-in Plan mode is controlled by the host; a skill cannot switch it merely by saying so.
- Delegate only when supported and authorized, using actual available subagents. Otherwise plan inline. Do not invent a Plan agent type or create sidebar tasks for internal work.
- Report actionable findings first with severity, file/line, impact, and evidence. Attach native inline code comments when supported; keep the shared review's flow and model analysis in its artifact.
- Present results in chat. Posting replies, resolving discussions, committing, and pushing require user authorization.
