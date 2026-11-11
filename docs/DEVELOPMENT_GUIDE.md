# Local development guide (Windows PowerShell)

This guide starts EnvShare with the local SQLite database, Django development server, and Vite. Django settings read process environment variables; Django does not load `.env` files. Vite can load its own `.env` files, but `.env.example` and `.env.production.example` are templates and are not loaded automatically.

## Prerequisites

- Git.
- Python compatible with the pinned Django 6.1.3 dependency. The current Windows checkout was verified with Python 3.14.4.
- Node.js and npm. The current checkout was verified with Node 24.18.0 and npm 11.16.0.
- PowerShell.

Version numbers above describe the verified checkout, not minimum-version guarantees. PostgreSQL and Redis are not needed for SQLite development.

## Clone and install dependencies

From the directory where you keep projects:

```powershell
git clone <repository-url> EnvShare
Set-Location EnvShare
py -3.14 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location frontend
npm ci
Set-Location ..
```

If `py -3.14` is unavailable, install a Python version supported by Django 6.1 and use its launcher option. Keep the virtual environment and `node_modules` out of Git; the repository ignore rules already cover them.

## Configure local environment

Local defaults are `DJANGO_ENV=development`, SQLite at `backend\db.sqlite3`, API port 8000, and CORS/CSRF origin `http://localhost:5173`. The development Django secret fallback is only for local development.

Variable create, update, delete, import, and restore operations write encrypted history snapshots for both Standard and Sensitive classifications. Therefore configure `ENVSHARE_ENCRYPTION_KEY` before variable writes. It must be Base64 text for a 32-byte key. Generate a key once for a new local database, store it outside the repository in a protected local secret store, and set that same value whenever the database is used. Do not replace it for a database that already contains history.

In the PowerShell terminal that will run Django, supply the saved key and optional local overrides:

```powershell
$env:DJANGO_ENV = 'development'
$env:ENVSHARE_ENCRYPTION_KEY = '<your saved Base64-encoded 32-byte development key>'
# Optional overrides:
# $env:DJANGO_SECRET_KEY = '<local-only Django secret>'
# $env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'
# $env:DJANGO_CORS_ALLOWED_ORIGINS = 'http://localhost:5173'
```

The placeholder above is not a usable key. Do not put a real key in this guide, a committed `.env` file, shell transcript, or shared log. If you only need to run the frontend or inspect non-variable pages, the encryption key is not needed; variable writes and history require it.

## Apply migrations and start the backend

From the repository root, in the configured terminal:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py migrate
.\backend\.venv\Scripts\python.exe -B backend\manage.py runserver localhost:8000
```

Keep that terminal open. Django creates the local SQLite database when migrations run. Review migrations and protect any existing local data before applying new ones.

## Start the frontend

Open a second PowerShell terminal from the repository root:

```powershell
Set-Location frontend
npm.cmd run dev -- --host localhost --port 5173
```

Open `http://localhost:5173`. The frontend development API default is `http://localhost:8000/api`. Use `localhost` consistently across browser, CORS, and CSRF origins; switching between `localhost` and `127.0.0.1` can affect cookies and origin checks.

## Run backend checks and tests

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py test
.\backend\.venv\Scripts\python.exe -B backend\manage.py check
.\backend\.venv\Scripts\python.exe -B backend\manage.py makemigrations --check --dry-run
.\backend\.venv\Scripts\python.exe -B -m pip check
```

The complete suite includes SQLite concurrency tests and five PostgreSQL-only tests. Those PostgreSQL tests are skipped when a PostgreSQL test service is unavailable; a SQLite pass does not verify PostgreSQL locking. For PostgreSQL integration, use a dedicated disposable test database with the `ENVSHARE_DB_*` settings below, then run `python backend\manage.py test projects.postgres_tests` from the repository root. Never point tests at production data.

To see migration state before applying changes:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py showmigrations
.\backend\.venv\Scripts\python.exe -B backend\manage.py migrate --plan
```

## Run frontend checks

From `frontend\`:

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run build
```

`test` runs `tests/authSession.test.mjs`; `check` runs TypeScript project checking. `build` runs TypeScript project build then Vite bundling. Every Vite build command requires `VITE_API_BASE_URL` to be an absolute HTTPS URL ending in `/api`, including a build whose Vite mode is overridden. Use an actual public deployment API URL for a production build; reserved example domains and localhost are rejected. Build output goes to `frontend\dist`.

## Database and environment-variable reference

SQLite is the default outside production. Production requires `ENVSHARE_DB_ENGINE=postgresql` and these variables:

- `ENVSHARE_DB_NAME`
- `ENVSHARE_DB_USER`
- `ENVSHARE_DB_PASSWORD`
- `ENVSHARE_DB_HOST`

Optional database settings are `ENVSHARE_DB_PORT` (default `5432`), `ENVSHARE_DB_CONNECT_TIMEOUT` (default `5` seconds), `ENVSHARE_DB_SSLMODE` (development default `prefer`, production default `require`), and `ENVSHARE_DB_SSLROOTCERT`. Production deployments should configure certificate validation such as `verify-full` when supported by the database provider. Set values in the process environment or protected secret store, not in source control.

Production also requires `DJANGO_ENV=production`, `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CORS_ALLOWED_ORIGINS`, `ENVSHARE_ENCRYPTION_KEY`, and `ENVSHARE_CACHE_URL`. See the [production configuration example](../backend/.env.production.example) and [deployment guide](PRODUCTION_DEPLOYMENT.md); never copy its placeholders into a running service.

## Troubleshooting

- **Django import error:** use the virtual-environment interpreter at `backend\.venv\Scripts\python.exe` and install `backend\requirements.txt`.
- **Variable write or decryption fails:** verify the process has the same saved `ENVSHARE_ENCRYPTION_KEY` used when the database history was written. Do not print or regenerate the key to troubleshoot.
- **CSRF/session errors:** check that browser, frontend, and backend use matching hostnames and that cookies are enabled.
- **API connection errors:** confirm Django is listening on port 8000. Set `VITE_API_BASE_URL` only when the development API is elsewhere; restart Vite after changing environment variables.
- **Vite production build rejects the URL:** provide an HTTPS API URL ending in `/api`; local, private/reserved literal IPs, reserved local hostnames, credentials, query strings, and fragments are rejected. Public DNS routing still needs deployment verification.
- **Vite reports `spawn EPERM`:** the sandbox or host may block esbuild child-process startup. TypeScript success alone is not a production build; run Vite in an environment that permits the required process.
- **Migration drift:** inspect model and migration history, then add a new migration only when needed. Do not reset the database or edit applied migrations to silence drift.

## Verification record

The latest recorded results and outstanding infrastructure checks are in [Project status](PROJECT_STATUS.md). PostgreSQL concurrency and Redis shared-cache integration remain pending until run against real services. Production hosting, TLS/proxy behavior, frontend CSP delivery, and backup recovery also require deployment-specific checks.
