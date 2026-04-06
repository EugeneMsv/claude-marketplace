---
name: msv-code-review
description: Makes a code review based on branch name
---

# Code Reviewer Skill

## Trigger
- User requests code review, PR review, or diff review
- User mentions reviewing changes, analyzing commits, or comparing branches

## Instructions

You are an expert Senior Software Engineer performing a code review.

### Workflow

1. **Get Branch Information**
    - Ask user for branch name if not provided
    - Use `git fetch --all` to update all remote branches

2. **Check for GitLab MR Context** (if applicable)
    - Use `glab mr list --source-branch <branch-name>` to find associated MR
    - If MR exists, use `glab mr view <mr-number> --comments` to retrieve all comments
    - Analyze MR comments to identify:
        - **Reviewer Requests**: What changes/fixes were requested
        - **Author Responses**: How author addressed each request
        - **Unresolved Discussions**: Any open threads or concerns
        - **Historical Context**: Previous iterations and decisions
    - Use this context to inform the review (do NOT store separately)

3. **Generate Diff**
    - When reviewing feature branches, use `git diff origin/main...<branch>` to get changes.
    - Store in `.claude/diff-<branch>-origin-main.txt`
    - If diff is empty, verify branch exists and has changes

4. **Analyze Changes**
    - Read the diff file thoroughly
    - Use git worktree for main branch and another one for provided branch
    - Identify major changes (exclude tests, minor refactors, comments)
    - Focus on: new logic, architectural changes, significant dependency changes
    - Always MUST identify the data flows which are affected by the changes
    - Always MUST identify Model/domain/POJO/DTO changes
    - Always MUST use git worktree

4.1 **Git worktree**
Use it per each branch in the diff to get the next:
- The whole picture of the affected files in the diff
- The flows comparison/changes (look for the 3.2 to get the details)
- To get any other details which are not in the diff, but might be better for the understanding by human reviewer

4.2 **Identifying the affected flows**
1. **Entry Point**: REST endpoint, message topic, scheduled job, sny other external integration
2. **Layer Transitions**: Web → Domain → Persistence → External
3. **Changed Components**: Mark with 🔵 or 🟢
4. **New Logic**: Highlight new calculators, validators, services with 🟢
5. **Data Transformations**: Show mapper invocations

Once the flows are identified, for each flow, the whole flow diagram must be presented and the changed part
   must be reflected.
    Example:

┌─────────────────────────────────────────────────────────────────────┐
│                POST /api/v1/subscriptions/initiate                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  WEB LAYER (my-service-web)                                         │
│  ├─ OrderInitiationController                                       │
│  │   └─ Receives JsonOrderInitiationRequest                         │
│  │                                                                  │
│  └─ JsonOrderMapper 🔵                                              │
│      └─ Transforms: JSON DTO 🔵 → Domain Model 🔵                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DOMAIN LAYER (my-service-domain)                                   │
│  └─ OrderInitiationService 🔵                                       │
│      ├─ 1. Business logic validation                                │
│      ├─ 2. Calculate order schedule 🟢                              │
│      ├─ 3. Create Order aggregate                                   │
│      ├─ 4. Call OrderRepository.save()                              │
│      └─ 5. Call PublicationService.publish()                        │
└─────────────────────────────────────────────────────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
┌────────────────────────────────────┐  ┌────────────────────────────────┐
│ PERSISTENCE LAYER                  │  │ EXTERNAL LAYER                 │
│ (my-service-persistence)           │  │ (my-service-external)          │
│                                    │  │                                │
│ ├─ JdbcOrderRepository             │  │ └─ PublicationService          │
│ │   └─ INSERT order                │  │     └─ Kafka event publisher   │
│ │       (MASTER DB)                │  │         order.initiated        │
│ │                                  │  │                                │
│ ├─ JdbcOrderItemRepository         │  │                                │
│ │   └─ INSERT order items          │  │                                │
│ │                                  │  │                                │
│ ├─ JdbcOrderActionRepository       │  │                                │
│ │   └─ INSERT audit trail          │  │                                │
│ │                                  │  │                                │
│ └─ JdbcOrderSnapshotRepo           │  │                                │
│     └─ INSERT order snapshot       │  │                                │
│                                    │  │                                │
│ [MySQL Master]                     │  │ [Kafka]                        │
└────────────────────────────────────┘  └────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RESPONSE FLOW                                                      │
│  ├─ Domain → JsonOrderMapper 🔵                                     │
│  └─ JsonOrderInitiationResponse                                     │
└─────────────────────────────────────────────────────────────────────┘

       Legend:
       - 🔴 = Removed component
       - 🟢 = Added component
       - ⚪ = Unchanged component
       - 🔵 = Transitively Changed component

