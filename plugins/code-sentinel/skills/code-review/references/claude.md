# Claude Code integration

- Artifact directory: `.claude/code-review/`, unless repository instructions override it. Resolve `<artifact-dir>` before using commands.
- Use Read/Grep/Glob for inspection and Bash for git/glab. Use only tools actually available.
- Track substantial work with TaskCreate/TaskUpdate/TaskList when available; otherwise use a concise checklist.
- For authorized delegated planning, use an available Plan agent through the host's Task/Agent tool. Otherwise plan inline. Do not require a particular model.
- Open the review with the required Ticket & Architecture Context from step 3.5: Key Docs, then the "What the MR does" and "How it relates to <X>" blocks. Follow the shared template: MR context, one global Reading Order, Flows and model changes, then Changes and detailed findings. Report findings with severity, file/line, impact, and evidence; attach native inline code comments when supported. Preserve this order in chat and any exported review. A findings-only reply or artifact link does not replace the required sections.
- Present results in chat. Post replies, resolve discussions, commit, or push only within user authorization.
