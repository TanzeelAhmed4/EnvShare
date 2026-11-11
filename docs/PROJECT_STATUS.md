# EnvShare project status

**Status as of 2026-11-11:** Batches 1–4 and the final security fixes are implemented in the local working tree. EnvShare has not been deployed and is **not production-certified**. PostgreSQL and Redis integration checks and deployment-dependent verification remain outstanding.

## Implemented scope

- Registration, login, logout, session authentication, CSRF handling, Argon2-preferred password hashing, login/registration throttling, and authentication audit events.
- Private projects with Owner, Admin, Manager, and Member roles. Backend permissions protect project data and membership operations. Only the Owner can manage Admin membership; Admins manage Managers and Members.
- Development, Staging, and Production environments; Standard and Sensitive variables; AES-GCM Sensitive storage and authorized reveal.
- Encrypted version snapshots for Standard and Sensitive values, version comparison and restoration, and encrypted deletion snapshots. Deleted-variable history is retained internally but not accessible through normal API routes.
- Single-use, expiring, email-bound invitations with hashed token storage and transactional acceptance. Invitation email sending is not implemented.
- `.env` import preview and explicit confirmation; paginated, filtered variable and project-access audit APIs.
- SQLite development support, environment-based PostgreSQL settings, project/environment write-locking, production configuration validation, Redis cache configuration, security middleware, structured logs, and liveness/readiness routes.

## Latest local verification

These results are from the latest recorded implementation checks. PostgreSQL/Redis service behavior and hosting behavior were not established by the local tests.

| Check | Result | Scope and limits |
|---|---|---|
| Backend test suite | **139 tests discovered; 134 passed, 5 skipped** | Ran with SQLite. The five skipped tests are PostgreSQL-specific concurrency/integration tests because no PostgreSQL service was available. SQLite concurrency tests ran; they do not verify PostgreSQL locking. |
| PostgreSQL integration | **Pending** | PostgreSQL was unavailable at `127.0.0.1:5432`; no PostgreSQL service was installed for this check. |
| Redis shared-cache integration | **Pending** | Redis was unavailable at `127.0.0.1:6379`. Local cache/tests do not establish multi-worker Redis behavior. |
| Frontend tests | **Passed** | `npm.cmd test` completed the auth, invitation-link, CSRF, API-configuration, and audit-filter assertions. The current script does not print an assertion count. |
| TypeScript | **Passed** | `tsc --noEmit --pretty false` completed successfully. |
| Django checks | **Passed** | `manage.py check` reported no issues. |
| Migration consistency | **Passed** | `makemigrations --check --dry-run` reported no changes. |
| Vite production bundling | **Passed in both modes** | Vite production-mode build and `vite build --mode development` completed with a valid HTTPS API URL, writing to temporary output directories. The overridden-mode build without an API URL failed during configuration as intended. |
| Combined `npm run build` | **Not confirmed as one command** | A sandboxed attempt passed its TypeScript phase but Vite/esbuild could not spawn (`EPERM`). TypeScript and Vite bundling were subsequently verified separately. |
| `git diff --check` | **Passed** | No whitespace errors; Git emitted line-ending conversion warnings. |

## Deployment-dependent work

- Run the five PostgreSQL-specific tests against a real, disposable PostgreSQL test service and verify production migrations, locking, TLS certificate validation, backups, and restoration.
- Run throttling and health-check tests against the configured Redis service with the intended multi-worker deployment.
- Verify HTTPS termination, trusted proxy behavior, allowed hosts, CORS/CSRF origins, cookie behavior, and the frontend/API site topology.
- Configure CSP response headers on the static frontend host; Django's response middleware does not set headers on a separately served React document.
- Verify production secret delivery, log collection/redaction and retention, monitoring, static hosting, and health probes.
- Test database-plus-key recovery in an isolated environment. The repository does not implement key rotation or automatic backup/recovery.

## Known limitations and risks

- Losing or replacing `ENVSHARE_ENCRYPTION_KEY` makes encrypted current Sensitive values and all historical snapshots unreadable.
- A known username can be repeatedly targeted after each failed-login cooldown expires, temporarily denying that account login.
- Audit APIs are read-only, but audit rows are not tamper-proof against database operators and are not exported to an independent append-only store.
- Project/variable deletion retains audit/version snapshot data internally; normal project-scoped APIs do not expose deleted-resource history.
- There is no MFA, password reset, email verification, invitation email delivery, or browser end-to-end suite.
- Production configuration checks are application guardrails. They do not certify a particular host, proxy, database, cache, email service, or recovery process.
