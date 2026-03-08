---
name: add-brand
description: Add a brand to the BRAND_DEPARTMENT_MAP in the scraper
user_invocable: true
---

# /add-brand — Add Brand to Department Map

Add a new brand and its department mapping to `BRAND_DEPARTMENT_MAP` in `scrape_sample_sales.py`.

## Arguments

The user should provide:
- **Brand name** (required) — e.g., "Gucci"
- **Department** (optional) — e.g., "Luxury Fashion". If not provided, infer the department from the brand.

## Steps

1. Read `scrape_sample_sales.py` and locate the `BRAND_DEPARTMENT_MAP` dictionary (around line 86)
2. Check if the brand already exists in the map (case-insensitive check against keys)
3. If it exists, inform the user and ask if they want to update the department
4. If it doesn't exist, add it in alphabetical order within the dictionary
5. Use the Edit tool to make the change
6. Confirm the addition to the user

## Valid Departments

Common departments used in the map:
- Women's Fashion, Men's Fashion, Luxury Fashion
- Contemporary Fashion, Streetwear, Activewear
- Accessories, Jewelry, Shoes, Handbags
- Home & Lifestyle, Beauty, Childrenswear
- Designer (general high-end), Outerwear
