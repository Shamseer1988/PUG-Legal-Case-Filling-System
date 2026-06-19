# Testing Phase 0 on Windows

This guide walks you through running and verifying the Phase 0 scaffolding on a
Windows machine using **PowerShell** (no WSL, no Docker required).

> If you prefer WSL / Git Bash, use the existing `scripts/setup.sh`,
> `scripts/dev-backend.sh`, `scripts/dev-frontend.sh` instead.

---

## 1. Prerequisites

Install these once. Direct download links are official.

| Software       | Version    | Where                                                             |
|----------------|------------|-------------------------------------------------------------------|
| Git            | latest     | https://git-scm.com/download/win                                  |
| Python         | **3.12.x** | https://www.python.org/downloads/windows/ (tick *Add to PATH*)    |
| Node.js LTS    | **20.x**   | https://nodejs.org/                                               |
| PostgreSQL     | **16.x**   | https://www.postgresql.org/download/windows/                      |
| Redis          | **7.x**    | https://github.com/redis-windows/redis-windows/releases (or Memurai) |

Verify in a new PowerShell:

```powershell
git --version
py -3.12 --version
node --version
npm --version
psql --version
redis-cli ping        # should print: PONG
```

---

## 2. Get the code

```powershell
cd C:\Projects
git clone https://github.com/Shamseer1988/PUG-Legal-Case-Filling-System.git
cd PUG-Legal-Case-Filling-System
git checkout claude/cool-allen-z3h6hb
```

---

## 3. Create the database

Open *SQL Shell (psql)* or PowerShell:

```powershell
psql -U postgres
```

Inside psql:

```sql
CREATE DATABASE pug_legal;
\q
```

If your postgres password is not `postgres`, edit `backend\.env` later
(`DATABASE_URL=...`).

Make sure Redis is running:

```powershell
# In a separate terminal
redis-server
# Test from another window:
redis-cli ping     # → PONG
```

---

## 4. One-time setup

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

This will:
- create `backend\.venv` (Python 3.12)
- install backend dependencies (FastAPI, SQLAlchemy, Alembic, etc.)
- copy `backend\.env.example` → `backend\.env`
- run `alembic upgrade head` against your local Postgres
- install frontend dependencies (`npm install`)
- copy `frontend\.env.example` → `frontend\.env.local`
- create `storage\`, `backups\`, `logs\` folders

> If `alembic upgrade head` warns, open `backend\.env` and fix
> `DATABASE_URL`, then re-run inside `backend\`:
> `.\.venv\Scripts\Activate.ps1; alembic upgrade head`

---

## 5. Run the apps (two PowerShell windows)

**Window 1 — backend**

```powershell
.\scripts\dev-backend.ps1
```

Expected output ends with:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Window 2 — frontend**

```powershell
.\scripts\dev-frontend.ps1
```

Expected output ends with:

```
   ▲ Next.js 14.x
   - Local:        http://localhost:3000
 ✓ Ready in ~1.5s
```

---

## 6. Verify Phase 0 is working

Run these checks **in order**.

### 6.1 Backend root
Open http://127.0.0.1:8000/

Expect JSON:
```json
{
  "app": "PUG Legal Case Control System",
  "version": "0.1.0",
  "docs": "/docs",
  "health": "/api/v1/health"
}
```

### 6.2 Health endpoint
Open http://127.0.0.1:8000/api/v1/health

Expect:
```json
{ "status": "ok", "app": "...", "version": "0.1.0", "time": "..." }
```

### 6.3 DB health
Open http://127.0.0.1:8000/api/v1/health/db

Expect:
```json
{ "status": "ok", "component": "database" }
```
If you get an error here, your `DATABASE_URL` is wrong or Postgres is down.

### 6.4 OpenAPI / Swagger
Open http://127.0.0.1:8000/docs

You should see the auto-generated Swagger UI listing `health` endpoints.

### 6.5 Frontend landing page
Open http://127.0.0.1:3000

Expect:
- **PUG** gold circle logo + "Paris United Group Holding" banner in navy/gold
- A green **status pill** showing `ok · v0.1.0` (means the frontend is talking
  to the backend)
- The 13-phase delivery checklist (Phase 0 marked Done, others Pending)
- A **moon / sun toggle** in the top-right — clicking it switches light/dark

If the status pill shows **Offline** (red), the backend isn't running on
`127.0.0.1:8000` or `NEXT_PUBLIC_API_URL` is set differently — check
`frontend\.env.local`.

### 6.6 Backend tests
In a **third** PowerShell window:

```powershell
cd C:\Projects\PUG-Legal-Case-Filling-System\backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

