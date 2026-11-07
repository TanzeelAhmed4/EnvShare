# Local development guide (Windows PowerShell)

## Prerequisites

- Python compatible with the pinned Django release; use the Python installation already used by this project where possible.
- Node.js/npm compatible with the locked Vite release.
- PowerShell, the project checkout, and the existing local encryption key if the database contains Sensitive variables.

Do not replace the key for an existing database. The `.env.example` files contain configuration placeholders/local settings, not usable credentials. Keep actual `.env` files outside Git.

## Install dependencies

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
cd ..\frontend
npm.cmd ci
```

If this checkout already has `backend\.venv` and `frontend\node_modules`, do not recreate them unless needed. `npm ci` reinstalls locked packages and is not needed for routine startup.

## Configure local backend environment

Copy `backend\.env.example` to a private `backend\.env` only if using a local environment loader, or set variables in the PowerShell process before launching Django. The project settings read process environment values; verify the current setup’s loader behavior before assuming a `.env` file is loaded automatically. At minimum configure local development mode and a strong Django secret key. Configure `ENVSHARE_ENCRYPTION_KEY` as a Base64-encoded 32-byte key.

For a **new, empty local database only**, generate a new key in a private shell using Python and set it in that shell. Never paste the generated value into chat, logs, source control, or a shared terminal transcript. For an existing database, use only its existing key. Losing or replacing that key makes existing Sensitive values unreadable.

The frontend default API URL is `http://localhost:8000/api`; `frontend/.env.example` sets `VITE_API_BASE_URL` to the same local endpoint. Django’s local CORS/CSRF settings must allow the Vite origin `http://localhost:5173`.

## Start both servers

Open two PowerShell terminals from the repository root.

**Terminal 1 — backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open **http://localhost:5173**. The API root is **http://localhost:8000/api/**. Use `localhost` consistently for both browser origins; mixing `localhost` and `127.0.0.1` can affect cookie/CSRF behavior.

## Checks

Backend commands (from `backend/`):

```powershell
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -B manage.py test accounts projects
.\.venv\Scripts\python.exe -B -m pip check
```

Frontend commands (from `frontend/`):

```powershell
npm.cmd test
npm.cmd run check
npm.cmd run build
```

The backend test suite may create a temporary test database. `migrate` changes the local database schema by applying unapplied migrations; inspect migration status first when working with important local data. Do not use `flush`, delete the database, or regenerate the encryption key as routine troubleshooting.

## Troubleshooting

- **Sensitive encryption unavailable:** check that the running Django process has `ENVSHARE_ENCRYPTION_KEY` configured in valid Base64 form decoding to exactly 32 bytes. Do not print the value. Restart Django after changing process environment.
- **Sensitive values fail to decrypt:** verify the existing key is being used. Do not generate a replacement key.
- **CSRF or session errors:** confirm both servers use the documented origins, requests include credentials, and Django allows/trusts the Vite origin.
- **API connection errors:** confirm Django is listening on port 8000 and the effective `VITE_API_BASE_URL` points to its `/api` path; restart Vite after changing its environment.
- **Migration drift:** inspect model and migration history before generating an additive migration. Never reset the database to silence drift.

## Verified in this documentation pass

Safe checks rerun: Django system check, migration dry-run, `pip check`, five frontend session assertions, and TypeScript no-emit validation. The full backend test suite and frontend build were not rerun in this pass; see [project status](PROJECT_STATUS.md) for prior Phase 7 results.
