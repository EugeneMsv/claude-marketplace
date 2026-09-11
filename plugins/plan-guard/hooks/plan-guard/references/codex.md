# Codex planning guidance

Follow the active host mode and user/repository instructions. A hook cannot switch Plan mode or elevate its own guidance to system policy.

- Classify the work as implementation or investigation. Keep the plan proportional to the request.
- Inspect current code and relevant documentation. State assumptions and resolve missing decisions before dependent work.
- Give ordered tasks with exact files and meaningful verification commands supported by repository evidence. Never invent build commands.
- Use update_plan only when exposed in the current mode; otherwise use a concise Markdown plan. Do not call TaskCreate or ExitPlanMode.
- Do not modify project code in Plan mode. Present the plan for the user's decision.
- Preserve existing changes. Perform branch preparation and commits only within user authorization.
- Identify test cases during planning when useful; write and verify affected tests during implementation.
- Name the documentation affected by the work and describe remaining risks or unknowns.
- Explicit update_plan events can be persisted by this plugin. Native narrative plans are not guaranteed to emit that event; do not claim they have been saved without inspecting the output file.
