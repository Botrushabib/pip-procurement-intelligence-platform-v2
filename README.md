# pip-procurement-intelligence-platform-v2
Procurement Intelligence Platform – PIP 2.0

## Local PostgreSQL

Start the PostgreSQL container for local development:

```bash
docker compose up -d db
```

The service uses the canonical development database settings:

- Database: pip_db
- User: postgres
- Password: postgres
- Hostname: db

## Database Migrations

Apply schema migrations with Alembic before starting the backend, in any environment:

```bash
alembic upgrade head
```

## Backend — Installation and Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend (development):

```bash
uvicorn app.main:app --reload
```

Run the backend (production — see the single-worker constraint below):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the backend test suite:

```bash
pytest
```

## Production DATABASE_URL Configuration

The backend reads the `DATABASE_URL` environment variable (see
[app/core/database.py](app/core/database.py)). A local development fallback is
provided for convenience, but **production deployments must explicitly set
`DATABASE_URL`** to point at the production PostgreSQL instance, e.g.:

```
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
```

## Production Deployment Constraint — Single Worker, Single Instance

The MVP **must be run with exactly one backend worker/process and one
application instance**. The receiving import flow keeps an in-memory preview
store and uses a process-local lock to serialize commits; running multiple
workers, multiple processes, or multiple instances behind a load balancer
will break preview/commit consistency and duplicate-detection guarantees.
Do not pass `--workers` to uvicorn and do not horizontally scale this MVP.

## Frontend — Installation, Development, and Production Build

All frontend commands run from the `frontend/` directory.

Install dependencies:

```bash
npm install
```

Run the development server:

```bash
npm run dev
```

Type-check:

```bash
npm run typecheck
```

Run the frontend test suite:

```bash
npm run test
```

Build for production:

```bash
npm run build
```

The production build is emitted to `frontend/dist` and must be served from
the same origin as (or behind a reverse proxy routing `/api` to) the backend,
since the frontend calls relative `/api/...` paths.

## Receiving Excel Upload Limit

Receiving workbook uploads are limited to **25 MiB**. Uploads exceeding this
size are rejected by the backend (see
[app/api/receiving_import_api.py](app/api/receiving_import_api.py)).

## Operational Flow: Excel → Preview → Commit → Analytics

1. **Excel** — Upload a receiving workbook via the receiving import API.
2. **Preview** — The backend reads and maps the workbook, returning a preview
   with a preview token.
3. **Commit** — The confirmed preview is committed, persisting receiving
   events and lines to the database.
4. **Analytics** — Committed receiving data is immediately available through
   the receiving analytics API and surfaced in the frontend analytics
   dashboard.

## Environment Variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes, in production | PostgreSQL connection string used by the backend. Falls back to a local development default if unset. |
| `VITE_API_PROXY_TARGET` | No, development only | Overrides the Vite dev server's `/api` proxy target. Not used in production builds. |

## MVP Release Notes

This release delivers the Receiving Import + Analytics MVP:

- Excel-based receiving event import with preview and commit steps,
  including mapping, validation, and duplicate detection.
- Receiving analytics API exposing summary, history, trend, supplier
  comparison, price, supplier, and category insights.
- A frontend analytics dashboard consuming the receiving analytics API.
- PostgreSQL-backed persistence with Alembic-managed schema migrations.
- Supported as a single-worker, single-instance deployment.
