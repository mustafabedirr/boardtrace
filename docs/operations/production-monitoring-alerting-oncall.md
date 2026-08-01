# BoardTrace Production Monitoring, Alerting, and On-Call

## Providers and Activation

Monitoring provider, alert transport, retention/access policy, and production
routes are `UNKNOWN`. Design status is `DESIGNED`; provisioning, configuration,
activation, and testing are `NO`.

## Signal and Alert Matrix

| Alert                    | Signal                          | Threshold    | Window       | Severity | Primary owner | Secondary owner | Route   | Runbook                         | Test plan                          | Recovery condition                     | Approval | Decision   |
| ------------------------ | ------------------------------- | ------------ | ------------ | -------- | ------------- | --------------- | ------- | ------------------------------- | ---------------------------------- | -------------------------------------- | -------- | ---------- |
| API availability         | health/error/latency            | NOT APPROVED | NOT APPROVED | high     | UNKNOWN       | UNKNOWN         | UNKNOWN | observability incident response | synthetic failure/recovery         | sustained healthy signal               | PENDING  | INCOMPLETE |
| queue pressure           | queue depth/age                 | NOT APPROVED | NOT APPROVED | high     | UNKNOWN       | UNKNOWN         | UNKNOWN | worker recovery                 | inject bounded backlog             | queue returns below approved threshold | PENDING  | INCOMPLETE |
| worker/Stockfish failure | task failures/child health      | NOT APPROVED | NOT APPROVED | high     | UNKNOWN       | UNKNOWN         | UNKNOWN | worker-loss recovery            | terminate worker in non-production | healthy claims and drain               | PENDING  | INCOMPLETE |
| database saturation      | latency/connections/errors      | NOT APPROVED | NOT APPROVED | high     | UNKNOWN       | UNKNOWN         | UNKNOWN | database incident runbook       | approved synthetic test            | normal latency/connection envelope     | PENDING  | INCOMPLETE |
| security anomaly         | auth/rate-control audit signals | NOT APPROVED | NOT APPROVED | high     | UNKNOWN       | UNKNOWN         | UNKNOWN | security operations governance  | approved alert-delivery test       | anomaly clears and owner confirms      | PENDING  | INCOMPLETE |

## On-Call Assignments and Coverage

| Role                | Actual assignee/team classification | Coverage     | Timezone | Contact-channel classification | Start date | Approval source | Decision |
| ------------------- | ----------------------------------- | ------------ | -------- | ------------------------------ | ---------- | --------------- | -------- |
| primary on-call     | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |
| secondary on-call   | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |
| incident commander  | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |
| security lead       | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |
| data-integrity lead | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |
| communications lead | UNKNOWN                             | NOT VERIFIED | UNKNOWN  | UNKNOWN                        | PENDING    | none            | MISSING  |

Launch-window coverage and escalation are not verified. The activation test plan
cannot execute until providers, routes, actual assignees, thresholds, and a
launch window are approved.

## Prompt 20-D-R3 Approved Monitoring Policy

- provider model: Uptime Kuma plus basic Docker/host metrics;
- panels: Dozzle and Uptime Kuma through SSH tunnel only;
- Telegram critical-alert destination: `BoardTrace Alerts` bot to
  `BoardTrace Pilot` group;
- alert scope: application unavailable, API health failure, critical container
  stopped, or server unavailable;
- panel thresholds: CPU 85%, RAM 85%, disk warning 80%, critical disk 90%;
- disk 90% action: stop new analyses, enter restricted mode, clean safe
  temporary/log/Docker usage, then Mustafa Bedir manually re-enables;
- operational owner: Mustafa Bedir.

The bot, group, token, chat identifier, monitoring service, and alert routes are
pending provisioning. Primary/secondary on-call, incident commander, security,
data-integrity, communications roles, coverage, and launch availability remain
missing, so D20R2-014 is unresolved.
