---
name: discover
description: Run the account discovery system only
user_invocable: true
---

# /discover — Run Account Discovery

Run only the social media account discovery system without the full scraping pipeline.

## Steps

1. Read `scrape_sample_sales.py` to understand the discovery system
2. Create and run a script that:
   - Imports and calls `run_account_discovery()` from the scraper
   - Loads existing `discovered_accounts.json` if present
   - Runs mention mining and hashtag exploration
   - Reports newly discovered accounts with relevance scores
3. Show results:
   - Number of new accounts found
   - Account names, platforms, and relevance scores
   - Which accounts passed the relevance threshold (≥0.3)
4. If PostgreSQL is configured, persist discovered accounts to the `discovered_accounts` table

## Notes

- Discovery uses @mention mining from existing account posts and hashtag exploration
- Relevance scoring (0.0–1.0) filters out unrelated accounts
- Accounts with score ≥ 0.3 are considered relevant
- Network restrictions may limit live discovery; this is expected behavior
