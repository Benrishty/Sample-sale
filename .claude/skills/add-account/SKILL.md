---
name: add-account
description: Add a social media account to the scraping config
user_invocable: true
---

# /add-account — Add Social Media Account

Add a new Instagram or Threads account to the `SOCIAL_MEDIA_ACCOUNTS` config in `scrape_sample_sales.py`.

## Arguments

The user should provide:
- **Platform** (required) — "instagram" or "threads"
- **Username** (required) — e.g., "260samplesale"

## Steps

1. Read `scrape_sample_sales.py` and locate the `SOCIAL_MEDIA_ACCOUNTS` dictionary (around line 68)
2. Check if the account already exists for the given platform
3. If it exists, inform the user
4. If it doesn't exist, add the username to the appropriate platform list
5. Use the Edit tool to make the change
6. Confirm the addition to the user

## Notes

- Accounts should be relevant to NYC sample sales
- The auto-discovery system may have already found the account — check `discovered_accounts.json` too
- Instagram accounts are scraped via Instaloader; Threads via Playwright
