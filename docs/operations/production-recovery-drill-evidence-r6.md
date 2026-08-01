# BoardTrace R6 First Recovery Drill Evidence

Status: `NOT PERFORMED — MODE A`. This is an evidence form, not a completed
drill. Required participants are Mustafa Bedir and Ahmet Bedir. Use only
synthetic or empty data with public application traffic disabled.

| Field                    | Entry                      |
| ------------------------ | -------------------------- |
| date/start/end/timezone  | PENDING                    |
| host identifier (safe)   | PENDING                    |
| participants             | Mustafa Bedir; Ahmet Bedir |
| initial controlled state | PENDING                    |
| approval                 | PENDING                    |

For each scenario record starting state, exact allowlisted action, prohibited
negative check, expected/actual result, elapsed time, deviations, follow-up,
and approval:

1. stopped application container;
2. failed worker container;
3. Redis unavailable and fail-closed behavior;
4. rollback to previous-known-good immutable image;
5. disk restricted-mode response;
6. health validation;
7. communication handoff.

Success requires recovery to a controlled non-public state within the exercise
target, understandable instructions, working rollback/health checks, only
approved Ahmet actions, and resolution of every critical defect. Otherwise
R4-007 remains open.
