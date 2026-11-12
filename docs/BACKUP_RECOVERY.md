# Database backup and recovery

EnvShare does not create automatic backups or upload database contents. The examples below describe an operator procedure; **they have not been exercised as a production recovery**. Test them with a disposable database and the intended secret store before relying on them.

## What must be protected

Back up the database and the exact matching `ENVSHARE_ENCRYPTION_KEY`, `ENVSHARE_HISTORY_ENCRYPTION_KEY`, and `DJANGO_SECRET_KEY` as separate protected assets. Restrict access to each, encrypt backups at rest and in transit, define retention, and keep keys in an approved secret-management system rather than with the database dump. `ENVSHARE_ENCRYPTION_KEY` is required for current Sensitive values, Sensitive history, and older Standard v1 history; `ENVSHARE_HISTORY_ENCRYPTION_KEY` is required for new Standard v3 history. Legacy Standard v2 snapshots were derived from the original Django key. Retain that Django key, or provision the dedicated history key with the matching legacy-derived material and verify it before changing the Django key. An authorized operator with the database backup and the matching key material can recover corresponding records.

All three settings are external process configuration and must be backed up independently from the database. A database backup without its matching keys cannot recover the affected ciphertext. Losing or replacing a key makes ciphertext written with that key unreadable; setting a new key does not rotate or recover old data. EnvShare does not implement key rotation or history re-encryption.

Generate the two keys once for a new database using a cryptographically secure 32-byte random value encoded as URL-safe Base64. Store them in separate named entries in the approved secret manager, verify recovery access, and never paste them into repository files, tickets, shell transcripts, logs, or database backups. Do not generate replacement keys for an existing database.

## SQLite local development backup

The local database defaults to `backend\db.sqlite3`. SQLite's online backup API can produce a consistent copy while the source is open. Run from the repository root and choose protected storage outside the repository:

```powershell
$backupDir = Join-Path $env:USERPROFILE 'EnvShareBackups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$sourcePath = (Resolve-Path 'backend\db.sqlite3').Path
$backupPath = Join-Path $backupDir ("envshare-{0}.sqlite3" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
python -c "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()" $sourcePath $backupPath
```

This example writes a local backup; move or copy it to the approved protected backup location. Do not commit it. For local restore, stop Django, preserve the current database separately, copy the selected backup to `backend\db.sqlite3`, verify the configured encryption key, and check migrations before restarting. These restore steps have not been tested as a recovery exercise.

## PostgreSQL backup

Use a PostgreSQL-supported `pg_dump` version compatible with the server. Configure a dedicated least-privilege backup role and a protected password source such as a restricted `PGPASSFILE` or platform-managed credential injection. Do not put passwords in command-line arguments, scripts, shell history, or logs.

The application's `ENVSHARE_DB_*` variables are not automatically read by `pg_dump`. In PowerShell, map the non-password connection settings into libpq variables, using the same approved TLS settings as the application:

```powershell
$env:PGHOST = $env:ENVSHARE_DB_HOST
$env:PGPORT = if ($env:ENVSHARE_DB_PORT) { $env:ENVSHARE_DB_PORT } else { '5432' }
$env:PGUSER = $env:ENVSHARE_DB_USER
$env:PGDATABASE = $env:ENVSHARE_DB_NAME
$env:PGSSLMODE = if ($env:ENVSHARE_DB_SSLMODE) { $env:ENVSHARE_DB_SSLMODE } else { 'require' }
if ($env:ENVSHARE_DB_SSLROOTCERT) { $env:PGSSLROOTCERT = $env:ENVSHARE_DB_SSLROOTCERT }
$backupDir = Join-Path $env:USERPROFILE 'EnvShareBackups'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$dumpPath = Join-Path $backupDir ("envshare-{0}.dump" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
pg_dump --format=custom --file=$dumpPath --dbname=$env:PGDATABASE
```

Use a unique, access-controlled output name and protected storage in operational use. Configure authentication through the protected password mechanism; do not set a literal password in this document or command. Encrypt the dump at rest and restrict transfers and access.

## PostgreSQL restoration

Restore only into a newly provisioned, isolated, access-controlled database during a recovery exercise. Confirm host, port, database, role, PostgreSQL version, TLS, and target before running a restore. Set `PGHOST`, `PGPORT`, `PGUSER`, and protected password/TLS configuration for the restore target, then use a target database that has been intentionally created and is empty:

```powershell
$env:PGDATABASE = 'envshare_restore'
pg_restore --no-owner --dbname=$env:PGDATABASE $dumpPath
```

Do not add destructive cleanup flags or test this against production. Review migration state and apply only the migrations appropriate to the restored application version. Validate database consistency and application reads in isolation before any controlled service cutover. The repository does not provide or verify a production cutover procedure.

## Encryption-key backup and recovery

Store the exact existing `ENVSHARE_ENCRYPTION_KEY` and `ENVSHARE_HISTORY_ENCRYPTION_KEY` in an approved secret manager with access controls and recovery permissions separate from database backup access. Do not put key values in this document, source control, a database dump, a ticket, shell history, or logs. Record non-secret identifiers/versions in the recovery record so operators can select the matching keys without exposing their values.

During recovery, restore the database and retrieve all matching key settings through the approved secret-management process. Supply them to the backend process environment without printing them. Preserve the original `DJANGO_SECRET_KEY` when the database contains legacy Standard `v2` history unless the dedicated history key has already been provisioned with that history's derived material and verified. New `v3` Standard history is independent of Django's key. Start an isolated instance with matching configuration and perform controlled recovery checks without copying plaintext into logs or reports. Do not replace keys if decryption fails; stop and investigate the selected backup/key pair.

## Recovery exercises and operational ownership

Schedule isolated restore exercises. Record the database backup identifier, key reference (not the key), software/migration version, duration, and pass/fail outcome. Protect and retain the restored environment according to the same data-handling rules. A backup is not known to be recoverable until restore and decryption checks have actually succeeded.

Operators remain responsible for backup schedules, encryption, access control, off-site retention, PostgreSQL compatibility, key escrow/recovery, monitoring, retention, incident response, and deletion of expired copies. No production backup or recovery test has been verified for EnvShare.
