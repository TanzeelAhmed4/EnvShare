# EnvShare agent handoff

## Working-tree safeguards

This repository contains substantial uncommitted Batch 3 and Batch 4 work. Inspect `git status` and the relevant diff before changing anything. Preserve the current database, migration history, custom `accounts.User`, and existing encryption key. Do not reset, revert, stash, clean, or overwrite unrelated work. Never expose secrets, Sensitive values, tokens, passwords, or private user data. Staging, committing, pushing, and deployment require explicit authorization.

## Project state and layout

EnvShare is a React/TypeScript frontend with a Django REST Framework backend. SQLite is the local default; PostgreSQL is configurable and required by production settings. Production cache uses Redis. Source is under `frontend/src/`, `backend/accounts/`, `backend/projects/`, and `backend/config/`.

The current Windows checkout has a backend virtual environment at `backend\.venv` and Node dependencies at `frontend\node_modules`. The interpreter/runtime versions observed in this checkout are Python 3.14.4, Django 6.1.3, Node 24.18.0, and npm 11.16.0. See [Development guide](DEVELOPMENT_GUIDE.md) for commands.

## Implemented behavior

- Cookie-backed session authentication, CSRF token retrieval, Argon2-preferred password hashing, registration/login throttling, and authentication audit events.
- Project roles: Owner, Admin, Manager, and Member. The creator is the Owner. Only the Owner manages Admins; Admins may manage Managers and Members; Managers and Members cannot manage membership.
- Development, Staging, and Production environments; Standard and Sensitive variables; AES-GCM encryption for current Sensitive values and all historical snapshots.
- Variable history, compare, restore, and deletion snapshots; deleted-variable history is retained internally but is unavailable through regular API endpoints.
- Single-use, email-bound invitations with hashed tokens, expiry, and transactional acceptance. Email delivery is not implemented.
- Signed `.env` import preview/confirmation, audit history and server-side filters/pagination, project/environment-scoped write locking, and audit snapshot retention.
- Environment-based production settings, guarded WSGI/ASGI entrypoints, PostgreSQL and Redis configuration, health endpoints, security headers, and structured redacted logs.

## Important security and data rules

- Enforce project membership and role permissions in backend views/helpers; frontend visibility is not an authorization boundary.
- Do not put Sensitive plaintext in logs, audit rows, ordinary serializers, previews, or error messages. Successful Sensitive reveal is audited before plaintext is returned.
- Standard current values are stored as plaintext. Standard and Sensitive historical snapshots are encrypted.
- Historical AES-GCM context binds project, environment, variable, key, version, and classification. Current Sensitive value context binds environment and key.
- Variable writes create encrypted history, so the process needs the stable `ENVSHARE_ENCRYPTION_KEY` before variable creation/import. Never replace it for an existing database; key rotation and recovery are not implemented.
- SQLite is local/test default; production requires PostgreSQL and Redis. PostgreSQL row-lock behavior and Redis multi-worker behavior are not verified until tested against real services.
- Audit APIs are read-only but records are not tamper-proof against database operators or exported to an independent append-only store.
- Read [Production deployment](PRODUCTION_DEPLOYMENT.md) and [Backup and recovery](BACKUP_RECOVERY.md) before changing deployment guidance. The recovery procedures are documentation, not tested recovery evidence.

## Verification record

Latest recorded local verification:

- Backend: 139 tests discovered, 134 passed, 5 PostgreSQL-specific tests skipped because no PostgreSQL service was available. A separate deletion-history regression test passed after its route assertions were expanded.
- Frontend tests, TypeScript validation, Django checks, migration consistency, and `git diff --check` passed.
- Vite production bundling passed in production mode and with `--mode development`, using temporary output directories. A missing API URL under the overridden mode failed validation as intended. The combined `npm run build` attempt in the sandbox stopped at Vite/esbuild `spawn EPERM`; TypeScript and Vite bundling were verified separately.
- PostgreSQL concurrency and Redis shared-cache integrations remain pending. No deployment or recovery procedure has been certified.

Refer to [Project status](PROJECT_STATUS.md) for current limits. Do not turn skipped tests into passing claims, and do not describe EnvShare as production-certified.
