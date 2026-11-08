# EnvShare project status

## Current state

EnvShare implements a local course-project workflow for account sessions, projects, project membership, three environments, Standard and Sensitive variables, `.env` import preview/confirmation, and variable audit history. It has not been deployed and is not production-ready or production-certified.

### Security behavior in the current source

- Signup, login, logout, CSRF-token, and current-user endpoints use Django sessions and CSRF protection for mutations. Argon2 is the first configured password hasher.
- Login has independent controls: 5 requests per client IP per minute and a username-based failed-password bucket allowing 5 failures within 15 minutes before a 60-second cooldown. Cache keys contain an HMAC digest of an NFKC-normalized, trimmed, lowercase username, not the raw username or password. Successful authentication clears that username's failure and cooldown keys. Registration has a separate 5-per-hour client-IP throttle.
- Login uses Django's `username__iexact` lookup to resolve case variants to the stored username before calling Django authentication. Usernames and non-empty emails have case-insensitive uniqueness constraints using `Lower`. These Django ORM lookups and constraints can map to PostgreSQL, but only SQLite is configured here and PostgreSQL behavior has not been runtime-tested.
- Sensitive values are encrypted using AES-256-GCM, a random 12-byte nonce, and associated data bound to the environment identifier and variable key. Ordinary serializers mask them. Standard values are stored as plaintext.
- A successful Sensitive reveal is audited as action `revealed` with actor, project, environment, variable ID/key, and timestamp. The event's changes object is empty; plaintext is not passed to the audit recorder. Audit persistence happens before returning plaintext, and a failed audit write produces a generic 503 response without the value. Invalid access, missing variables, Standard variables, and decryption failures do not create reveal events.
- Variable mutations and their audit rows are transactional. Audit changes redact Sensitive values. Audit history is scoped to projects visible to the requesting owner/member.
- The frontend's `AuditEvent` union includes `revealed`; `EnvironmentVariables` invokes its audit-change callback only after reveal succeeds, causing the parent workspace's audit refresh token to change and the timeline to fetch again.

Migration `backend/projects/migrations/0004_reveal_audit_action.py` depends on project migration `0003_environmentvariableauditevent` and alters the existing `action` choices to add `revealed`. The model choice and migration agree. It adds no column and does not change the field's `max_length`.

## Verification status

Dates below use the project/client date context, 2026-11-08. These entries distinguish reported history from commands actually run in the latest verification session.

| Check | Result | Evidence and limits |
|---|---|---|
| Full backend suite | **79 passed, reported** | The independent security-review report says all 79 passed. The suite was not rerun during documentation work. |
| Django `check` and migration dry-run | **Previously reported passed; latest attempt unavailable** | An earlier report says both passed. The recent attempt used system Python and failed before Django started (`ModuleNotFoundError`). The requested root-level `backend.venv` path was absent. This inspection found the existing `backend\.venv\Scripts\python.exe` and verified Django 6.1.3 imports, but did not rerun checks or tests with it. |
| Frontend tests | **PASS, most recent run** | `npm.cmd test` passed 5 auth-session response assertions. |
| TypeScript check | **PASS, most recent run** | `npm.cmd run check` completed `tsc -b --pretty false` successfully. |
| Production build | **FAIL, most recent run** | `npm.cmd run build`: TypeScript completed, then Vite/esbuild failed to spawn with `spawn EPERM`. This is an execution-environment failure; no successful build was established by that run. |
| `git diff --check` | **PASS, most recent run** | No whitespace errors; Git printed line-ending conversion warnings. |

The independent review also reported 79 backend tests passing and frontend test/type checks passing. That report did not establish a production build result. Older README/phase notes recorded 59, 65, and 71 tests from earlier checkpoints; those counts are superseded by the latest reported count of 79 and are retained here only as historical context, not current test status.

No tests were rerun during this documentation update. The backend test modules declare 79 test functions/methods by source inspection; declaration count is not itself a test execution result.

## Scope and missing functionality

Implemented: authentication, project creation and creator-managed registered membership, owner/member project access, environment/variable CRUD, Sensitive reveal, import preview/confirmation, audit history, and basic responsive React UI.

Not implemented or not verified: hosted deployment; production database support/configuration; browser end-to-end tests; email verification or password reset; MFA; project update/delete UI/API; encryption-key rotation/recovery; off-site/tamper-proof audit retention; multi-worker shared-cache operation. The current project list/detail supports creating and reading projects; membership administration is creator-only. No additional member role hierarchy exists.

## Remaining production risks

- **Shared throttling cache:** Django's current default cache is local-memory/process-local. IP and username throttle counters are not coordinated across multiple workers. Configure and test a shared Redis cache (or an equivalent shared backend) before multi-worker deployment.
- **Repeated cooldown denial of service:** an attacker who knows a username can repeatedly submit enough wrong passwords after each 60-second cooldown expires, continuing to block that account temporarily. This is an acknowledged account-targeted denial-of-service risk.
- **Database operations:** settings hard-code SQLite. Select and configure a production database, then validate migrations, locking, backups, restore, capacity, and operational monitoring.
- **Encryption key recovery:** the AES key is external process configuration. There is no rotation or recovery workflow. Back up and restrict access to the existing key; losing or replacing it makes stored Sensitive values unreadable.
- **HTTPS and deployment:** production mode requires explicit host/origin/secret/key configuration and HTTPS CORS origins, turns on secure cookies and SSL redirect, and configures HSTS. Actual TLS termination, proxy behavior, domain coverage, HSTS subdomain/preload choices, secret delivery, static assets, and deployment automation remain unimplemented/unverified.
- **Audit durability:** audit rows are application-level and mutable by database operators; they cascade with project deletion and are not exported to an independent append-only store.
- **Validation coverage:** the frontend suite is small and no browser-level integration/E2E suite exists. A prior production build attempt failed at process spawn.

## Next work

Complete the local browser demonstration and submission checklist. Verify signup/login, owner/member permissions, project and environment navigation, variable CRUD, Sensitive masking/reveal plus timeline refresh, import confirmation, and audit history. Rerun backend tests/checks/migration dry-run with `backend\.venv\Scripts\python.exe`, rerun frontend tests/type check, and obtain a successful production build in an environment that permits esbuild child-process startup. Deployment remains out of scope unless separately authorized.
