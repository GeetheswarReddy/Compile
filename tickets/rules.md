# Hard rules
1. Only create/edit files listed under "Files owned." Touching anything else is a failure condition — stop and report instead.
2. Do not alter any signature listed under "Interfaces consumed." If it's insufficient for your task, STOP and report exactly what's missing rather than changing it unilaterally.
3. If you must introduce a new interface not in your "Interfaces produced" list, implement it, but explicitly flag it at the end of your run under a heading "New interfaces introduced" so it can be reconciled against other in-flight tickets.
4. At the end of your run, output your ACTUAL "Interfaces produced" as implemented — this may differ slightly from the plan; report the real signatures, not the planned ones, since this becomes the input to any downstream ticket.
5. Do not run/modify tests or files belonging to other tickets, even to "fix" something you notice — report it instead.

# End-of-run report format
- Files changed: <list>
- Interfaces produced (actual): <signatures>
- New interfaces introduced (if any): <list>
- Blockers / deviations from plan: <list, or "none">