# BoardTrace Production Deployment Preflight

Run from the repository root:

```powershell
pnpm production:preflight
```

This is the only repository deployment-preflight entry point. It validates the
R4 decision package, SSH artifacts, and the complete process-injected production
environment, then stops. It performs no remote deployment and supports no
`--force`, `--skip`, partial-deployment, or fallback mode.

The canonical inventory is
`infrastructure/production/production-environment-contract.json`. It separates
required secrets, required non-secret policy, optional tuning, and generated
external identifiers. The placeholder-only
`infrastructure/production/.env.production.example` intentionally fails the
real preflight and must never be deployed.

Required external categories include Telegram token/chat ID, R2 account/bucket
and credentials, GHCR user/token/image, DuckDNS hostname, and the code-derived
API/worker/web/extension settings. Validation reports key names only and never
values. Production remains blocked until real values are provisioned outside
the repository and this same preflight passes with them.