Expect:
```
..                                                                       [100%]
2 passed in 0.x s
```

### 6.7 Lint
```powershell
# backend
cd backend
.\.venv\Scripts\Activate.ps1
ruff check .

# frontend
cd ..\frontend
npm run lint
npm run type-check
```

All three should exit clean.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `py: command not found` | Re-install Python 3.12 and tick "Add python.exe to PATH". |
| `Activate.ps1 cannot be loaded` | Run PowerShell once as Admin: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| `alembic` says `connection refused` | Start the **postgresql-x64-16** service from Services.msc, or fix `DATABASE_URL` in `backend\.env`. |
| Health page works but `/health/db` errors | Bad DB URL, wrong password, or DB `pug_legal` not created. |
| Frontend pill stays **Offline** | Backend not running, or CORS — confirm `CORS_ORIGINS` includes `http://127.0.0.1:3000`. |
| `redis-cli ping` hangs | Redis not running — start `redis-server` in its own window or install **Memurai** (Redis-compatible Windows service). |
| Port 8000 / 3000 already in use | `netstat -ano \| findstr :8000` then `taskkill /PID <pid> /F`. |
| `npm install` SSL errors behind proxy | `npm config set strict-ssl false` (corporate proxy only). |

---

## 8. Phase 1 — Auth, RBAC, Masters

After running migrations, also seed the default admin + roles + sample masters:

```powershell
.\scripts\seed.ps1
```

Then:

1. Open http://127.0.0.1:3000 — you should be redirected to the login screen.
2. Sign in with `admin@pug.local` / `Admin@123`.
3. You land on **/dashboard** with the sidebar showing **Workspace**,
   **Transactions** (placeholders), **Masters**, and **Admin**.
4. Open each Masters page (Divisions, Banks, Customers, Salesmen, Lawyers,
   Case Types) — create, edit, delete rows. Required validation surfaces
   server-side errors as red banners.
5. Open **Admin > Users** — create a new user, assign a role and divisions.
   Sign out, sign in as the new user, and confirm the sidebar hides items
   they don't have permission for.
6. Open **Admin > Roles & Permissions** — view the 9 system roles. Try
   creating a custom role and assigning permissions like `cases:read`,
   `masters:write`, or `*`.

### Phase 1 API endpoints (Swagger)

http://127.0.0.1:8000/docs lists every endpoint:

- `POST /api/v1/auth/login` — returns access + refresh JWTs
- `POST /api/v1/auth/refresh`
- `GET  /api/v1/auth/me`
- `GET/POST/PATCH/DELETE /api/v1/users`
- `GET/POST/PATCH/DELETE /api/v1/roles`
- `GET/POST/PATCH/DELETE /api/v1/masters/{divisions|banks|customers|salesmen|lawyers|case-types}`

All `/users`, `/roles` and `/masters` routes require the matching permission
(`users:read`, `masters:write`, etc.). The Admin role and any user flagged
`is_super` bypass permission checks.

---

## 9. Phase 2 - Legal Case Entry Form

After Phase 1 setup:

1. `.\scripts\setup.ps1` to pull new deps and run migration `0002_phase2_cases`.
2. Open the app, sign in as admin.
3. **Masters** -> **Customers** -> add at least one (e.g. code `C001`,
   name "Acme Trading", division Head Office).
4. Sidebar -> **Transactions** -> **Cases** -> click **New Case**.
5. Fill the form:
   - Tick **Criminal** or **Civil** (Both ticks them together)
   - Pick a Customer, Division, Salesman, Bank
   - Enter Actual Due / Legal Filing amounts and Deposit Date
   - Click **+ Add Cheque** to add multiple cheques (number, bank,
     amount, date, type, bounce reason)
   - Pick signatories (Sales Mgr, Div Mgr, Auditor, FM, ED, Chairman,
     Lawyer)
6. Click **Save Draft** -> the page reloads as `/cases/{id}` and the
   case number `PUG-LEGAL-2026-0001` is assigned.
