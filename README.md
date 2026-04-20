# Passenger Flow Backend Server

API and demo generator for bus passenger flow accounting.

## Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2.x
- SQLite
- Pydantic 2.x
- uv
- Docker + Docker Compose

## Project Structure

```text
project/
в”њв”Ђ app/
в”‚  в”њв”Ђ main.py
в”‚  в”њв”Ђ db.py
в”‚  в”њв”Ђ models.py
в”‚  в”њв”Ђ schemas.py
в”‚  в”њв”Ђ crud.py
в”‚  в”њв”Ђ errors.py
в”‚  в”њв”Ђ routes/
в”‚  в”‚  в”њв”Ђ buses.py
в”‚  в”‚  в”њв”Ђ passengers.py
в”‚  в”‚  в””в”Ђ timeline.py
в”‚  в””в”Ђ utils/
в”‚     в””в”Ђ datetime_parser.py
в”њв”Ђ demo/
в”‚  в””в”Ђ main.py
в”њв”Ђ tests/
в”‚  в”њв”Ђ conftest.py
в”‚  в””в”Ђ test_api.py
в”њв”Ђ data/
в”‚  в””в”Ђ .gitkeep
в”њв”Ђ pyproject.toml
в”њв”Ђ uv.lock
в”њв”Ђ Dockerfile.api
в”њв”Ђ Dockerfile.demo
в”њв”Ђ docker-compose.yml
в””в”Ђ README.md
```

## Run With Docker Compose

```bash
docker compose up --build
```

If Docker Hub rate limits are hit, override base image registry:

```bash
set PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
docker compose up --build
```

API will be available at:

- `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

## Run Locally (uv)

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Demo Service ENV

- `API_DEV_MODE` (default: `false`) - if enabled (`true`, `1`, `yes`, `on`), API skips `X-AUTH` validation
- `API_AUTH_KEY` (default: `local-dev-key`) - required API key for `X-AUTH` header
- `DEMO_BUS` (default: `BUS-DEMO`)
- `DEMO_CAM_MODE` (`fixed` or `random`, default: `random`)
- `DEMO_CAM` (default: `1`) - one camera (`1`) or CSV list (`1,2,3`)
- `DEMO_INTERVAL_SECONDS` (default: `120`)
- `DEMO_BUS_CAMERA_COUNT` (default: `4`)
- `DEMO_TIMEOUT_SECONDS` (default: `10`)
- `API_URL` (default: `http://api:8000`)

## Date Format

Input date format for `/api/v1/timeline` and `/api/v1/passengers`:

- `DD.MM.YYYYTHH:MM`
- Example: `19.05.2026T19:30`

Output date format in responses:

- `YYYY-MM-DDTHH:MM:SS`
- Example: `2026-05-19T19:30:00`

## API Examples (curl)

All `/api/v1/*` requests require header: `X-AUTH: <API_AUTH_KEY>`.
If `API_DEV_MODE=true`, authorization is disabled for API routes.

Create bus:

```bash
curl -X POST http://localhost:8000/api/v1/buses \
  -H "X-AUTH: local-dev-key" \
  -F "bus=BUS-001" \
  -F "cameraCount=4"
```

Get buses:

```bash
curl -H "X-AUTH: local-dev-key" http://localhost:8000/api/v1/buses
```

Create timeline event:

```bash
curl -X POST http://localhost:8000/api/v1/timeline \
  -H "X-AUTH: local-dev-key" \
  -F "bus=BUS-001" \
  -F "cam=2" \
  -F "date=19.05.2026T19:30" \
  -F "in=4" \
  -F "out=2"
```

Get passengers timeline for period:

```bash
curl -X POST http://localhost:8000/api/v1/passengers \
  -H "X-AUTH: local-dev-key" \
  -F "bus=BUS-001" \
  -F "cam=2" \
  -F "dateFrom=19.05.2026T19:00" \
  -F "dateTo=19.05.2026T20:00"
```

Delete bus:

```bash
curl -X DELETE http://localhost:8000/api/v1/buses/BUS-001 \
  -H "X-AUTH: local-dev-key"
```

## Tests

```bash
uv sync --group dev
uv run pytest
```
