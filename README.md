# EnvShare

EnvShare is a local course project for sharing and managing environment variables across a team. It provides session-based authentication, project membership, three project environments, protected variable management, `.env` import preview, and an audit timeline.

**Status:** Phases 1–7 are implemented. The application is intended for local demonstration and course submission. Deployment has not started; this documentation does not claim production readiness.

## Completed features

- Signup, login, logout, duplicate username/email validation, password validation, CSRF protection, and session-authenticated private APIs.
- The existing custom `accounts.User` model is preserved. Argon2 is the preferred password hasher.
- Project creation and owner-managed membership for registered users. Owners and members can access project data; members cannot manage membership.
- Exactly Development, Staging, and Production environments per project.
- Standard and Sensitive environment variables, key validation, and duplicate-key prevention per environment.
- Sensitive values stored using AES-256-GCM encryption, masked in ordinary API responses, and revealed through a separate authorized operation.
- `.env` parsing and preview with New, Update (old/new), and Unchanged classifications; confirmation is required before writes. Existing sensitivity is preserved on update, and new variables require a classification.
- Audit records for variable creation, update, deletion, and import changes, with actor and timestamp. Sensitive plaintext is redacted.
- Production configuration validation and security settings, login throttling, normalized username/email uniqueness constraints, stale import-preview rejection, and frontend session-expiry handling.

## Architecture

```text
Browser (React, TypeScript, Tailwind, Vite)
  └── Django REST Framework API (session cookies + CSRF)
        ├── accounts: custom user and authentication
        ├── projects: projects, membership, environments, variables,
        │             import preview/confirmation, encryption, audit history
        └── SQLite: local development and course-submission data
```

Backend code lives under `backend/`; frontend code and its npm manifests live under `frontend/`. The encryption key is supplied through environment configuration and must remain separate from source control and the database. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Repository layout

```text
EnvShare/
├── .gitignore
├── README.md
├── docs/
│   ├── AI_AGENT_HANDOFF.md
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT_GUIDE.md
│   └── PROJECT_STATUS.md
├── backend/
│   ├── accounts/       # custom user, auth, migrations, tests
│   ├── config/         # Django settings and URL routing
│   ├── projects/       # projects, variables, import, encryption, audit
│   ├── manage.py
│   └── requirements.txt
└── frontend/
    ├── src/            # React screens, API helpers, styling
    ├── tests/
    ├── package.json
    └── package-lock.json
```

## Files created and modified

The implementation spans Phases 1–7. Important existing and added files include:

- **Backend configuration and accounts:** `backend/config/settings.py`, `backend/config/security_settings.py`, `backend/config/urls.py`, `backend/accounts/models.py`, `backend/accounts/auth_views.py`, `backend/accounts/serializers.py`, `backend/accounts/tests.py`, and `backend/accounts/migrations/0001_initial.py` plus the additive `0002_alter_user_options_and_more.py`.
- **Projects and data workflows:** `backend/projects/models.py`, `permissions.py`, `serializers.py`, `views.py`, `environment_views.py`, `environment_serializers.py`, `encryption.py`, `env_import.py`, `audit.py`, `audit_views.py`, `signals.py`, the project test modules, and migrations `0001_initial.py` through `0003_environmentvariableauditevent.py`.
- **Frontend:** `frontend/src/App.tsx`, `authApi.ts`, `authSession.ts`, `projectsApi.ts`, `ProjectWorkspace.tsx`, `EnvironmentVariables.tsx`, `AuditTimeline.tsx`, stylesheets, and `frontend/tests/authSession.test.mjs`.
- **Manifests and local configuration examples:** `backend/requirements.txt`, `backend/.env.example`, `frontend/package.json`, `frontend/package-lock.json`, and `frontend/.env.example`.
- **Repository documentation and ignores:** root `.gitignore`, `backend/.gitignore`, `frontend/.gitignore`, this README, and the four documents under `docs/`.

This is a phase-level summary rather than a per-commit change log. The original custom user model and applied migrations were preserved; Phase 7 added an account constraint migration without resetting the local database.

## Dependencies

Backend versions are pinned in `backend/requirements.txt`: Django 6.1.3, Django REST Framework 3.18.3, django-cors-headers 4.9.0, argon2-cffi 25.1.0, and cryptography 46.0.3.

Frontend versions are recorded in `frontend/package-lock.json`: React 18, React DOM 18, Lucide React, TypeScript 5.6, Vite 6.4.5, the Vite React plugin, Tailwind CSS 3, PostCSS, and Autoprefixer. The Phase 7 dependency review reported zero npm audit findings after the Vite update; see [known issues](docs/PROJECT_STATUS.md) for the scope of verification.

## Local setup and checks

Use the exact PowerShell setup and startup commands in [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md). In short, configure the backend environment, install Python and npm dependencies, apply migrations, then run Django on port 8000 and Vite on port 5173. Open `http://localhost:5173`.

Previously reported Phase 7 verification included 59 passing backend tests, successful Django checks, no migration drift, a clean `pip check`, five frontend session assertions, TypeScript checks, a successful Vite production build, and zero npm audit findings. During the current documentation inspection, I reran safe checks only: Django `check`, migration dry-run, `pip check`, the five frontend assertions, and TypeScript no-emit validation; these all passed. Backend test suite and frontend build were not rerun during this documentation pass.

## Known limitations and risks

- Deployment, hosting, production database operations, and domain-specific HTTPS configuration are not implemented.
- Browser-based end-to-end tests are not configured. Existing automated tests focus on backend API behavior and a small frontend session helper.
- AES key rotation and recovery are not implemented. Preserve the current key: replacing it makes existing encrypted values unreadable.
- SQLite is intended for local use. Concurrent writes and row-lock behavior differ from a production database.
- Audit history is application-level history, not tamper-proof or independently retained; it follows project deletion.
- Production HSTS subdomain and preload settings remain disabled pending review of the eventual domain topology.
- Login throttling uses local-memory cache and is process-local.
- `.env.example` files contain placeholders/local settings only. Never commit actual `.env` files, credentials, encryption keys, databases, or generated artifacts.
- The root, backend, and frontend `.gitignore` files were inspected. The root ignore file covers environment files, databases, dependencies/build outputs, and private-key/certificate extensions. At inspection, Git status showed the root `backend/`, `frontend/`, `docs/`, README, and root ignore file as untracked. Review `git status` carefully before the first commit, especially to ensure no local secrets or databases are included. No files were staged or committed during this documentation update.

## Exact next phase

**Phase 8: Local demonstration and submission preparation.** Validate the full user workflow in a browser, document any reproducible defects, and prepare a course-submission checklist. This phase does not authorize deployment or new product features. See [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) and [AI_AGENT_HANDOFF.md](docs/AI_AGENT_HANDOFF.md).
