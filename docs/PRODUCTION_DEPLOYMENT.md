# Production deployment guide

This guide documents the production settings and application boundaries present in the repository. It does not provision infrastructure or certify a deployment. PostgreSQL and Redis integration, TLS/proxy behavior, static hosting, monitoring, and recovery must be tested in the selected environment.

## Configuration and secret provisioning

Django reads process environment variables; it does not load `.env` files. `backend/.env.production.example` is a placeholder template only. Do not load it as a real configuration file or copy its placeholder values into a service. Supply the values below through a protected deployment secret/configuration mechanism and restrict access to them.

Required application settings:

- `DJANGO_ENV=production` and `DJANGO_DEBUG=false`.
- `DJANGO_SECRET_KEY`: a private value of at least 50 characters. Production validation rejects known development keys and obvious placeholders. Never reuse a sample value.
- `DJANGO_ALLOWED_HOSTS`: explicit host names; wildcard hosts are rejected.
- `DJANGO_CORS_ALLOWED_ORIGINS`: comma-separated exact HTTPS origins without paths, credentials, query strings, or fragments. The same list configures Django's trusted CSRF origins.
- `ENVSHARE_ENCRYPTION_KEY`: the existing Base64-encoded 32-byte AES key. Keep it stable for all current and historical encrypted values. It is not stored in the database. Do not replace it as a deployment step.
- `ENVSHARE_CACHE_URL`: a `redis://` or `rediss://` URL. Production uses Redis as Django's default cache for API throttles, admin throttling, and readiness checks.

Required production database settings:

- `ENVSHARE_DB_ENGINE=postgresql`
- `ENVSHARE_DB_NAME`, `ENVSHARE_DB_USER`, `ENVSHARE_DB_PASSWORD`, and `ENVSHARE_DB_HOST`

Optional database settings include `ENVSHARE_DB_PORT` (default `5432`), `ENVSHARE_DB_CONNECT_TIMEOUT` (default `5` seconds), `ENVSHARE_DB_SSLMODE` (production default `require`), and `ENVSHARE_DB_SSLROOTCERT`. Prefer `verify-full` with the provider's trusted CA where available. `require` encrypts transport but does not verify server identity. Do not put database passwords on command lines.

Other optional settings include `DJANGO_SECURE_HSTS_SECONDS` (default one day), `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` (default false), `DJANGO_SECURE_HSTS_PRELOAD` (default false), `DJANGO_SESSION_COOKIE_AGE` (default one hour), `DJANGO_TRUST_PROXY_SSL_HEADER` (default false), and `ENVSHARE_LOG_LEVEL` (default `INFO`). Enabling HSTS subdomains or preload affects every relevant hostname; enable only after reviewing the domain and HTTPS coverage.

Email is disabled by default. To enable SMTP, configure `ENVSHARE_EMAIL_ENABLED=true`, `EMAIL_HOST`, `EMAIL_PORT`, `DEFAULT_FROM_EMAIL`, and one appropriate TLS/SSL mode; set `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` together if authentication is required. SMTP configuration does not send invitations: invitation email delivery is not implemented.

## Validate settings and select the production entry point

Install the pinned backend requirements, provide the environment above, then run from the repository root:

```powershell
python backend\manage.py validate_production
python backend\manage.py migrate --check
python backend\manage.py collectstatic --noinput
```

`validate_production` requires `DJANGO_ENV=production`; settings validation runs on import and Django deployment checks follow. These commands do not prove that remote services, certificates, proxy behavior, email, or recovery work. Review the migration plan and a current backup before applying migrations as a deliberate release operation.

Run a production WSGI server with the application target `config.production_wsgi:application`, or an ASGI server with `config.production_asgi:application`. The repository does not pin or configure a WSGI/ASGI process server. The production entry points require `DJANGO_ENV=production` and load the validated production settings. Do not use Django's development server in production. Default `config.wsgi` and `config.asgi` reject non-production server startup; local `manage.py runserver` remains the SQLite development path.

## Database, Redis, and TLS

Production settings reject SQLite and insecure PostgreSQL SSL modes. They configure PostgreSQL using the `ENVSHARE_DB_*` variables, connection timeout, health checks, and persistent connections. Test migrations, row locking, concurrency, backup, and restore against a disposable PostgreSQL service before production use. Five PostgreSQL-specific tests were skipped in the latest recorded local suite because PostgreSQL was unavailable; local SQLite results are not PostgreSQL verification.

