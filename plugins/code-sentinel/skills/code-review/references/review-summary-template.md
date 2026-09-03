# Review Summary Output Template

Use this template to structure the final review output for step 9 (Provide Review Summary).

```
Code Review:

Ticket & Architecture Context (if found in step 3.5)

Key Docs: [Jira KEY link] · [Epic KEY link, or "no epic linked"] · [Confluence page title + link] · [another Confluence page title + link, if a second main doc surfaced] (⚠️ flag any doc >1yr old as potentially stale)

[2 short paragraphs onboarding a reviewer unfamiliar with this project: what the project/feature is about, what the linked epic is trying to achieve, and the major design points surfaced by the docs above — enough to orient before reading the diff]

Not attempted: [reason, e.g. "no Jira key in MR"] — omit this line if the step ran

MR Context (if GitLab MR exists)

- MR #: [number]
- Reviewer Requests Addressed:
  - ✅ [Request 1] - [How addressed in code]
  - ✅ [Request 2] - [How addressed in code]
  - ⚠️  [Unresolved request] - [Status/concern]
- Key Discussion Points:
  - [Point 1 from comments]
  - [Point 2 from comments]

Major Changes (Prioritized)

1. [Most impactful change]
2. [Second most impactful]
   ...

Detailed Analysis

Change 1: [Title]

     Location: path/to/file.java:123

     What Changed: [Explanation]

     Concerns:
- ⚠️  [Issue 1]
- ⚠️  [Issue 2]

  Code Snippet:
  // relevant code

  Test Coverage: ✅ Covered / ❌ Missing

  ---
     [Repeat for each major change]

PR Notes (Copy to PR Description)

     Summary: [1-2 sentence overview]

     Action Items:
- [Specific fix needed]
- [Test to add]
- [Question for author]

  Questions:
- [Question 1]
- [Question 2]

Review Score: X/100

     Rating Scale:
- 90-100: Excellent, minimal changes needed
- 70-89: Good, minor improvements suggested
- 50-69: Acceptable, moderate changes recommended
- 30-49: Needs work, significant concerns
- 1-29: Major issues, substantial revision required

  Justification: [Why this score]
```
