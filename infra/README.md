# Infra (Optional / Future)

Local dev does **not** use Docker — see the root README for direct setup.

The files in this folder are kept ready for future cloud deploy:

- `docker-compose.yml` — full stack (Postgres, Redis, backend, frontend, nginx)
- `backend.Dockerfile` — backend image
- `frontend.Dockerfile` — frontend image
- `nginx.conf` — reverse proxy template
- `systemd/` — systemd unit templates (added in Phase 12)

## Try the stack with Docker (optional)

```bash
cd infra
docker compose up --build
```

- Backend: http://127.0.0.1:8000
- Frontend: http://127.0.0.1:3000
