---
name: db-migrate
description: Initialize or migrate the PostgreSQL database schema
user_invocable: true
---

# /db-migrate — Database Migration

Initialize or update the PostgreSQL database schema for the sample sales tracker.

## Steps

1. Check that `DATABASE_URL` environment variable is set
2. If not set, inform the user and provide the expected format:
   ```
   export DATABASE_URL="postgresql://user:password@host:5432/sample_sales"
   ```
3. Read `db_schema.sql` from the project root
4. Run `python -c` or a small script to:
   - Connect to PostgreSQL using `psycopg2` and `DATABASE_URL`
   - Execute the schema SQL (uses `IF NOT EXISTS` so it's safe to re-run)
   - Report which tables were created or already existed
5. Verify by listing tables and their row counts

## Schema Tables

- `sample_sales` — Scraped sale records with deduplication
- `discovered_accounts` — Auto-discovered social media accounts
- `scrape_runs` — Log of each scraping run with counts

## Notes

- Schema uses `IF NOT EXISTS` so migrations are idempotent
- The `dedup_key` column on `sample_sales` enforces uniqueness
- Run this before the first `/scrape` if you want PostgreSQL persistence
