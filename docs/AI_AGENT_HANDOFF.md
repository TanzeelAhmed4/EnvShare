# EnvShare AI agent handoff

## Read this before making changes

**Before changing any file, inspect the current workspace, README, this handoff, relevant implementation, migrations, tests, Git status, and applicable instructions. Report the current state and propose a focused plan when the task requires it. Do not assume an earlier phase is incomplete and recreate it.**

Preserve the working Phase 1–7 functionality, the custom `accounts.User` model, applied migration history, local database and user data, and the existing encryption key. Never reset/delete the database, regenerate/replace the encryption key, expose secrets, or alter unrelated files. Add migrations safely and only when needed. Do not deploy without explicit approval.

## Product scope

EnvShare is the course project “Team Environment Variable Manager.” The original two-page course PDF is authoritative. The MVP requirements are:

1. User signup and login.
2. User-created projects.
3. Project creators invite/add registered users; owners and members view/edit variables; members cannot manage membership.
4. Development, Staging, and Production environments per project.
5. Key/value variables classified Standard or Sensitive.
6. Sensitive values are encrypted at rest, masked in normal UI/API responses, and revealed only through an authorized operation.
7. Paste `.env` text; ignore blank lines/comments and parse supported key-value syntax.
8. Preview New, Update (old vs new), and Unchanged before saving; new values can be classified and existing classifications are retained.
9. Audit additions, changes, and deletions with actor, action, key/context, and time; redact Sensitive plaintext.
10. Accessible chronological history.
11. Secure password hashing, clear errors, and consistent UI.

Do not add features that expand the approved course scope without asking.

## Stack and layout

- Backend: Python, Django, Django REST Framework; SQLite for local course submission.
- Authentication: Django sessions and CSRF; Argon2 preferred for password hashing.
- Sensitive values: AES-256-GCM, with key supplied through environment configuration.
- Frontend: React, TypeScript, Vite, Tailwind CSS.
- Main paths: `backend/config/`, `backend/accounts/`, `backend/projects/`, `frontend/src/`, `frontend/tests/`, `docs/`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries and data flow, [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) for local commands, and [PROJECT_STATUS.md](PROJECT_STATUS.md) for phase status and checks.

## Implemented state

Phases 1–6 implement configuration, authentication, projects/memberships, three environments and encrypted variables, `.env` import preview/confirmation, and audit history. Phase 7 added focused security hardening, constraint migration, production configuration validation, login throttling, stale-preview rejection, and session-expiry handling. Phase 8 local browser demonstration/course-submission preparation is the next phase; it has not started. Deployment is out of scope and the application is not certified production-ready.

Backend tests cover authentication/CSRF, project access and roles, variable CRUD and authorization, encryption at rest/masking/reveal, key configuration, import parsing/classifications/confirmation/security, and audit attribution/redaction/permissions/transactions. Frontend tests include five session-response assertions. Browser E2E tests are not configured.

## Data and security invariants

- Preserve `backend/accounts/models.py` and the original `accounts` initial migration. Existing constraints were added in an additive migration.
- Never output actual `.env` values, passwords, tokens, encryption keys, Sensitive variable plaintext, or private user data. Inspect secret-bearing files only through a value-redacting classifier if necessary.
- Sensitive values must never appear in ordinary serializers, logs, errors, import tokens/previews, or audit records.
- Enforce project membership in backend permissions on every project-scoped API. Frontend hiding is not an access control.
- Keep variable writes and corresponding audit records transactional.
- Preserve existing migrations and database records. Never use `flush`, delete the SQLite DB, or rewrite migrations as a shortcut.
- The existing encryption key is required to decrypt current Sensitive values. Do not replace or rotate it; rotation/recovery is not implemented.
- Do not make dependency upgrades without checking advisories and compatibility first.

## Verification and reporting

Run relevant backend tests and checks, migration consistency checks, frontend session tests, TypeScript validation, and build when the task calls for them. Fix failures before reporting completion. Do not claim a command passed unless it was actually run; distinguish current checks from historical Phase 7 results. Avoid commands that modify data when doing read-only review/documentation work.

At task completion report files changed, behavior implemented, tests/checks performed with outcomes, and remaining limitations. Keep changes focused and save them. No deployment, remote configuration, commit, or push unless explicitly requested.
