# Review Summary Output Template

Use this template to structure the final review output for step 9 (Provide Review Summary).
The opening context section is required in chat and in any exported review. Follow step 3.5's
access gate before proceeding; an explicit user-authorized exception must remain visible here.
List only sources actually retrieved. Absence of access is not evidence of absent tickets or docs.

```
Code Review:

Ticket & Architecture Context

Key Docs: [Jira KEY link + last-modified date] · [Epic KEY link + last-modified date, or "no epic linked" only after checking the ticket] · [Confluence page title + link + last-modified date] · [second main doc, if found] (⚠️ flag docs >1yr old as potentially stale; use "not applicable" for a user-confirmed ticketless change)

[2 short paragraphs onboarding a reviewer unfamiliar with this project: what the project/feature is about, what the linked epic is trying to achieve, and the major design points surfaced by the docs above — enough to orient before reading the diff]

Context gaps / authorized exception: [Unavailable sources and explicit authorization to proceed, or completed searches that found no relevant docs; distinguish code-derived context from fetched requirements. Omit this line when there are no gaps.]

MR Context (if GitLab MR exists)

- MR #: [number]
- Reviewer Requests Addressed:
  - ✅ [Request 1] - [How addressed in code]
  - ✅ [Request 2] - [How addressed in code]
  - ⚠️  [Unresolved request] - [Status/concern]
- Key Discussion Points:
  - [Point 1 from comments]
  - [Point 2 from comments]

Reading Order

1. [File/class/method to read first — what to understand here]
2. [Next file/class/method — how it connects to the previous stop]
   ...
[One definitive sequence for the whole review, covering all affected flows and shared models. No per-change reading orders or alternative traversals.]

Flows and model changes

[Affected flow diagrams and model/domain/DTO diff trees from steps 5.2/5.3. State explicitly when there are no model changes.]

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
