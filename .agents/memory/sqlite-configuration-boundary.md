---
name: SQLite configuration boundary
description: Database URL handling for the SQLite MVP in an environment that may expose a platform PostgreSQL URL.
---

The incident commander database uses an app-specific `INCIDENT_DATABASE_URL` variable. This keeps the SQLite MVP isolated from a platform-provided `DATABASE_URL` that may point to PostgreSQL without a configured driver or service.

**Why:** Database initialization initially attempted to import the PostgreSQL driver because the environment already exposed `DATABASE_URL` with a PostgreSQL scheme, which conflicted with the requested SQLite MVP.

**How to apply:** Use `INCIDENT_DATABASE_URL` for this application. When PostgreSQL is intentionally introduced later, add its driver and explicitly configure this variable rather than reusing an unrelated platform value.