# UI redesign orchestration

Updated: 2026-09-19

| Ticket | Agent | State | Dependencies | Integration gate |
| --- | --- | --- | --- | --- |
| T16 | `ticket_t16_resume` | Complete; deployed and verified | None | 60 tests + SAM lint/build pass; private and public execution passed live |
| T17 | `ticket_t17` | Complete; reviewed | T16 findings only for live verification | 4 contract + 4 mounted tests and production build passed |
| T18 | `ticket_t18` | Complete; reviewed | T17 | 4 API + 8 mounted tests, production build, desktop/mobile visual QA passed |
| T19 | `ticket_t19_resume` | Complete; reviewed | T17, T18 | 4 API + 10 mounted tests, production build, three-size visual QA passed |
| T20 | `ticket_t20` | Complete; focused paths reviewed | T18, T19 | Editor 2/2, T17 4/4, T19 2/2, API 4/4, production build passed |
| T21 | `ticket_t21` | Backend gate complete; frontend push pending | T16–T20 | Local suite/visual QA and deployed API pass; hosted frontend revision pending |

## Ownership and scheduling

- T16 owns backend/deployment files and may run in parallel with T17.
- T17, T18, and T19 share frontend composition files and run strictly in that order.
- T20 begins only after T19 freezes the workspace pane contract.
- T21 begins only after every implementation ticket has passed review and its integration gate.
- Each agent must stay within its ticket's owned files, preserve pre-existing work, and write `tickets/out/TNN.md`.
- The orchestrator reviews diffs and tests at every handoff. Git push remains the repository owner's action.

## Integration log

- 2026-09-19: T16 and T17 started as the first non-overlapping wave.
- 2026-09-19: T17 completed and passed orchestrator review; T18 started after the shared-file handoff.
- 2026-09-19: T18 completed; orchestrator corrected unsupported baseline-retake copy through the owning agent, then started T19.
- 2026-09-20: T19 resumed after usage interruption, completed, and passed orchestrator review; T20 started with exclusive editor/package ownership.
- 2026-09-20: T20 completed; T17/T19 owners migrated their own tests to the CodeMirror DOM contract. T21 started; T16 deployment remains approval-blocked.
- 2026-09-20: T21 local gate passed with 60 backend tests (1 platform skip), 16 frontend tests, production build, SAM validation/build, and nine viewport captures. Live release remains blocked on backend deployment approval and the repository-owner push.
- 2026-09-20: User explicitly approved the disclosed Lambda-only fallback. `compile-v2` reached `UPDATE_COMPLETE`; the private seeded solution passed, followed by one coordinated public practice check. Baseline resume, question loading, Run & Check, hint, trace, and CORS passed. Frontend release now requires only the repository-owner push and hosted browser check.
