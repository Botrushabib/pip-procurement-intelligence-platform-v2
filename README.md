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
