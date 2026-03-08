---
name: scrape
description: Run the full NYC sample sales scraping pipeline
user_invocable: true
---

# /scrape — Run Full Scraping Pipeline

Run the complete sample sales scraping workflow.

## Steps

1. Run `python scrape_sample_sales.py` from the project root (`/home/user/Sample-sale/`)
2. Report the results:
   - Number of sales found from web scrapers
   - Number of sales found from social media
   - Number of verified fallback sales used
   - Total unique sales after deduplication
   - Any new accounts discovered
3. Show the generated CSV and Markdown file paths
4. If PostgreSQL is configured (`DATABASE_URL` env var), confirm data was persisted to the database

## Notes

- The scraper uses graceful degradation — if live scraping fails (e.g., network issues), it falls back to verified data
- Social media scraping requires `instaloader` and optionally `playwright`
- Output files: `nyc_sample_sales_<month>_<year>.csv` and `.md`
