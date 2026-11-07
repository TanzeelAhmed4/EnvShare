# EnvShare project status

## Current state

Phases 1–7 are implemented. EnvShare has its local Django REST Framework backend, React client, SQLite database, session authentication, project sharing, environment variables, encrypted sensitive values, import preview/confirmation, and audit history. The application has not been deployed and is not declared production-ready.

Registration attempts are throttled separately from login: five attempts per client IP per hour. Login remains limited to five attempts per minute.

The original course PDF is the functional authority. Its requirements are preserved: authentication; projects and registered-user sharing; Development, Staging, and Production environments; Standard/Sensitive key-value variables; encryption and authorized reveal; `.env` parsing and a New/Update/Unchanged preview before save; audit records for additions, changes, and deletions; accessible history; secure password handling; clear errors; and consistent UI.

## Phase record

| Phase | Scope | Status |
|---|---|---|
| 1 | Project configuration, dependency manifests, Django REST Framework, React initialization | Completed |
| 2 | Registration, session login/logout, CSRF, Argon2 preference, auth screens and tests | Completed |
| 3 | Projects, registered-user membership, roles, owner/member access and tests | Completed |
| 4 | Three environments, variable CRUD, AES-256-GCM, masking/reveal and tests | Completed |
| 5 | `.env` parsing, comparison preview, explicit confirmation and tests | Completed |
| 6 | Variable audit timeline, actor attribution, safe change details, import audit and tests | Completed |
| 7 | Focused security hardening, dependency advisory review, regression tests, local config validation | Completed; not a production-readiness certification |
| 8 | Browser-based local demonstration and course-submission preparation | Next; not started |

## Verification record

**Previously reported for Phase 7:** 59 backend tests passed; Django system checks passed; migration consistency check reported no changes; `pip check` was clean; frontend session assertions, TypeScript check, and Vite build passed; npm audit reported zero vulnerabilities. A production-mode deployment check had two warnings because HSTS subdomain coverage and preload were intentionally disabled pending domain review. Browser end-to-end tests were not configured.

**Rerun during this documentation inspection:** Django `check` passed with no issues; `makemigrations --check --dry-run` reported no changes; `pip check` found no broken requirements; five frontend session assertions passed; TypeScript `--noEmit --incremental false` passed. All listed accounts and projects migrations were shown as applied. The full backend suite and frontend production build were not rerun in this documentation-only pass.

**Registration throttle change:** all 65 backend tests passed, including six new regression tests for configured rates, allowed requests, 429 behavior without user creation, isolation from login/unrelated endpoints, CSRF enforcement, and sensitive-input redaction. Django `check` passed. No migration was added or applied.

No database migration or write, dependency installation, build, deployment, or secret/key operation was performed during this documentation pass.

## Current limitations

- No browser end-to-end test suite; manual full-workflow verification remains for Phase 8.
- No deployment infrastructure or production database configuration.
- No encryption-key rotation/recovery process; preserving the key is essential to decrypt existing Sensitive values.
- SQLite and the local-memory login throttle are local-development choices.
- Audit records are not tamper-proof and are deleted through project cascade.
- HSTS subdomain and preload policy needs domain-specific review before deployment.

## Repository and secret handling

The root, backend, and frontend ignore files exist. The root `.gitignore` includes local environment files, Python artifacts, SQLite databases, frontend dependencies/builds, generated files, and private-key/certificate extensions. The `.env.example` files were reviewed by classification without printing values: the backend file uses placeholders including an instruction for supplying a generated encryption key; the frontend file contains a local API URL. Neither was found to contain an actual credential/key or private URL. Actual `.env` files must remain private.

At inspection, `git status --short` showed the root `backend/`, `frontend/`, and `docs/` directories and root README/ignore file as untracked. Review all contents before the first commit, particularly to ensure ignored local secrets and database files are not force-added. The documentation directory contained no documents before this update. No Git staging, commit, remote, or push operation was performed.

## Phase 8 exit criteria

1. Start backend and frontend using the documented Windows commands.
2. Verify signup, login/logout, project creation, member addition, environment switching, variable CRUD, Sensitive masking/reveal, import preview/confirmation, and history in a real browser.
3. Verify outsider and member/owner permissions in the browser against backend behavior.
4. Record only reproducible defects and resolve them with focused regression coverage.
5. Re-run the backend suite, Django checks, migration consistency check, frontend tests, TypeScript check, and production build before marking Phase 8 complete.
6. Keep deployment out of scope unless the user separately approves it.
