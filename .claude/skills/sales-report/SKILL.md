---
name: sales-report
description: Generate a summary report from scraped sales data
user_invocable: true
---

# /sales-report — Generate Sales Report

Generate a summary report from the most recent CSV data or from PostgreSQL.

## Steps

1. Find the most recent `nyc_sample_sales_*.csv` file in the project directory
2. If PostgreSQL is configured (`DATABASE_URL`), also query the database for comparison
3. Generate a report including:
   - **Total sales count**
   - **Sales by department** (count per department)
   - **Sales by source** (web vs social vs verified)
   - **Currently active sales** (where today falls between start and end dates)
   - **Upcoming sales** (start date in the future)
   - **Ended sales** (end date in the past)
   - **Top locations** (most common sale venues)
   - **Brands with multiple sales**
4. Format the report as a clean Markdown table and present to the user

## Notes

- Use Python's `csv` module to parse the CSV
- Date comparisons should use today's date
- If no CSV exists, suggest running `/scrape` first