4.3 **Model/domain/POJO/DTO** changes approach
        - If the structure is changed analyze the full fields hierarchy/tree of the class (starting from the root class).
        - Identify the root aggregate first (e.g., Subscription, Order, User), It is usually used by major components in the flow from 3.2
        - Show complete nested hierarchy from root to changed field
        - Never present isolated nested objects without parent context
        - Combine nested structures into single tree (not separate sections)
        - Show ALL intermediate levels - no skipped fields
        - Draw a human-readable diff tree where mark:
          - Red the removed nodes
          - Green the new nodes
          - Blue the changed object nodes
          - White not changed nodes/fields
        - Always include inner fields structure of the changed/removed/added nodes.
      example:
      com.example.payments
      └── config
      └─🔵 OrderConfig
      ├── ⚪ orderId: String
      ├── 🔴 customerId: String
      ├── 🟢 customer: CustomerInfo
      │   ├── 🟢 id: String
      │   ├── 🟢 email: String
      │   └── 🟢 tier: Integer
      ├── ⚪ amount: BigDecimal
      ├── 🔴 paymentMethod: String
      ├── 🟢 payment: PaymentInfo
      │   ├── 🟢 method: String
      │   ├── 🟢 provider: String
      │   └── 🟢 fees: Money
      │       ├── 🟢 amount: BigDecimal
      │       └── 🟢 currency: Currency
      ├── 🔴 status: String
      ├── 🟢 status: OrderStatus(enum: 🟢VALUE1, ⚪VALUE2, 🔴VALUE3)
      ├── ⚪ createdAt: Instant
      ├── 🔴 shippingAddress: String
      └── 🟢 shipping: ShippingInfo
      ├── 🔵 address: Address
      │   ├── 🔴 street: String
      │   ├── 🟢 city: String
      │   └── 🟢 postalCode: String
      ├── 🟢 carrier: String
      └── 🔵 trackingNumber: 🟢String 🔴Integer

       Legend:
       - 🔴 = Removed field
       - 🟢 = Added field
       - ⚪ = Unchanged field
       - 🔵 = Changed object field


5. **Prioritize by Impact**
    - Reorder from most to least impactful:
        - Core functionality changes (highest priority)
        - API/interface modifications
        - Architectural changes
        - Algorithm updates
        - Configuration changes (lowest priority)

6. **Review Each Major Change**

   For each prioritized change, analyze:

    - **Logic**: Bugs, edge cases, incorrect assumptions
    - **Performance**: O(n) complexity, database queries (N+1), memory usage
    - **Security**: Input validation, SQL injection, XSS, auth issues
    - **Standards**: Deviation from Java codestyle (final, var, records)
    - **SOLID Principles**: SRP, OCP, LSP, ISP, DIP violations
    - **Maintainability**: Clarity, naming, documentation

7. **Test Coverage**
    - Check if changes are covered by tests
    - Suggest test cases for untested changes
    - Verify test structure follows Given-When-Then

8. **Provide Review Summary**

   Format:
   Code Review:

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


10. **Export final review to markdown**

### Rules

- MUST use `git --no-pager` for clean output
- MUST compare against `origin/main` (not local main)
- MUST store diff in `.claude/` folder
- MUST use `mcp__sequentialthinking__sequentialthinking` for complex analysis
- MUST reference specific file paths with line numbers
- MUST include code snippets for top 3 most significant changes
- MUST verify test coverage for all major changes
- MUST present the review output in chat — NEVER post to GitLab MR unless user explicitly instructs it
- MUST draw ASCII before/after directory layout diagrams when packages, modules, or files are reorganized
- DO NOT review test files in detail (only verify coverage)
- DO NOT comment on formatting if spotlessApply will handle it
- DO NOT mention files where only imports changed — skip them entirely

### Example Invocation

User: "Review my feature branch feature/user-authentication"
