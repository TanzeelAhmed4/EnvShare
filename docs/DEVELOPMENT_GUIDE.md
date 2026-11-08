# Local development guide (Windows PowerShell)

## Existing tools in this checkout

This checkout contains the backend virtual environment at `backend\.venv`; its interpreter imports Django 6.1.3. Use it explicitly. The path `backend.venv` at the repository root does not exist. Node dependencies are expected under `frontend\node_modules`; inspect their availability before running npm commands. Do not reinstall packages just to perform routine checks.

## Environment configuration

Django settings read process environment variables directly. They do not load `.env` files. Do not print values while checking configuration, and do not put secrets in command history, source, or shared logs.

For local development, `DJANGO_ENV` defaults to `development`; override it only when needed. Set a private `DJANGO_SECRET_KEY` and, when creating/revealing Sensitive variables, `ENVSHARE_ENCRYPTION_KEY` to Base64 text that decodes to 32 bytes. The development fallback Django key is unsuitable for shared or deployed use. If the database already contains Sensitive values, use the existing encryption key: replacing or losing it makes those values unreadable. Do not generate a replacement key for an existing database.

The backend defaults to SQLite at `backend\db.sqlite3`, CORS/CSRF origin `http://localhost:5173`, and local API port 8000. The frontend API defaults to `http://localhost:8000/api`; set `VITE_API_BASE_URL` in the frontend process only if the API is elsewhere.

## Start the application

From the repository root, in the first PowerShell terminal:

```powershell
.\backend\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

In a second terminal, from the repository root:

```powershell
Set-Location frontend
npm.cmd run dev -- --host localhost --port 5173
```

Open `http://localhost:5173`. Use `localhost` consistently in the browser and API/CORS origins; mixing `localhost` and `127.0.0.1` can affect session/CSRF behavior.

## Backend checks

Run from the repository root with the existing interpreter:

```powershell
.\backend\.venv\Scripts\python.exe -B backend\manage.py test
.\backend\.venv\Scripts\python.exe -B backend\manage.py check
.\backend\.venv\Scripts\python.exe -B backend\manage.py makemigrations --check --dry-run
.\backend\.venv\Scripts\python.exe -B -m pip check
```

Django's test runner uses a test database; checks and migration dry-run are not a substitute for inspecting the local database before applying migrations. To apply migrations intentionally, run `python.exe backend\manage.py migrate` only after reviewing the pending migration list and protecting existing local data. Never use `flush`, delete the database, or rewrite applied migrations to silence drift.

## Frontend checks

Run from `frontend\`:

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run build
```

The current test script runs `tests/authSession.test.mjs` (five response assertions). `check` runs TypeScript project checking. `build` runs TypeScript project build followed by Vite production bundling.

## Production configuration boundary

`DJANGO_ENV=production` requires a private `DJANGO_SECRET_KEY` of at least 50 characters, `DJANGO_ALLOWED_HOSTS` with explicit host names, HTTPS-only `DJANGO_CORS_ALLOWED_ORIGINS`, and a valid Base64-encoded 32-byte `ENVSHARE_ENCRYPTION_KEY`. HSTS duration must be at least one day; preload additionally requires subdomains and a one-year duration. Secure cookies and SSL redirect are enabled. These validations do not configure a production database, shared cache, TLS proxy, static hosting, backups, monitoring, or deployment. The application is not production-ready.

## Troubleshooting

- **Django import error:** invoke the existing interpreter explicitly as `backend\.venv\Scripts\python.exe`; do not assume the active global Python has Django.
- **Encryption unavailable/decryption fails:** check that the process has the correct existing Base64-encoded key configured. Never print or replace it as troubleshooting.
- **CSRF/session errors:** verify origin consistency, credentialed requests, cookie acceptance, and configured CORS/CSRF origins.
- **API connection errors:** confirm Django is listening on port 8000 and `VITE_API_BASE_URL` ends with `/api`; restart Vite after process-environment changes.
- **Vite build fails with `spawn EPERM`:** the frontend TypeScript check can pass while Vite/esbuild cannot start a child process. Run the build in an environment that permits esbuild process startup; do not describe a failed build as successful.
- **Migration drift:** inspect model and migration history, then create a new additive migration only when needed. Do not reset the database.

## Verification record

The latest frontend test and TypeScript commands passed; the latest production build attempt failed at esbuild startup with `spawn EPERM`. The latest backend suite result available is a 79-pass result reported by the independent security review, not rerun during documentation work. The system-Python attempt lacked Django; the actual nested `backend\.venv` interpreter was found and its Django import/version verified during this inspection, but backend tests/checks were not rerun here. Full details are in [PROJECT_STATUS.md](PROJECT_STATUS.md).
