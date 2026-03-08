---
name: db-query
description: Run ad-hoc queries against the PostgreSQL database
user_invocable: true
---

# /db-query — Query the Database

Run ad-hoc read-only queries against the PostgreSQL sample sales database.

## Arguments

The user should provide:
- **Query description** (required) — what they want to look up, in natural language

## Steps

1. Check that `DATABASE_URL` environment variable is set
2. Translate the user's natural language request into a SQL query
3. Run the query using `psycopg2` with a read-only transaction
4. Format and display the results as a Markdown table
5. Include the SQL query used for transparency

## Example Queries

- "Show all active sales" → `SELECT * FROM sample_sales WHERE start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE`
- "Which brands have had the most sales?" → `SELECT brand, COUNT(*) FROM sample_sales GROUP BY brand ORDER BY count DESC LIMIT 10`
- "Show recent scrape runs" → `SELECT * FROM scrape_runs ORDER BY run_at DESC LIMIT 5`
- "New accounts discovered this week" → `SELECT * FROM discovered_accounts WHERE discovered_date >= CURRENT_DATE - INTERVAL '7 days'`

## Safety

- Always use read-only queries (SELECT only)
- Never run DELETE, DROP, UPDATE, or INSERT via this skill
- Use parameterized queries if user input is included in WHERE clauses
- Set `statement_timeout` to prevent long-running queries
