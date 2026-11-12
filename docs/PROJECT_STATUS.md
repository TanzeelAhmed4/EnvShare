# EnvShare project status

**Status as of 2026-11-12:** Batches 1–4 and the encryption compatibility fixes are present in the local working tree. EnvShare is **not production-certified**. Local checks do not establish PostgreSQL, Redis, hosting, or recovery behavior.

## Implemented features

- Registration, login, logout, session authentication, CSRF handling, Argon2-preferred password hashing, login/registration throttling, and authentication audit events.
- Private projects with Owner, Admin, Manager, and Member roles enforced by backend permissions.
- Development, Staging, and Production environments; Standard and Sensitive variables; AES-256-GCM Sensitive storage and authorized reveal.
- Encrypted version snapshots, comparison and restoration, and deletion snapshots. Restoration creates a new version. Deleted-variable history is retained internally but is not exposed through normal routes.
- Single-use, expiring, email-bound invitations with hashed token storage and transactional acceptance. Invitation email delivery is not implemented.
- `.env` import preview and explicit confirmation; filtered, paginated project, membership, variable, and authentication audit APIs.
- SQLite local development; configurable PostgreSQL; production Redis cache configuration; guarded production entry points; security middleware; structured redacted logs; liveness and readiness endpoints.
- Separate `ENVSHARE_ENCRYPTION_KEY` for Sensitive values and `ENVSHARE_HISTORY_ENCRYPTION_KEY` for new Standard history. Legacy v1/v2 snapshot readers preserve access through the documented compatibility paths.

## Latest verified results

The following local results were reported for the latest completed verification run:

| Check | Result | Notes |
|---|---|---|
| Backend tests | **149 passed; 5 skipped** | The skipped tests are PostgreSQL-specific. The run used SQLite; it does not establish PostgreSQL locking or concurrency. |
| Frontend tests | **Passed** | Local frontend test suite completed. |
| TypeScript | **Passed** | TypeScript checking completed. |
| Django system check | **Passed** | No issues reported. |
| Migration consistency | **Passed** | No uncommitted model migration changes reported. |
| Production frontend build | **Passed** | Production Vite build completed. |
| `git diff --check` | **Passed** | No whitespace errors reported. |
| Existing local encrypted history | **4 snapshots decrypted** | Read-only verification; only the success count was reported. |
| Existing local Sensitive records | **1 record decrypted** | Read-only verification; no value was printed. |
| Encryption availability | **Sensitive and Standard history available** | Both status flags reported available during the read-only verification. |
| Manual workflows | **Confirmed by user** | Standard creation, Sensitive creation, and `.env` import were confirmed working locally. |

The local decryption counts refer to the verified local database and configured keys at that time; they are not a guarantee for another database or backup. No database records were modified by those checks.

## Pending production verification

- Run the five PostgreSQL-specific tests against a real disposable PostgreSQL service; verify migrations, row locks, concurrency, TLS certificate validation, and backup/restore behavior.
- Exercise Redis-backed throttling and health checks across the intended number of application workers.
- Verify HTTPS termination, trusted proxy behavior, allowed hosts, CORS/CSRF origins, cookie behavior, frontend/API site topology, and frontend-host CSP headers.
- Verify production secret delivery, log collection/redaction and retention, monitoring, alerts, static hosting, and health probes.
- Restore a production-like database with matching keys in an isolated environment and perform controlled decryption checks.

## Known limitations

- Losing or replacing `ENVSHARE_ENCRYPTION_KEY` makes current Sensitive values, Sensitive history, and legacy v1 history unreadable. New Standard v3 history needs `ENVSHARE_HISTORY_ENCRYPTION_KEY`.
- Legacy Standard v2 history was derived from the Django `SECRET_KEY` active when written. The reader first tries the currently configured Django key, then the dedicated history key as a compatibility fallback. To remain independent of future Django key changes, the dedicated key must contain the exact corresponding legacy HKDF-derived material. Keep the original Django key until that compatibility has been provisioned and verified.
- Key rotation and history re-encryption are not implemented. Replacing a key does not migrate data.
- A known username can be repeatedly targeted after each failed-login cooldown expires, temporarily denying that account login.
- Audit APIs are read-only, but database operators can alter audit rows; there is no independent append-only audit store.
- There is no MFA, password reset, email verification, invitation email delivery, or browser end-to-end suite.
- Production checks are application guardrails and do not certify a particular deployment.
