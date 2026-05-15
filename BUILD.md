# Docker Build

Last verified: 2026-05-15

## Commands

Build both Docker images:

```bash
docker compose build
```

Start the stack:

```bash
docker compose up -d
```

Rebuild only the frontend after frontend config changes:

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

Check running services:

```bash
docker compose ps
```

## Verified Services

- Backend image: `repo-explorer-backend`
- Frontend image: `repo-explorer-frontend`
- Backend URL: `http://localhost:8000`
- Frontend URL: `http://localhost:3000`

Final Docker status:

```text
repo-explorer-backend-1   Up (healthy)   0.0.0.0:8000->8000/tcp
repo-explorer-frontend-1  Up (healthy)   0.0.0.0:3000->80/tcp
```

## Verified Endpoints

Backend health:

```bash
curl http://localhost:8000/api/llm/status
```

Graph node details:

```bash
curl -X POST http://localhost:8000/api/graph/node-details \
  -H "Content-Type: application/json" \
  -d '{"structure":{"files":[{"path":"src/auth/login.py","name":"login.py","definitions":{"classes":["Authenticator"],"functions":["verify_token"],"variables":["MAX_RETRIES"]},"imports":["src/utils/security.py"]}]},"node_id":"src/auth/login.py"}'
```

Expected graph node details response includes:

```json
{
  "id": "src/auth/login.py",
  "path": "src/auth/login.py",
  "label": "login.py",
  "name": "login.py",
  "group": "src",
  "definitions": {
    "classes": ["Authenticator"],
    "functions": ["verify_token"],
    "variables": ["MAX_RETRIES"]
  },
  "imports": ["src/utils/security.py"]
}
```

Frontend health:

```bash
curl http://localhost:3000/health
```

## Notes

- The Docker frontend now defaults to `http://localhost:8000` for the backend URL.
- In this local environment, `127.0.0.1:8000` returned a stale/non-Docker backend response during verification, while `localhost:8000` correctly reached the Docker backend.
- The production backend image does not install `pytest`; run Python tests locally or add a dedicated test image/stage if containerized tests are required.
- Vite emits a non-blocking warning about a JavaScript chunk larger than 500 kB.
