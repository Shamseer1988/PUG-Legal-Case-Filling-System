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

## 8. What's NOT in Phase 0 yet

These arrive in later phases (so do not test for them):

- Login / authentication (Phase 1)
- Users, roles, masters (Phase 1)
- Case entry form (Phase 2)
- Approval workflow (Phase 3)
- Reports / export / backup / email log / audit log (Phases 5–9)
- Admin settings UI (Phase 10)

Phase 0 only proves the **plumbing**: backend boots, talks to Postgres,
serves a branded frontend, and CI is wired.
