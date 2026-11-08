# EnvShare

EnvShare is a local course project for sharing project environment variables with registered teammates. It combines a Django REST Framework API with a React and TypeScript client. It is intended for local demonstration and course submission; it has not been deployed and is not certified production-ready.

## Implemented features

- Session-based signup, login, logout, current-user lookup, CSRF protection, and Argon2-preferred password hashing.
- Login request limiting by client IP (5 requests per minute), plus a separate failed-password counter keyed by an HMAC of the normalized username (5 failures in 15 minutes, then a 60-second cooldown). Registration is limited to 5 attempts per client IP per hour.
- Case-insensitive username and email uniqueness constraints. Login resolves username case variants with Django's `username__iexact` lookup before invoking Django authentication. This uses Django ORM expressions; PostgreSQL is not configured or runtime-tested in this project.
- Projects with a creator and registered members. Creators manage membership; creators and members can view and edit project data. There are no additional member roles.
- Development, Staging, and Production environments created with each project.
- Standard and Sensitive variables with key validation and per-environment uniqueness. Sensitive values use AES-256-GCM at rest and are masked in ordinary API responses.
- Authorized reveal through a dedicated endpoint. Each successful Sensitive reveal records a `revealed` audit event before returning plaintext. The event records context only and has an empty changes object. If the audit write fails, the API withholds plaintext. Failed, unauthorized, missing, Standard-variable, and decryption-failure requests do not create a reveal event.
- `.env` parsing, preview, and explicit confirmation. New entries require a classification; existing classifications are retained. Sensitive values are masked in previews. The signed preview is bound to the user, project, environment, input, and current variable state and expires after 15 minutes.
- Application audit history for variable create, update, delete, import, and reveal activity. Sensitive before/after values are redacted. The frontend timeline refreshes after a successful reveal.
- Frontend handling for expired authentication sessions.

## Stack and layout

- Backend: Python, Django 6.1.3, Django REST Framework 3.18.3; local database configuration is SQLite.
- Frontend: React 18, TypeScript 5.6, Vite 6.4.5, Tailwind CSS and project styles.
- Key paths: `backend/accounts/`, `backend/projects/`, `backend/config/`, `frontend/src/`, `frontend/tests/`, and `docs/`.
- Migration `backend/projects/migrations/0004_reveal_audit_action.py` adds the `revealed` audit action to the choices for the existing audit action field. It is additive and follows migration `0003_environmentvariableauditevent.py`.

The encryption key is supplied through the Django process environment and is not stored in the database or source. See [the architecture](docs/ARCHITECTURE.md), [development guide](docs/DEVELOPMENT_GUIDE.md), and [project status](docs/PROJECT_STATUS.md).

## Run locally on Windows

This checkout has an existing virtual environment at `backend\.venv`. From the project root, start the backend with:

```powershell
.\backend\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

In a second PowerShell window, run:

```powershell
Set-Location frontend
npm.cmd run dev -- --host localhost --port 5173
```

Open `http://localhost:5173`. Configure required development environment variables in the process before starting Django. Settings read process environment variables; they do not load `.env` files themselves. For details and test commands, see [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md).

## Verification record

The most recent independent security-review report states that all 79 backend tests passed. That result is reported history, not a rerun during the documentation inspection. The latest frontend test and TypeScript commands passed (5 session assertions and `tsc -b --pretty false`). The latest production build attempt failed when esbuild could not spawn (`spawn EPERM`); TypeScript compilation inside the build completed before that failure. The latest Django commands attempted with the active system Python could not import Django. The root-level path `backend.venv` that was requested for a retry does not exist; this inspection found `backend\.venv\Scripts\python.exe` and verified it imports Django 6.1.3, but did not rerun the suite with it. See [PROJECT_STATUS.md](docs/PROJECT_STATUS.md) for the full dated status and limits.

## Important limitations

- No hosted deployment, production database configuration, browser end-to-end suite, password reset, email verification, MFA, or key rotation/recovery is implemented.
- Django is configured to use SQLite. A production database and its operational procedures remain to be selected and verified.
- The default Django cache is process-local. Throttling state is not shared between workers; configure and verify a shared cache such as Redis before multi-worker deployment.
- Username cooldowns can be repeatedly retriggered after expiry by anyone who knows the target username, temporarily denying that account login.
- Preserve and securely back up the existing encryption key. Loss or replacement makes existing Sensitive values unreadable; recovery and rotation are not implemented.
- Production requires HTTPS and explicit secure deployment configuration. Hosting, TLS termination, secret provisioning, backups, monitoring, and deployment automation are not supplied.
- Audit history is application-level, not tamper-proof or independently retained, and project deletion cascades to project audit events.
