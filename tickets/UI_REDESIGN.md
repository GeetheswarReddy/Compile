# Compile UI redesign and deployed submission recovery

Requested: a LeetCode-like workspace with question left, code editor right, and trace bottom-left, plus repair of deployed submission. Reviewed `../image.png` and current frontend source on 2026-09-19.

The image shows the current home screen, oversized type, default buttons, and “Failed to fetch”. It does not prove a submission-specific root cause. Source confirms a vertically stacked editor and trace outside the workspace. Live AWS inspection found an in-progress rollback after a concurrency allocation failure; the current template already removes that allocation. Investigation must distinguish these observations.

| Ticket | Priority | Deliverable | Dependencies |
| --- | --- | --- | --- |
| [T16](T16.md) | P0 | Recover backend deployment and prove live submissions | None |
| [T17](T17.md) | P0 | Recoverable initialization/submission states | T16 findings for live checks |
| [T18](T18.md) | P1 | Cohesive typography, controls, navigation and colors | T17 shared-file edits |
| [T19](T19.md) | P1 | Question-left/editor-right workspace; trace bottom-left | T17, T18 |
| [T20](T20.md) | P1 | Python editor with syntax highlighting and indentation | T18, T19 |
| [T21](T21.md) | P0 gate | Browser, visual, integration and deployed release evidence | T16–T20 |

## Execution rules

These are new follow-up tickets; T01–T15 remain historical. Read current README and source before implementing: the older digest has outdated generation timing and execution-boundary descriptions. Follow tickets/rules.md within each ticket's owned files. Shared frontend files are deliberately sequenced T17 → T18 → T19; do not edit them concurrently. T16 backend work can proceed alongside frontend work. Preserve existing uncommitted reflection and smoke-test changes.

Keep the single practice Run & Check action, existing baseline/scoring/quota rules, anonymous identity, private execution service, and demo trace feature flag. Similarity to LeetCode describes information placement and editing ergonomics; preserve Compile branding and product behavior. No account system, multi-language support, or unrelated feature expansion is required.

No ticket is implemented merely by being created. T21 is the release gate. Capture actual interfaces, owned files changed, evidence, and blockers in each ticket's out report. Git pushing remains the repository owner's step under the existing handoff.
