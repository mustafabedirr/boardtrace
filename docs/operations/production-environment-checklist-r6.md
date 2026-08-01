# BoardTrace R6 Production Environment Checklist

This checklist contains names and expected categories only. Real values belong
only in `/opt/boardtrace/.env`, owned by root with mode `0600`, during an
explicitly authorized Mode B execution.

## Static requirements

- [ ] `BOARDTRACE_ENVIRONMENT=production`
- [ ] JSON metadata-only logging; raw game logging prohibited
- [ ] hostname and all public/API URLs use `https://boardtrace.duckdns.org`
- [ ] CORS and trusted-host lists contain no localhost values
- [ ] queue, rate-limit, timeout, session-only result, terminal deletion and
      provenance policies match the R5-R2 contract
- [ ] SSH port is 48227; key auth required; password auth disabled
- [ ] admin panels are private/local-only
- [ ] R2 bucket is `boardtrace-pilot-backups`
- [ ] GHCR repository is `ghcr.io/mustafabedirr/boardtrace`, with an immutable
      approved version and digest rather than `latest`

## Secret categories

- [ ] application JWT signing secret and refresh-token pepper
- [ ] PostgreSQL and Redis connection values
- [ ] Telegram bot token and chat identifier
- [ ] R2 account, access-key and secret-key values
- [ ] GHCR username and packages-read token
- [ ] DuckDNS token in its separate root-only updater configuration
- [ ] age public recipient on the host; age private key confirmed off-host

## Secret-safe verification

```powershell
.\.venv\Scripts\python.exe scripts\production_preflight.py
```

The command has no force/skip switch and reports missing key names only. Mode A
must fail at the real-value environment gate. Never run `Get-Content`/`cat`,
`env`, `set`, or Docker configuration dumps against the production secret file
as evidence.
