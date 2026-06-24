# On-Call Runbook

A first-responder cheat sheet. Each row tells you what to look at and
what to do in the first 5 minutes.

## Quick checks

```bash
# 1. Health
curl -fsSL https://pug-legal.example.com/api/v1/health | jq .

# 2. Diagnostics (requires admin token)
curl -fsSL -H "Authorization: Bearer $TOKEN" \
  https://pug-legal.example.com/api/v1/diagnostics | jq .

# 3. Service status (direct deploy)
sudo systemctl status pug-backend pug-frontend nginx postgresql redis
journalctl -u pug-backend -n 200 --no-pager
journalctl -u pug-frontend -n 200 --no-pager

# 4. Docker compose deploy
sudo docker compose -f /etc/pug-legal/docker-compose.yml ps
sudo docker compose -f /etc/pug-legal/docker-compose.yml logs --tail=200 backend
```

## Symptom map

| Symptom | First check | Likely cause | Fix |
|---|---|---|---|
| `502 Bad Gateway` from nginx | `systemctl status pug-backend` | backend crashed / OOM | `systemctl restart pug-backend` |
| Login fails for everyone | journal `pug-backend` for `JWT`/`secret` errors | `APP_SECRET_KEY` changed | restore previous key from `/etc/pug-legal/.env` |
| Login throttled | response is `429` | rate-limit hit (10/min default) | wait 1 min; raise `RATE_LIMIT_LOGIN_PER_MINUTE` if legitimate |
| Notification emails not arriving | Diagnostics shows SMTP `Sent` but recipient inbox empty | spam filter, wrong DNS / SPF | check **Admin -> Email Log**, send test |
| Audit chain fails verification | Audit page red banner | someone edited a row directly | restore latest backup OR document the tamper (don't repair) |
| Backup creation fails | `error` field in `BackupJob` row | disk full / FS permissions | `df -h`, check `/var/lib/pug-legal/backups` ownership |
| Scheduler not firing | Diagnostics shows `Scheduler: Fail` | backend was hot-restarted but scheduler lock stuck | `systemctl restart pug-backend` |
| Cases stuck at a stage | Approvals inbox empty for the configured signatory | wrong user assigned on the form | open the case, edit signatory, resubmit |
| Slow page loads | nginx access log shows long `upstream_response_time` | DB lock / runaway query | `psql -U pug_legal -c 'SELECT pid, query, state, query_start FROM pg_stat_activity WHERE state != ''idle'' ORDER BY query_start;'` then `pg_cancel_backend(pid)` |

## Escalation

1. **Capture context**: timestamp, env, user reporting, screenshot, last
   100 lines of `journalctl -u pug-backend`.
2. **Open a backup**: trigger an emergency backup via the UI.
3. **Notify**: post in `#pug-legal-oncall` Slack channel with the
   capture above.
4. **Roll back** only as a last resort - restore from the latest verified
   backup using `docs/runbooks/backup-restore.md`.

## Useful psql snippets

```sql
-- Open cases at risk (SLA-breached)
SELECT case_no, current_stage, sla_due_at
FROM cases
WHERE status IN ('Submitted','In Review') AND sla_due_at < now()
ORDER BY sla_due_at;

-- Latest audit log row
SELECT id, created_at, actor_email, action, entity_type, summary
FROM audit_log ORDER BY id DESC LIMIT 10;

-- Disk usage of attachments
SELECT pg_size_pretty(pg_database_size(current_database()));
```
