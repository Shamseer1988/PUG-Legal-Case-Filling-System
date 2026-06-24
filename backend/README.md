# Backend — PUG Legal Case Control System

FastAPI service for the Legal Case Control System.

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,reports]"

cp .env.example .env
# edit .env with your local Postgres / Redis details

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:
- http://127.0.0.1:8000/
- http://127.0.0.1:8000/docs (OpenAPI)
- http://127.0.0.1:8000/api/v1/health

## Tests / Lint

```bash
pytest
ruff check .
ruff format .
```

## Migrations

```bash
alembic revision --autogenerate -m "your change"
alembic upgrade head
alembic downgrade -1
```
