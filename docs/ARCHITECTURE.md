# EnvShare architecture

## System overview

```text
React browser app (Vite, TypeScript, Tailwind)
       │ HTTP requests with session cookies and CSRF token
       ▼
Django URL routing ── Django REST Framework views/serializers/permissions
       │                   │
       │                   ├── accounts: custom User, signup, session auth
       │                   └── projects: membership, environments, variables,
       │                                 import, encryption, audit timeline
       ▼
SQLite local database
       ▲
       └── Sensitive values are AES-256-GCM ciphertext; key comes from process environment
```

## Backend

- `backend/config/` contains Django settings, URL routing, production-configuration validation, and ASGI/WSGI entry points.
- `backend/accounts/` retains the custom `accounts.User` model and its original migration. Authentication endpoints use Django sessions and CSRF protection; Argon2 is the preferred password hasher. Phase 7 added case-insensitive username/email constraints through a separate migration.
- `backend/projects/` contains project and membership models, environment/variable models, serializers, endpoints, permission checks, import parsing and confirmation, AES-GCM helpers, audit records/views, and focused tests.
- `backend/db.sqlite3` is the local development/course database. Existing database records and migrations must be preserved.

## Access model

Each project has a creator/owner and registered members. Owners and members can view and edit project variable data. Membership administration is owner-only. Project-scoped API views must check membership for every data endpoint; reveal and audit history are separately permission checked. The UI is not an authorization boundary.

Each project receives exactly three supported environments: Development, Staging, and Production. Variable keys are unique within an environment. Variables are classified Standard or Sensitive.

## Sensitive value handling

Sensitive plaintext is encrypted before persistence with AES-256-GCM using a random nonce and associated data bound to the environment/key. The key is read from `ENVSHARE_ENCRYPTION_KEY` in the running Django process, parsed and validated as a 32-byte key. It is not stored in the database or source. Ordinary API responses return masked Sensitive values; a separate authenticated, authorized reveal operation returns plaintext only when requested. Logs, exceptions, import previews, and audit records must not include Sensitive plaintext.

Changing or losing the key prevents decryption of existing ciphertext. Key rotation and recovery are not implemented. Do not replace the current key or store it in this repository.

## Import and audit flow

`.env` parsing ignores blank lines and comments, retains equals signs in values, handles supported whitespace/quoted forms, and reports invalid lines. Preview compares parsed pairs with the selected environment as New, Update, or Unchanged. Existing classifications are retained; new keys require a classification. A confirmation request is required to persist changes, and preview data is protected by an expiring signed fingerprint token. Import writes and its audit entries are transactional.

Variable create, update, and delete operations write audit events with project, environment, key, actor, action, and timestamp. Before/after details are recorded only when safe; Sensitive values are redacted. The timeline is chronological and access-scoped. Audit history is application-level, not tamper-proof, and project deletion cascades to the associated events.

## Frontend

`frontend/src/` holds the React entry point, application state and screens, authentication/session helpers, project API calls, project/member workspace, environment/variable/import UI, audit timeline, and styles. The API base defaults to `http://localhost:8000/api` and may be overridden by `VITE_API_BASE_URL`. Requests include credentials; mutation requests obtain/use CSRF protection.

## Local runtime versus deployment

Local development uses SQLite, Django session cookies, and a Vite dev server. Production settings require explicit configuration and secure transport settings, but hosting, database operations, domain topology, secret provisioning, backups, monitoring, and deployment automation have not been implemented or verified. Do not infer production readiness from configuration checks.
