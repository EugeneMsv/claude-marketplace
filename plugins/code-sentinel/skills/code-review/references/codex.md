# Codex integration

- Artifact directory: `.Codex/code-review/`, unless repository instructions override it. Resolve `<artifact-dir>` before using commands.
- Use available shell/file tools and `rg` for bounded inspection; use apply_patch for code edits. Do not call Claude-only Read, TaskCreate, or ExitPlanMode tools.
- Use update_plan if exposed, otherwise a concise Markdown checklist. Built-in Plan mode is controlled by the host; a skill cannot switch it merely by saying so.
- Delegate only when supported and authorized, using actual available subagents. Otherwise plan inline. Do not invent a Plan agent type or create sidebar tasks for internal work.
- Open the review with the required Ticket & Architecture Context from step 3.5: Key Docs, then the "What the MR does" and "How it relates to <X>" blocks. Follow the shared template: MR context, one global Reading Order, Flows and model changes, then Changes and detailed findings. Report findings with severity, file/line, impact, and evidence; attach native inline code comments when supported. Preserve this order in chat and any exported review. A findings-only reply or artifact link does not replace the required sections.
- Present results in chat. Posting replies, resolving discussions, committing, and pushing require user authorization.
