# Backup & Restore Runbook

## What gets backed up

Every backup is a single `.bkp.enc` (or `.bkp.tar.gz` if unencrypted)
file containing:

- `manifest.json` - kind, timestamps, row counts, encryption flag
- `data.json` - every table in FK order
- `storage/...` - the entire attachments tree

Files live in `BACKUP_LOCAL_PATH` (default `/var/lib/pug-legal/backups`).

The backup itself is **AES-256-GCM encrypted** when `BACKUP_ENCRYPTION_KEY`
is set (32 raw bytes, base64-encoded). Each file uses a fresh 12-byte
nonce; the magic header is `PUGBKP1\0`.

## On-demand backup

1. Sign in.
2. **Admin -> Backup & Restore**.
3. Add an optional note (`pre-upgrade`, `month-end`, etc.).
4. Click **Create Backup**. The status row appears `Completed` when done
   (a few seconds on a small DB).
5. Click **Verify** - the green banner confirms checksum + decrypt.
6. **Download** to a separate machine so you have an off-host copy.

Equivalent API:

```bash
curl -fsSL -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notes": "manual via runbook"}' \
  https://pug-legal.example.com/api/v1/backups
```

## Scheduled backups (cron)

Until the Phase 10 scheduled-backup loop is enabled, use cron on the
host:

```cron
# /etc/cron.d/pug-legal-backup
30 02 * * * pug curl -fsSL -X POST -H "Authorization: Bearer $(cat /etc/pug-legal/service-token)" -H "Content-Type: application/json" -d '{"notes":"nightly"}' http://127.0.0.1:8000/api/v1/backups >/dev/null
```

Tip: create a long-lived service-account user with `admin:backup`
permission, log in once, and store the access token in
`/etc/pug-legal/service-token` (chmod 600).

## Retention

The current build keeps every backup until you delete it. Add cron pruning:

```cron
# Keep the last 7 daily backups, plus anything from the last 6 months
0 3 * * * pug find /var/lib/pug-legal/backups -name 'backup-*' -type f -mtime +7 -mtime -180 -delete
```

The Backup Policy fields in **Admin -> System Settings -> Backup Policy**
are recorded for future automation.

## Restore from a backup

> Destructive: every table is wiped and replayed. A safety snapshot of
> the *current* state is taken first by default.

1. **Admin -> Backup & Restore**.
2. Click **Verify** on the target backup first - never restore an
   unverified file.
3. Click **Restore** -> the rose modal appears. Leave **safety snapshot**
   ticked. Type `RESTORE` in the confirmation box.
4. Click **Restore Now**. The page reloads with the restored state.
5. Sign in (your old token is invalidated because the users table was
   replaced).

If something goes wrong, restore the safety snapshot that was just
recorded (look for kind `Safety Snapshot` in the list).

## Restore on a fresh host

```bash
# 1. Set up the host per docs/runbooks/deploy.md, but skip the seed step.
# 2. Drop the encrypted bundle into the backups dir
sudo install -o pug -g pug ~/backup-000003-20260619-021500.bkp.enc \
    /var/lib/pug-legal/backups/
# 3. Insert a BackupJob row so the UI can see it. Easier: copy the file
#    name and use the API:
curl -fsSL -X POST -H "Authorization: Bearer $TOKEN" \
    -F file=@backup-000003-20260619-021500.bkp.enc \
    https://pug-legal.example.com/api/v1/backups/import   # Phase 12.1 (TODO)
# 4. Until /import lands, restore the file directly with:
sudo -u pug /opt/pug-legal/backend/.venv/bin/python -c "
from app.db.session import SessionLocal
from app.services import backup_service
from app.models.backup import BackupJob
db = SessionLocal()
job = BackupJob(kind='manual', status='Completed',
    storage_path='backup-000003-20260619-021500.bkp.enc',
    is_encrypted=True, checksum_sha256='...')
db.add(job); db.commit(); db.refresh(job)
backup_service.restore_backup(db, job, take_safety_snapshot=False)
"
```

## Chain integrity

After every restore, walk to **Admin -> Audit Log -> Verify Chain**. A
restore truncates the audit log to whatever was in the snapshot; the
restoring action is then re-appended so the chain continues from there.