Redis is required by production settings. Use a protected Redis URL, preferably `rediss://` when supported, and test the configured cache across all application workers. The latest local checks had no Redis service available, so shared-cache behavior remains pending.

Terminate public TLS at a trusted load balancer or reverse proxy and prevent untrusted direct access to the application origin. Production enables HTTPS redirects, secure session and CSRF cookies, and HSTS. Sessions default to one hour and `SESSION_SAVE_EVERY_REQUEST=true`, so their expiry rolls forward during activity. Session and CSRF cookies are Secure, HttpOnly as configured, and `SameSite=Lax`.

If Django must interpret `X-Forwarded-Proto`, set `DJANGO_TRUST_PROXY_SSL_HEADER=true` only when the trusted proxy removes any client-provided header and writes the authoritative value. The application does not validate proxy source IPs. Test redirects and cookie behavior through the actual TLS proxy, not only against Django directly.

## CORS and CSRF

Use the exact HTTPS browser origin in `DJANGO_CORS_ALLOWED_ORIGINS`; the setting also supplies CSRF trusted origins. Credentialed requests and the CSRF header are required. Prefer a same-site frontend/API arrangement: `SameSite=Lax` cookies are not sent on cross-site fetches between unrelated sites. Do not address that topology by permitting broad CORS. A different cookie/CSRF design would need deliberate review.

## Frontend build, static files, and CSP

Build from `frontend\` with `VITE_API_BASE_URL` set to the real public HTTPS API URL ending in `/api`:

```powershell
Set-Location frontend
$env:VITE_API_BASE_URL = 'https://api.your-domain.com/api'
npm.cmd run build
```

The build guard applies to all Vite build modes. It rejects credentials, query strings, fragments, reserved local hostnames, and private/reserved IP literals. It cannot verify where a public hostname resolves; check DNS and routing in the target deployment. The built React app is in `frontend\dist`; host it on HTTPS. Vite does not load the `.env.production.example` filename; provide the variable through the build environment or a Vite-recognized configuration source.

If Django static assets are used, `collectstatic` writes to `backend\staticfiles`; configure the selected web server/static service to serve them. This repository does not configure a static host or reverse proxy.

Django's middleware sets a restrictive CSP on Django responses. If the React app is served separately, its static host must set its own CSP response header; an API response header does not protect the frontend document. Add only the exact API origin to the app's `connect-src` when needed. Test the delivered headers in a browser. Do not add `unsafe-inline` or `unsafe-eval` without a reviewed requirement.

## Health, logs, and operations

- `/health/live/` reports process liveness only.
- `/health/ready/` checks the database and configured default cache and returns 503 when a dependency check fails. Configure dependency-aware load balancer/orchestrator probes to use this endpoint; `/api/` is not a readiness probe.
- Production Django logs are structured and the application redacts recognized credential-shaped fields. Do not log request bodies, cookies, authorization headers, environment dumps, or variable values. Configure proxy/host access logs, retention, monitoring, alerts, and incident response separately.
- Set up TLS certificate renewal, PostgreSQL/Redis availability monitoring, log retention, static hosting, and operator access controls. None is provided by the repository.

## Backup and recovery

EnvShare does not create automatic backups. Back up the PostgreSQL database and the matching `ENVSHARE_ENCRYPTION_KEY` separately, with restricted access and a recovery plan. Database-only recovery cannot decrypt Sensitive current values or historical snapshots without the corresponding key. Replacing the key is not key rotation and makes existing ciphertext unreadable. See [Backup and recovery](BACKUP_RECOVERY.md); the documented procedures have not been exercised against production infrastructure.

## Deployment verification checklist

Before describing a deployment as ready, operators should:

1. Validate configuration and startup using the production entry point and secret store.
2. Apply reviewed migrations to a backed-up, disposable PostgreSQL environment; run `python backend\manage.py test projects.postgres_tests` and check `verify-full` TLS where available.
3. Exercise Redis-backed throttling and readiness with the intended number of workers.
4. Test HTTPS redirect, trusted proxy handling, cookies, CORS/CSRF, allowed hosts, and public DNS/routing through the real proxy.
5. Verify the React static host serves CSP and other required headers and that the frontend reaches the intended API.
6. Confirm liveness and readiness probes, structured logs, redaction, retention, alerts, and incident-response ownership.
7. Restore a database backup and its matching encryption key in an isolated environment, then verify representative data and controlled decryption.
8. Test SMTP only if it is enabled. Invitation mail delivery remains unimplemented.

These infrastructure checks are pending. The code-level settings and local test results are not a production certification.
