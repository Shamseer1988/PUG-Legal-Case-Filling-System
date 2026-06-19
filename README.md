# PUG Legal Case Control System

Centralized legal case management for Paris United Group Holding's multi-branch
operations — case intake, multi-stage approvals, court filing, hearings,
expenses, reporting and full audit.

> See the full plan: [`docs/phase-plan.html`](docs/phase-plan.html)

---

## Repository Layout

```
PUG-Legal-Case-Filling-System/
├── backend/        FastAPI + SQLAlchemy + Alembic + Celery
├── frontend/       Next.js 14 + TypeScript + Tailwind + shadcn/ui
├── infra/          Optional Docker / docker-compose (future cloud deploy)
├── scripts/        Local dev setup helpers
├── storage/        Local file storage (uploads, attachments) [gitignored]
├── backups/        Local DB / attachment backups [gitignored]
├── docs/           Plans, runbooks, API docs
└── assets/         Branding, sample form, SOP
```

## Architecture (Phase 0)

- **Local dev = direct** (PugFin-style). No Docker required to run the app.
- **Postgres 16** and **Redis 7** installed locally as system services.
- **File storage = local filesystem** at `./storage/`. S3 will be added later as
  an optional integration under Admin → System Settings.
- **Docker / docker-compose files are checked in** but kept for *future* cloud
  deploys — they are not part of the local dev flow.
- **systemd units + nginx** will land in Phase 12 (deployment).

## Quick Start (Local Dev)

### Prerequisites

- Python 3.12
- Node.js 20 LTS + pnpm (or npm)
- PostgreSQL 16 running locally
- Redis 7 running locally

### One-time setup

```bash
./scripts/setup.sh
```

This will:
- Create a Python venv in `backend/.venv/`
- Install backend dependencies
- Install frontend dependencies
- Copy `.env.example` to `.env` in both apps
- Create the `storage/` and `backups/` folders
- Run Alembic migrations against your local Postgres

### Run the backend

```bash
./scripts/dev-backend.sh
# → http://127.0.0.1:8000/health
# → http://127.0.0.1:8000/docs   (OpenAPI)
```

### Run the frontend

```bash
./scripts/dev-frontend.sh
# → http://127.0.0.1:3000
```

### Seed default admin + sample masters

```bash
./scripts/seed.sh        # Linux / macOS
.\scripts\seed.ps1       # Windows PowerShell
```

Default login: **admin@pug.local** / **Admin@123**

## Tech Stack

| Layer       | Tech                                                            |
|-------------|-----------------------------------------------------------------|
| Backend     | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2        |
| Jobs        | Celery + Redis, APScheduler                                     |
| Frontend    | Next.js 14, React 18, TypeScript, Tailwind, shadcn/ui           |
| Database    | PostgreSQL 16                                                   |
| Cache/Queue | Redis 7                                                         |
| Storage     | Local filesystem (S3-compatible optional later)                 |
| Docs        | WeasyPrint, OpenPyXL, Jinja2                                    |
| Auth        | JWT + Argon2 + optional TOTP 2FA                                |

## Development Phases

Phases are sized to fit within a single Claude Code 5-hour token window.
See [`docs/phase-plan.html`](docs/phase-plan.html) for the full roadmap.

| Phase | Focus                                  | Status      |
|------:|----------------------------------------|-------------|
| 0     | Foundation & Scaffolding               | ✅ Done     |
| 1     | Auth, RBAC, Masters                    | ✅ Done     |
| 2     | Legal Case Entry Form                  | ✅ Done     |
| 3     | Approval Workflow Engine               | ✅ Done     |
| 4     | Court Filing, Hearings, Expenses       | ✅ Done     |
| 5     | Notifications & Email Log              | ✅ Done     |
| 6     | Reports + Excel/PDF/Print Export       | Pending     |
| 7     | Scheduled Reporting via Email          | Pending     |
| 8     | Audit Log (Tamper-Evident)             | Pending     |
| 9     | Backup & Restore (PugFin parity)       | Pending     |
| 10    | System Settings & Admin Console        | Pending     |
| 11    | Executive Dashboard & Charts           | Pending     |
| 12    | Hardening, Tests, Deploy               | Pending     |

## License

Proprietary — Paris United Group Holding.
