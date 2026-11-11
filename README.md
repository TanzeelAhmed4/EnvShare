# EnvShare – Team Environment Variable Manager

EnvShare is a web app for teams to organize project environment variables by environment. It gives collaborators controlled access to shared configuration, masks Sensitive values in normal views, and records changes for review.

## Features

- Session-based registration, login, logout, and CSRF-protected API requests.
- Private projects with Owner, Admin, Manager, and Member roles.
- Development, Staging, and Production environments for each project.
- Standard and Sensitive variables, with AES-GCM encryption for Sensitive values at rest and authorized reveal.
- Encrypted version snapshots for both classifications, with history, comparison, and restoration. Deleted-variable history is retained internally but is unavailable through normal API routes.
- Single-use, expiring, email-bound team invitations. Invitation email delivery is not implemented.
- `.env` import preview with New, Update, and Unchanged results, followed by explicit confirmation.
- Project, membership, variable, import, and authentication audit events, with project-scoped filters and server-side pagination.

## Roles

| Role | Project permissions |
|---|---|
| Owner | Full project control, including assigning Admins, managing all memberships, and deleting the project. The owner is represented by `Project.creator`. |
| Admin | Manage project data and invitations; manage Managers and Members. Admins cannot change the Owner or manage another Admin. |
| Manager | Create, edit, import, delete, reveal, and review project variables and audit history. Cannot manage membership. |
| Member | View project variables and audit history. Sensitive values remain masked without reveal permission. |

## Technology and architecture

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS.
- **Backend:** Python, Django 6.1, Django REST Framework.
- **Data:** SQLite for local development; environment-configured PostgreSQL support.
- **Security:** Django sessions and CSRF protection; AES-256-GCM encryption; role checks on backend endpoints; rate limiting; audit events; production security settings and health endpoints.

The browser app calls the Django REST API using session cookies and a CSRF token. The backend applies project membership permissions, stores project and environment data, and uses the configured database. Sensitive current values and all historical snapshots are encrypted with a Base64-encoded 32-byte key supplied to the backend process. Standard current values are stored as plaintext. See [Architecture](docs/ARCHITECTURE.md) for data flows and security boundaries.

## Local setup

The commands below use Windows PowerShell. See the [development guide](docs/DEVELOPMENT_GUIDE.md) for prerequisites, environment setup, migration instructions, and troubleshooting.

From the repository root, start Django:

```powershell
.\backend\.venv\Scripts\python.exe backend\manage.py migrate
.\backend\.venv\Scripts\python.exe backend\manage.py runserver localhost:8000
```

In a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev -- --host localhost --port 5173
```

Then open `http://localhost:5173`. Django reads process environment variables; it does not load `.env` files. Preserve the same `ENVSHARE_ENCRYPTION_KEY` for the lifetime of a database containing variable history.

## Tests and checks

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py test
.\backend\.venv\Scripts\python.exe -B backend\manage.py check
.\backend\.venv\Scripts\python.exe -B backend\manage.py makemigrations --check --dry-run
```

From `frontend\`:

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run build
```

The latest recorded local run discovered 139 backend tests: 134 passed and 5 PostgreSQL-specific tests were skipped. Frontend tests, TypeScript validation, Django checks, migration consistency, and Vite production bundling passed; see [Project status](docs/PROJECT_STATUS.md) for the conditions and limitations of those checks.

## Configuration and deployment

See [Local development](docs/DEVELOPMENT_GUIDE.md), [Production deployment](docs/PRODUCTION_DEPLOYMENT.md), and [Backup and recovery](docs/BACKUP_RECOVERY.md). Production configuration requires PostgreSQL, Redis, explicit secrets and origins, and a production WSGI/ASGI entry point. These settings do not make a deployment production-certified.

## Known limitations and status

- PostgreSQL concurrency tests have not run against a real PostgreSQL service; Redis shared-cache behavior has not been integration-tested.
- Hosting, TLS termination, proxy behavior, frontend-host CSP, monitoring, and recovery procedures require deployment-specific verification.
- There is no MFA, password reset, email verification, invitation email delivery, encryption-key rotation/recovery, browser E2E suite, or independent append-only audit store.
- Database operators can alter audit rows. Losing or replacing the encryption key makes encrypted current/history values unreadable.
- Username cooldowns can be repeatedly retriggered for a known account, temporarily preventing login.

**Project status:** Batches 1–4 and the final security fixes are implemented locally. EnvShare is **not production-certified**. PostgreSQL and Redis integration verification and deployment-level checks remain pending.
