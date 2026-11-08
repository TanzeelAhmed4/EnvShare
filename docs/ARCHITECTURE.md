# EnvShare architecture

## System overview

```text
React + TypeScript client (Vite)
        | HTTP, session cookies, CSRF token
        v
Django URL routing + Django REST Framework views/serializers/permissions
        |                                  |
        |                                  +-- accounts: custom User, sessions, throttles
        |                                  +-- projects: membership, environments,
        |                                      variables, import, audit
        v
SQLite database (the only configured database)

Sensitive variable value -- AES-256-GCM ciphertext at rest
                            key supplied by Django process environment
```

## Applications and configuration

- `backend/accounts/` defines the custom `accounts.User`, registration/login/session endpoints, serializers, and auth throttling.
- `backend/projects/` defines projects, memberships, environments, variables, import parsing/confirmation, AES-GCM encryption, audit events and timeline APIs.
- `backend/config/` sets Django apps/middleware, SQLite, sessions, CSRF/CORS, REST defaults, security flags, and development/test/production configuration validation.
- `frontend/src/` contains the React app, session-aware API client, project workspace, variable/import screens, audit timeline, and CSS. The API base defaults to `http://localhost:8000/api`; `VITE_API_BASE_URL` can override it.

`DJANGO_ENV` accepts `development`, `test`, or `production`. Settings read variables from the process environment; there is no `.env` loader in Django settings. Development uses a deliberately non-production fallback Django secret key unless overridden. Production rejects that fallback and requires a private `DJANGO_SECRET_KEY`, explicit hosts, HTTPS CORS origins, and a valid Base64-encoded 32-byte `ENVSHARE_ENCRYPTION_KEY`. Production mode enables secure cookies, SSL redirect, and HSTS (with subdomain/preload options defaulting off). These checks validate configuration values; they do not supply deployment infrastructure or prove production readiness.

## Data model and permissions

- A `Project` belongs to a creator. `ProjectMembership` represents registered members; unique membership prevents duplicates. Creators administer members. Both creators and members can access project data. There is a single member role.
- A project gets Development, Staging, and Production `Environment` records via a post-save signal. Environment names are unique within a project.
- `EnvironmentVariable` keys are unique per environment and limited to letters, digits, and underscores, starting with a letter or underscore. Classification is Standard or Sensitive. Values are limited to 65,536 characters by the serializer.
- `EnvironmentVariableAuditEvent` keeps action, actor/project/environment snapshots, variable ID/key, `changes`, and timestamp. Its project foreign key cascades on deletion; actor and environment foreign keys may become null while their snapshots remain.
- API endpoints require authentication by default. Project data lookups are scoped through projects visible to the requester. Only the creator can add/list/remove project members. Frontend hiding is not an authorization boundary.

## Authentication and throttling

The client obtains a CSRF token and includes cookies on requests. Registration and login are CSRF-protected; private APIs use Django session authentication. Passwords use Django's configured Argon2-first hasher list. Login's IP request throttle is 5/minute; registration's is 5/hour. Separately, failed passwords share a per-normalized-username counter across IPs: five failures during a 15-minute key lifetime activate a 60-second cooldown. Usernames are normalized with Unicode NFKC, trimming, and lowercase for the failure bucket; the cache key contains an HMAC digest keyed by Django's secret, never the raw username or password. Success deletes the failure and cooldown keys.

The login endpoint resolves case variants using `username__iexact` and then calls Django's normal authentication backend with the stored spelling. Case-insensitive username and non-empty email unique constraints use `Lower`. These ORM operations avoid SQLite-only SQL, but the configured database is SQLite and PostgreSQL behavior has not been runtime-tested. SQLite's case handling and Unicode behavior may differ from PostgreSQL; database-specific behavior should be verified before claiming cross-database parity.

The default cache is local-memory and process-local. Multiple workers will not share throttle counters without a configured shared cache. A target username can be repeatedly locked for 60 seconds after each set of five failures, so username throttling has a denial-of-service tradeoff.

## Sensitive data lifecycle

Standard variable values are stored as plaintext. Sensitive values are encrypted before database persistence using AES-256-GCM, a random 12-byte nonce, and associated data containing the environment ID and variable key. The key comes from `ENVSHARE_ENCRYPTION_KEY`, which must decode from Base64 to 32 bytes. The key is not persisted in the database. Changing the environment ID/key or losing the encryption key prevents decryption; key rotation/recovery is not implemented.

Ordinary variable serializers return a mask for Sensitive values. Reveal is a separate authenticated project-scoped POST operation and only accepts Sensitive variables. The endpoint decrypts, writes a `revealed` audit event with context and an empty changes object, then returns plaintext. It never passes plaintext to the audit helper. If audit persistence fails, a generic 503 is returned and plaintext is withheld. Unauthorized/missing/Standard/decryption-failure paths do not create reveal events. Sensitive values in other audit actions are redacted; audit errors do not include secret values.

## Import and audit flow

The importer accepts simple `KEY=VALUE` lines, ignores blank lines/comments, preserves `=` characters after the first delimiter, and supports matching single or double quotes around a value. It rejects malformed keys, duplicate keys, and unclosed quotes. Preview identifies New, Update, and Unchanged entries. Existing Sensitive values are decrypted only for comparison and remain masked in preview; new Sensitive values are also masked. Existing sensitivity is retained. New keys require a Standard/Sensitive classification. Confirmation requires an explicit flag and a signed, 15-minute token bound to actor, project, environment, input/classifications, and a keyed fingerprint of the current state. Writes and audit entries occur in a transaction.

Create/update/delete/import operations write audit events with safe context and value redaction. Each successful Sensitive reveal writes action `revealed`; `backend/projects/migrations/0004_reveal_audit_action.py` adds this choice to the existing action field after migration `0003_environmentvariableauditevent.py`. No schema column is added. The API serializes event metadata and changes only. Project history is chronological, access-scoped application history; it is not tamper-proof or independently retained.

## Frontend data flow

`authApi.ts` sends credentials and CSRF headers, includes cookies, and reports expired sessions to `App`. `ProjectWorkspace` loads project/member/environment data and holds an audit refresh counter. `EnvironmentVariables` invokes `onAuditChange` after successful variable writes/imports and after successful reveal. Failed reveal skips that callback. `AuditTimeline` reloads when its project ID or refresh token changes and displays the returned metadata. The `AuditEvent` TypeScript union includes `created`, `updated`, `deleted`, and `revealed`.

## Local versus production

Local development runs SQLite, Django's development server, and Vite. The project has no production database adapter/configuration, cache service, infrastructure-as-code, TLS setup, process manager, static-file deployment path, monitoring, backup/restore procedure, or deployment automation. Production settings validation is a guardrail only, not a production deployment implementation.