7. Use **Attach Files** to upload supporting docs. Files land in
   `storage\cases\<id>\` and can be downloaded or removed.
8. Click **Print** in the action bar -> a new tab opens the branded
   A4 print view (PUG navy/gold header, signatory grid). Use the
   browser's Print dialog (Ctrl+P) to print or save as PDF.
9. Click **Save & Submit** -> status switches to `Submitted` and the
   form locks. Editing/deleting Drafts is allowed; Submitted is not.

API endpoints visible at http://127.0.0.1:8000/docs:

- `GET/POST /api/v1/cases`
- `GET/PATCH/DELETE /api/v1/cases/{id}`
- `POST /api/v1/cases/{id}/submit`
- `POST/DELETE /api/v1/cases/{id}/attachments[/{att_id}]`
- `GET /api/v1/cases/{id}/attachments/{att_id}/download`
- `GET /api/v1/cases/{id}/print` (HTML)

Run `pytest -q` -> 5 tests pass (auth + cases).

---

## 10. Phase 3 - Approval Workflow

After running migration `0003_phase3_workflow`:

1. Create a case (Phase 2 flow) and `Save & Submit`.
2. Open the case detail page (`/cases/{id}`) - you now see the
   **Workflow** flow strip at the top showing each stage as a chip
   (Accountant -> Sales Manager -> Division Manager -> Audit ->
   Finance Manager -> Executive Director -> Chairman / MD -> Lawyer).
   The current stage glows gold; completed stages are green ticks.
3. Below the strip is the **History** log with one row per
   transition (submitted, approved, etc.) - actor, timestamp,
   comment.
4. The **Actions at <stage>** card offers:
   - **Approve** -> advances to the next stage
   - **Request Clarification** (comment required) -> status becomes
     "Clarification Requested" and the case returns to Accountant
   - **Reject** (comment required) -> terminal "Rejected"
5. As the Accountant on a clarification-requested case, the actions
   card shows **Resubmit** instead, returning the case to the stage
   that asked the question.
6. Open the sidebar **Approvals Inbox**:
   - Lists every case waiting for a stage you can act on
   - Toggle **Assigned to me only** to filter by the user picked as
     that stage's signatory on the entry form
   - Overdue cases show a red badge (SLA hours: 24-72 per stage)
7. The default admin (super) can act at every stage, so you can drive
   a case through the whole chain with one login.

### Phase 3 API endpoints

- `POST /api/v1/cases/{id}/transition` body `{action,comment}` -
  actions: `approve` | `reject` | `request_clarification` | `resubmit`
- `GET /api/v1/cases/{id}/timeline`
- `GET /api/v1/approvals/inbox`
- `GET /api/v1/approvals/workflow` - stage descriptor (used by UI)

Run `pytest -q` - 9 tests pass (auth + cases + workflow).

---

## 11. Phase 4 - Court Filing, Hearings, Cash Requests

After running migration `0004_phase4_court`:

1. Create a case and walk it through the full approval chain (admin can act
   at every stage). Once Chairman / MD approves, status becomes
   **Approved** and three new panels appear at the bottom of the case
   page: **Court Filing**, **Hearings**, **Cash Requests & Expenses**.

2. **Court Filing**:
   - Click **Record Filing**
   - Enter Police Case No. (e.g. `POL/2026/12345`), Court Case No.
     (`COURT/2026/9876`), filed court, filed date, notes
   - Save -> case status flips to **Filed**, and the timeline gets a
     `court_filed` entry. Use the case **Attachments** section to
     upload the govt acknowledgement scan.

3. **Hearings**:
   - **Add Hearing** -> date/time, type, location, outcome, optional
     next-hearing date
   - The row shows on the case and on the sidebar **Hearings Calendar**

4. **Cash Requests & Expenses**:
   - Lawyer flow: **Request Cash** -> amount + purpose -> status `Requested`
   - FM flow: **Approve** (optional comment) or **Reject** (reason required)
   - Accountant flow: **Pay** with a payment reference -> status `Paid`
   - The header pill shows live totals (Paid / Approved / Open count)

5. **Sidebar Hearings Calendar** (`/hearings`):
   - Lists hearings + next-hearing dates within 30/60/90/180-day range
   - Grouped by date with case-no, type, location

6. **Sidebar Cash Requests** (`/cash-requests`):
   - Cross-case inbox filtered by status (default Requested)
   - Approve / Reject / Pay actions from here too

API endpoints visible at http://127.0.0.1:8000/docs:

- `GET/POST/PATCH /api/v1/cases/{id}/court-filing`
- `GET/POST/PATCH/DELETE /api/v1/cases/{id}/hearings[/{hid}]`
- `GET /api/v1/cases/{id}/spend-summary`
- `GET/POST /api/v1/cases/{id}/cash-requests`
- `GET /api/v1/cash-requests?only=...`
- `POST /api/v1/cash-requests/{id}/{approve|reject|pay}`
- `GET /api/v1/hearings/calendar?days=60`

Run `pytest -q` -> 13 tests pass (auth + cases + workflow + court).

---

## 12. Phase 5 - Notifications & Email Log

After running migration `0005_phase5_notifications`:

1. **SMTP**: leave `SMTP_HOST` blank in `backend\.env` for console mode
   (everything is logged in the EmailLog as `Sent` but not actually
   delivered). To send real emails, fill SMTP_HOST/PORT/USERNAME/PASSWORD
   and set SMTP_USE_TLS=true.

2. Sign in as admin and create a new case. Pick yourself as Sales
   Manager (so you get notified). Save & Submit.

3. Topbar **bell icon** in the right corner shows a red badge with the
   unread count. Click it -> dropdown lists notifications.
   Click a notification -> jumps to the case and marks it read.
   Click **Mark all read** to clear all.

4. Walk the case through stages. Each approval fires a notification to
   the next stage's assigned user (if one was selected on the form).
   Reject / Request Clarification notify the case creator.

5. After Chairman/MD approval, record a court filing -> the FM is
   notified. Create a cash request -> FM is notified. Approve it -> the
   accountant is notified. Pay it -> the lawyer is notified.

6. Sidebar **Admin -> Email Log** lists every outbound message with:
   - Status pill (Sent / Queued / Failed / Bounced)
   - Subject, recipients, event tag, attempts
   - **Preview** opens the rendered branded HTML in a modal iframe
   - **Resend** re-attempts delivery

### Phase 5 API endpoints

- `GET /api/v1/notifications?only_unread=&limit=`
- `GET /api/v1/notifications/unread-count`
- `POST /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`
- `GET /api/v1/admin/email-log?only=Sent|Failed|...`
- `GET /api/v1/admin/email-log/{id}`
- `GET /api/v1/admin/email-log/{id}/preview` (HTML)
- `POST /api/v1/admin/email-log/{id}/resend`
- `POST /api/v1/admin/email-log/bounce` (super only)

Run `pytest -q` -> 17 tests pass.

---

## 13. Phase 6 - Reports + Excel / PDF / Print

1. Sidebar **Insights -> Reports** lists 6 reports. Click **Case
   Register**.
2. Adjust the parameters (Status / Created From / Created To) and click
   **Run** -> a branded table renders with row counts in the footer.
3. **Excel** downloads `.xlsx` with: PUG navy title bar, gold accent,
   frozen header row, zebra striping, type-aware formatting.
4. **PDF** downloads `.pdf` with gold-accented header on every page,
   footer with page numbers + UTC timestamp, auto-landscape for wide
   tables.
5. **Print** opens the browser print dialog with the table tuned for
   A4 (app chrome hidden, brand strip on top).

Run `pytest -q` -> 22 tests pass (auth + cases + workflow + court +
notifications + reports).

API endpoints visible at http://127.0.0.1:8000/docs:

- `GET /api/v1/reports` - registry
- `GET /api/v1/reports/{key}` - JSON data
- `GET /api/v1/reports/{key}.xlsx` - Excel download
- `GET /api/v1/reports/{key}.pdf` - PDF download

---

## 14. What's NOT done yet

These arrive in later phases (so do not test for them):

- Court filing, hearings, expenses (Phase 4)
- Notifications & Email Log (Phase 5)
- Excel / PDF / Print export (Phase 6)
- Scheduled email reports (Phase 7)
- Audit log (Phase 8)
- Backup & restore (Phase 9)
- Admin settings UI (Phase 10)
- Executive dashboard & charts (Phase 11)
