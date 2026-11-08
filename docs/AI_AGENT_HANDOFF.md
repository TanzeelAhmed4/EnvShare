# EnvShare AI agent handoff

## Read this before making changes

Before editing, inspect the current workspace, this handoff, README, relevant source, migrations, tests, Git status, and applicable instructions. Preserve the current local database, migration history, custom `accounts.User`, and existing encryption key. Do not reset the database, regenerate/replace the key, expose secrets, or alter unrelated files. Add migrations only when needed and never rewrite an applied migration. Deployment, staging, committing, and pushing require separate explicit authorization.

EnvShare is a local course project, not a production-ready service. The original course requirements remain the product boundary: account sessions; projects and registered-user sharing; Development, Staging, Production; Standard/Sensitive key-value variables; encrypted Sensitive storage and authorized reveal; `.env` preview/confirmation; variable audit history; secure password handling; and a usable frontend.

## Stack and paths

- Backend: Django 6.1.3, Django REST Framework 3.18.3, SQLite, accounts and projects apps.
- Existing Windows backend interpreter: `backend\.venv\Scripts\python.exe` (Django 6.1.3 verified). The root-level `backend.venv` path is absent.
- Frontend: React 18, TypeScript 5.6, Vite 6.4.5; sources in `frontend/src/`, the current small test in `frontend/tests/`.
- Read [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md), and [PROJECT_STATUS.md](PROJECT_STATUS.md) before relevant work.

## Current implementation details

Implemented behavior includes session/CSRF authentication, Argon2-preferred password hashing, case-insensitive login and uniqueness constraints, IP and per-normalized-username failed-login protection, owner/member project access, three environments, variable CRUD, AES-GCM Sensitive values, import preview and confirmation, and chronological audit history.

Login limits are 5 requests/IP/minute and 5 failed passwords/normalized username per 15-minute window followed by a 60-second cooldown; registration is 5/IP/hour. The username failure cache key uses an HMAC digest. A successful login clears the failure state. The cooldown can be repeatedly triggered against a known account, creating a temporary denial-of-service risk. Cache is currently local-memory/process-local, not shared between workers.

Sensitive reveal auditing is implemented in `backend/projects/environment_views.py`: only successful Sensitive reveals write action `revealed`; the audit event stores metadata with empty `changes`, before the API returns plaintext. The plaintext is not passed to the audit helper. Audit-write failure returns a generic 503 and withholds the value. `backend/projects/migrations/0004_reveal_audit_action.py` adds the model action choice after migration 0003. The frontend type includes `revealed`; its successful reveal handler invokes `onAuditChange`, which refreshes `AuditTimeline`; failure does not invoke it.

Case-insensitive login resolves `username__iexact` to the stored username before Django authentication. Username and non-empty email uniqueness use `Lower` constraints. This avoids SQLite-only lookup SQL and is intended to improve PostgreSQL portability, but settings only configure SQLite and PostgreSQL behavior is not verified.

## Security and data invariants

- Never print, copy, or expose `.env` values, passwords, tokens, encryption keys, Sensitive variable plaintext, or private user data. Do not inspect secret-bearing files through ordinary output commands.
- Never put raw usernames or passwords in login-throttle cache keys. Keep IP request throttling separate from username failure cooldown state.
- Sensitive plaintext must not enter audit rows, logs, error messages, ordinary serializers, or import previews. Reveal plaintext only after audit persistence succeeds.
- Enforce project membership in backend views/permissions; frontend hiding is not authorization.
- Keep variable writes and corresponding audits transactional. Preserve project deletion cascade semantics unless explicitly changed.
- Preserve the existing encryption key. Rotation/recovery is not implemented.
- Keep actual `.env`, database, virtual-environment, key, and build artifacts out of source changes.

## Verification and reporting

Use the exact Windows commands in the development guide. Distinguish current execution from historical reports. The latest available full backend result is 79 passing tests as reported by the independent security review; it was not rerun in the documentation inspection. Latest frontend tests (five assertions) and TypeScript check passed; the latest production build failed because esbuild hit `spawn EPERM`. The actual nested backend virtualenv imports Django 6.1.3, but backend checks were not rerun with it during the inspection. Do not claim a check passed unless it was run.

No browser E2E suite exists. Production database setup, shared cache, key backup/recovery, HTTPS/deployment operations, and independent audit retention remain unresolved. Report files changed, checks actually run, errors/limitations, and discrepancies. Do not stage or commit unless separately asked.
