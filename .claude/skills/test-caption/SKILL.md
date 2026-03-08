---
name: test-caption
description: Test the caption parser with sample text
user_invocable: true
---

# /test-caption — Test Caption Parser

Test the social media caption parsing pipeline with sample text to verify extraction of brands, dates, locations, and notes.

## Arguments

The user should provide:
- **Caption text** (required) — the sample caption to parse

## Steps

1. Read `scrape_sample_sales.py` to understand the current parsing pipeline
2. Create a small test script that:
   - Imports `parse_social_caption` from the scraper (or recreates the parsing logic inline)
   - Runs the provided caption through: `normalize_caption()` → `resolve_relative_dates()` → `split_multi_sale_caption()` → `parse_social_caption()`
   - Prints each extracted `SampleSale` with all fields
3. Run the test script and show the results
4. Highlight any parsing issues (missing brand, wrong dates, over-matching location, etc.)

## Example Captions to Test

```
🔥 SAMPLE SALE ALERT! Rag & Bone sample sale starts March 10-14 at 260 Fifth Ave. Up to 80% off!
```

```
Upcoming sample sales this week:
1. Theory - March 10-12, 260 Sample Sale, 260 Fifth Ave
2. Vince - March 11-15, Clothingline, 261 W 36th St
```
