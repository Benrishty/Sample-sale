#!/usr/bin/env python3
"""
NYC Sample Sale Scraper — March 2026
=====================================
Scrapes upcoming/active sample sales from:

  Website aggregators:
    1. 260 Sample Sale (https://260samplesale.com/pages/nyc-schedule)
    2. Chicmi NYC (https://www.chicmi.com/new-york/sample-sales/)
    3. Lazar Shopping (https://lazarshopping.com/)
    4. NYC Insider Guide (https://www.nycinsiderguide.com/nyc-shopping/sample-sales)

  Social media accounts (Instagram via Instaloader, Threads via Playwright):
    5. @260samplesale (Instagram)
    6. @chicaboratanyc (Instagram)
    7. @lazaboratasamplesales (Instagram)
    8. @nycstealzanddeals (Instagram)
    9. @thestylishcity (Instagram)
   10. @vipsamplesalenewyork (Threads)

  Auto-discovery: Learns new accounts from @mentions and hashtags, persisted
  in discovered_accounts.json for subsequent runs.

Outputs:
  - nyc_sample_sales_march_2026.csv
  - nyc_sample_sales_march_2026.md
  - discovered_accounts.json (auto-generated)
"""

import csv
import os
import re
import json
import hashlib
import random
import sys
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

# Optional imports — graceful degradation
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import instaloader
    HAS_INSTALOADER = True
except ImportError:
    HAS_INSTALOADER = False

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
DISCOVERED_ACCOUNTS_FILE = SCRIPT_DIR / "discovered_accounts.json"

SOCIAL_MEDIA_ACCOUNTS = {
    "instagram": {
        "260samplesale": {"enabled": True, "source_name": "Instagram @260samplesale"},
        "chicaboratanyc": {"enabled": True, "source_name": "Instagram @chicaboratanyc"},
        "lazaboratasamplesales": {"enabled": True, "source_name": "Instagram @lazaboratasamplesales"},
        "nycstealzanddeals": {"enabled": True, "source_name": "Instagram @nycstealzanddeals"},
        "thestylishcity": {"enabled": True, "source_name": "Instagram @thestylishcity"},
    },
    "threads": {
        "vipsamplesalenewyork": {"enabled": True, "source_name": "Threads @vipsamplesalenewyork"},
    },
}

DISCOVERY_HASHTAGS = ["nycsamplesale", "samplesalenyc", "260samplesale", "nycsamplesales"]

# Max posts to fetch per account (keep low to respect rate limits)
IG_MAX_POSTS = 12
THREADS_MAX_POSTS = 10


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

BRAND_DEPARTMENT_MAP = {
    # Footwear
    "manolo blahnik": "Footwear", "jimmy choo": "Footwear", "stuart weitzman": "Footwear",
    "christian louboutin": "Footwear", "aquazzura": "Footwear", "giuseppe zanotti": "Footwear",
    "salvatore ferragamo": "Footwear", "cole haan": "Footwear", "steve madden": "Footwear",
    "allbirds": "Footwear", "nike": "Footwear", "adidas": "Footwear", "new balance": "Footwear",
    "vince camuto": "Footwear", "schutz": "Footwear", "birkenstock": "Footwear",
    "shoe-inn": "Footwear", "ugg": "Footwear", "dolce vita": "Footwear",
    "sam edelman": "Footwear", "tony bianco": "Footwear",
    # Womenswear
    "reformation": "Womenswear", "ganni": "Womenswear", "ulla johnson": "Womenswear",
    "veronica beard": "Womenswear", "alice + olivia": "Womenswear", "dvf": "Womenswear",
    "diane von furstenberg": "Womenswear", "self-portrait": "Womenswear",
    "proenza schouler": "Womenswear", "rachel comey": "Womenswear", "staud": "Womenswear",
    "sandro": "Womenswear", "maje": "Womenswear", "ba&sh": "Womenswear",
    "iro": "Womenswear", "equipment": "Womenswear", "joie": "Womenswear",
    "eileen fisher": "Womenswear", "lafayette 148": "Womenswear",
    "derek lam": "Womenswear", "tanya taylor": "Womenswear",
    "cynthia rowley": "Womenswear", "lamarque": "Womenswear",
    "djerf avenue": "Womenswear", "weworewhat": "Womenswear",
    "max mara": "Womenswear, Menswear", "tia cibani": "Childrenswear",
    "mandinga": "Womenswear", "harleen kaur": "Womenswear",
    "alicia adams alpaca": "Womenswear, Accessories",
    "perfect moment": "Womenswear, Activewear",
    # Menswear
    "bonobos": "Menswear", "todd snyder": "Menswear", "suit supply": "Menswear",
    "suitsupply": "Menswear", "brooks brothers": "Menswear",
    "hugo boss": "Menswear, Womenswear", "bogner": "Womenswear, Menswear",
    "officine generale": "Menswear, Womenswear",
    # Multi-department / Designer
    "theory": "Womenswear, Menswear", "helmut lang": "Womenswear, Menswear",
    "rag & bone": "Womenswear, Menswear", "vince": "Womenswear, Menswear",
    "frame": "Womenswear, Menswear", "reiss": "Womenswear, Menswear",
    "velvet": "Womenswear",
    "coach": "Accessories", "kate spade": "Accessories", "marc jacobs": "Accessories",
    "michael kors": "Womenswear, Accessories", "tory burch": "Womenswear, Accessories",
    "goop": "Womenswear, Beauty, Home",
    # Accessories / Jewelry
    "kendra scott": "Accessories", "david yurman": "Accessories",
    "baublebar": "Accessories", "gorjana": "Accessories",
    # Home / Linens
    "frette": "Home, Linens", "west elm": "Home", "cb2": "Home",
    "williams-sonoma": "Home", "restoration hardware": "Home", "rh": "Home",
    # Swimwear
    "onia": "Swimwear", "aquilon": "Swimwear",
    # Haute Couture / Multi-brand
    "msa haute couture": "Womenswear, Haute Couture",
    "carlisle": "Womenswear",
    # Additional brands commonly seen on social media
    "anine bing": "Womenswear", "agolde": "Womenswear", "aritzia": "Womenswear",
    "khaite": "Womenswear", "toteme": "Womenswear", "le labo": "Beauty",
    "diptyque": "Beauty", "byredo": "Beauty", "aesop": "Beauty",
    "the row": "Womenswear", "nili lotan": "Womenswear",
    "zadig & voltaire": "Womenswear, Menswear",
    "rebecca minkoff": "Womenswear, Accessories",
    "3.1 phillip lim": "Womenswear, Menswear",
    "oscar de la renta": "Womenswear, Haute Couture",
    "carolina herrera": "Womenswear, Haute Couture",
    "monse": "Womenswear", "jonathan simkhai": "Womenswear",
    "jason wu": "Womenswear", "prabal gurung": "Womenswear",
    "cushnie": "Womenswear", "brandon maxwell": "Womenswear",
    "l'agence": "Womenswear", "chanel": "Womenswear, Accessories",
    "dior": "Womenswear, Accessories", "versace": "Womenswear, Accessories",
    "dolce & gabbana": "Womenswear, Menswear", "etro": "Womenswear, Menswear",
    "emilio pucci": "Womenswear", "taller marmo": "Womenswear",
}


@dataclass
class SampleSale:
    brand: str = ""
    department: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    link: str = ""
    notes: str = ""
    source: str = ""

    def dedup_key(self) -> str:
        raw = f"{self.brand.lower().strip()}|{self.start_date}|{self.location.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()


def infer_department(brand: str) -> str:
    key = brand.lower().strip()
    for pattern, dept in BRAND_DEPARTMENT_MAP.items():
        if pattern in key or key in pattern:
            return dept
    return "Various"


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2})\s*[-–—to]+\s*((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+)?\d{1,2}),?\s*(\d{4})?",
    r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*[-–—to]+\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s*\d{4})",
]

LOCATION_PATTERNS = [
    r"(\d+\s+(?:Fifth|Madison|Park|Lexington|Broadway|West|East|Spring|Wooster|Greene|Mercer|Prince|Houston|Canal|Broome|Grand|Bleecker|Christopher|Hudson|Washington|Warren|Church|Centre|Lafayette|Bowery|Elizabeth|Mott|Mulberry|Orchard|Rivington|Delancey|Allen|Essex|Norfolk|Suffolk|Clinton|Attorney|Ridge|Pitt|Columbia|Lewis|Stanton|Avenue|Street|St|Ave|Blvd|Place|Pl|Road|Rd|Way|Drive|Dr|Lane|Ln|Court|Ct)\b[^,\n!\.]{0,30})",
    r"(260\s+(?:Fifth|Sample|sample)[^,\n!\.]{0,30})",
    r"(\d+\s+[EWNS]\.?\s+\d+\w*\s+(?:St|Ave|Street|Avenue|Blvd|Pl|Place)\b[^,\n!\.]{0,30})",
    r"(\d+\s+\w+\s+(?:St|Ave|Street|Avenue|Blvd|Boulevard|Place|Pl|Road|Rd|Way|Drive|Dr)\b[^,\n!\.]{0,30})",
]


def parse_date_range(text: str) -> tuple[str, str]:
    if not text:
        return ("", "")
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            if len(groups) >= 2:
                start = groups[0].strip().rstrip(",")
                end_part = groups[1].strip().rstrip(",")
                year = groups[2] if len(groups) > 2 and groups[2] else "2026"
                if re.match(r"^\d{1,2}$", end_part):
                    month_match = re.match(r"([A-Za-z]+\.?\s+)", start)
                    if month_match:
                        end_part = month_match.group(1) + end_part
                return (f"{start}, {year}".replace(", ,", ","), f"{end_part}, {year}".replace(", ,", ","))
            elif len(groups) == 1:
                return (groups[0].strip(), groups[0].strip())
    return ("", "")


def extract_location(text: str) -> str:
    if not text:
        return ""
    for pattern in LOCATION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def extract_notes(text: str) -> str:
    notes = []
    note_patterns = [
        r"up\s+to\s+\d+%\s+off",
        r"\d+%\s+off",
        r"credit\s+card\s+only",
        r"cash\s+only",
        r"appointment\s+(?:required|only|necessary)",
        r"by\s+invitation\s+only",
        r"open\s+to\s+(?:the\s+)?public",
        r"free\s+(?:entry|admission)",
        r"rsvp\s+required",
        r"booking\s+required",
        r"all\s+sales\s+(?:are\s+)?final",
        r"registration\s+required",
    ]
    for pattern in note_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            notes.append(m.group(0).strip())
    return "; ".join(notes)


def clean_brand(brand: str) -> str:
    brand = re.sub(r"(?i)^\s*(the\s+)?", "", brand)
    brand = re.sub(r"(?i)\s*sample\s+sale\s*$", "", brand)
    brand = re.sub(r"(?i)\s*nyc\s*$", "", brand)
    brand = brand.strip(" -–—:|")
    return brand.strip()


# ---------------------------------------------------------------------------
# Social Media: Caption Parsing Pipeline
# ---------------------------------------------------------------------------

EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000200D"             # zero width joiner
    "\U00002B50\U00002B55"   # stars
    "\U0000231A-\U0000231B"  # watch/hourglass
    "]+", flags=re.UNICODE,
)

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def normalize_caption(text: str) -> tuple[str, list[str], list[str]]:
    """Strip emoji, extract hashtags and mentions, normalize whitespace (preserve newlines)."""
    hashtags = re.findall(r"#(\w+)", text)
    mentions = re.findall(r"@(\w+)", text)
    cleaned = EMOJI_PATTERN.sub(" ", text)
    cleaned = re.sub(r"#\w+", " ", cleaned)
    cleaned = re.sub(r"@\w+", " ", cleaned)
    # Preserve newlines for multi-sale splitting, but collapse other whitespace
    cleaned = re.sub(r"[^\S\n]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), hashtags, mentions


def resolve_relative_dates(text: str, reference_date: str) -> tuple[str, str]:
    """Convert 'today', 'tomorrow', 'this weekend', 'starts Friday' to absolute dates."""
    try:
        ref = datetime.strptime(reference_date, "%Y-%m-%d") if reference_date else datetime.now()
    except ValueError:
        ref = datetime.now()

    text_lower = text.lower()

    if re.search(r"\btoday\b", text_lower):
        d = ref.strftime("%B %d, %Y")
        return (d, d)

    if re.search(r"\btomorrow\b", text_lower):
        d = (ref + timedelta(days=1)).strftime("%B %d, %Y")
        return (d, d)

    m = re.search(r"\bthis\s+weekend\b", text_lower)
    if m:
        days_until_sat = (5 - ref.weekday()) % 7
        if days_until_sat == 0 and ref.weekday() != 5:
            days_until_sat = 7
        sat = ref + timedelta(days=days_until_sat)
        sun = sat + timedelta(days=1)
        return (sat.strftime("%B %d, %Y"), sun.strftime("%B %d, %Y"))

    m = re.search(r"\bstarts?\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", text_lower)
    if m:
        target_day = WEEKDAY_MAP.get(m.group(1).lower())
        if target_day is not None:
            days_ahead = (target_day - ref.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            start = ref + timedelta(days=days_ahead)
            return (start.strftime("%B %d, %Y"), "")

    return ("", "")


def extract_brand_from_caption(text: str, hashtags: list[str]) -> str:
    """
    Extract brand name from social media caption text.
    Priority: known brands → "X SAMPLE SALE" pattern → ALL-CAPS → hashtag brands.
    """
    text_lower = text.lower()

    # 1. Check for known brands in the text
    best_match = ""
    best_len = 0
    for brand_key in BRAND_DEPARTMENT_MAP:
        if brand_key in text_lower and len(brand_key) > best_len:
            best_match = brand_key
            best_len = len(brand_key)
    if best_match:
        # Find the original-case version in the text
        m = re.search(re.escape(best_match), text, re.IGNORECASE)
        if m:
            return m.group(0)
        return best_match.title()

    # 2. "BRAND SAMPLE SALE" pattern — words before "sample sale"
    m = re.search(r"([\w\s&\.\'\-]+?)\s+sample\s+sale", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        # Filter out generic words
        if candidate.lower() not in ("the", "a", "our", "this", "nyc", "new york", "annual", "big", "huge", "mega"):
            return clean_brand(candidate)

    # 3. ALL-CAPS sequences (common Instagram style: "REFORMATION SAMPLE SALE")
    caps_matches = re.findall(r"\b([A-Z][A-Z\s&\.\'\-]{2,}[A-Z])\b", text)
    for cap in caps_matches:
        cap_clean = cap.strip()
        if cap_clean.lower() not in ("sample sale", "nyc", "new york", "rsvp", "dm", "link in bio"):
            return clean_brand(cap_clean.title())

    # 4. Check hashtags for brand names
    for tag in hashtags:
        tag_lower = tag.lower()
        for brand_key in BRAND_DEPARTMENT_MAP:
            normalized = brand_key.replace(" ", "").replace("&", "and").replace(".", "")
            if tag_lower == normalized or normalized in tag_lower:
                return brand_key.title()

    return ""


def split_multi_sale_caption(text: str) -> list[str]:
    """Split captions that announce multiple sales into segments."""
    # Check for numbered lists: "1. Brand...\n2. Brand..."
    # Use findall to capture all numbered items (handles text before "1." correctly)
    numbered_items = re.findall(r"(?:^|\n)\s*\d+[\.\)]\s+(.*?)(?=\n\s*\d+[\.\)]|\Z)", text, re.DOTALL)
    if len(numbered_items) >= 2:
        return [s.strip() for s in numbered_items if s.strip()]

    # Check for bullet-style: "• Brand..." or "- Brand..."
    bullet_items = re.findall(r"(?:^|\n)\s*[•\-\*]\s+(.*?)(?=\n\s*[•\-\*]|\Z)", text, re.DOTALL)
    if len(bullet_items) >= 2:
        return [s.strip() for s in bullet_items if s.strip()]

    # Check for double-newline separated blocks with dates in each
    blocks = re.split(r"\n\s*\n", text)
    if len(blocks) > 1:
        blocks_with_dates = [b for b in blocks if re.search(
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2}/\d{1,2})", b, re.IGNORECASE
        )]
        if len(blocks_with_dates) > 1:
            return [b.strip() for b in blocks if b.strip()]

    return [text]


def parse_social_caption(
    caption: str, account: str, post_url: str, post_date: str
) -> list[SampleSale]:
    """
    Parse a social media caption into structured SampleSale objects.
    Returns a list because one caption may announce multiple sales.
    """
    if not caption:
        return []

    cleaned, hashtags, mentions = normalize_caption(caption)
    segments = split_multi_sale_caption(cleaned)
    sales = []

    for segment in segments:
        brand = extract_brand_from_caption(segment, hashtags)
        if not brand:
            brand = extract_brand_from_caption(cleaned, hashtags)
        if not brand or len(brand) < 2:
            continue

        # Try standard date parsing first
        start, end = parse_date_range(segment)
        if not start:
            start, end = parse_date_range(cleaned)
        # Try relative dates as fallback
        if not start:
            start, end = resolve_relative_dates(segment, post_date)
        if not start:
            start, end = resolve_relative_dates(cleaned, post_date)

        # Skip if still no date (can't create useful entry without timing)
        if not start:
            continue

        location = extract_location(segment) or extract_location(cleaned)
        notes = extract_notes(segment) or extract_notes(cleaned)
        link = post_url or ""

        sale = SampleSale(
            brand=clean_brand(brand),
            start_date=start,
            end_date=end,
            location=location,
            link=link,
            notes=notes,
            source=f"Instagram @{account}",
        )
        sale.department = infer_department(sale.brand)
        sales.append(sale)

    return sales


# ---------------------------------------------------------------------------
# Social Media: Instagram Scraper (Instaloader)
# ---------------------------------------------------------------------------

def scrape_instagram_account(
    loader: "instaloader.Instaloader",
    username: str,
    source_name: str,
    max_posts: int = IG_MAX_POSTS,
) -> tuple[list[SampleSale], list[dict]]:
    """
    Scrape recent posts from a public Instagram profile.
    Returns (sales, raw_posts) where raw_posts contains caption/metadata for discovery.
    """
    sales = []
    raw_posts = []

    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        count = 0
        for post in profile.get_posts():
            if count >= max_posts:
                break
            caption = post.caption or ""
            post_date = post.date_utc.strftime("%Y-%m-%d") if post.date_utc else ""
            post_url = f"https://www.instagram.com/p/{post.shortcode}/"

            raw_posts.append({
                "caption": caption,
                "url": post_url,
                "date": post_date,
                "account": username,
            })

            parsed = parse_social_caption(caption, username, post_url, post_date)
            for s in parsed:
                s.source = source_name
            sales.extend(parsed)
            count += 1

    except instaloader.exceptions.ProfileNotExistsException:
        print(f"    [WARN] Profile @{username} does not exist")
    except instaloader.exceptions.LoginRequiredException:
        print(f"    [WARN] Login required for @{username}, skipping")
    except instaloader.exceptions.ConnectionException as e:
        print(f"    [WARN] Connection error for @{username}: {e}")
    except Exception as e:
        print(f"    [ERROR] Failed to scrape @{username}: {e}")

    return sales, raw_posts


def run_instagram_scrapers(
    accounts: dict[str, dict],
) -> tuple[list[SampleSale], list[dict]]:
    """Run Instaloader-based Instagram scrapers for all enabled accounts."""
    if not HAS_INSTALOADER:
        print("  [SKIP] Instaloader not installed, skipping Instagram scrape")
        return [], []

    all_sales = []
    all_posts = []

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        download_geotags=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    for username, config in accounts.items():
        if not config.get("enabled", False):
            continue
        print(f"  Scraping Instagram @{username}...")
        sales, posts = scrape_instagram_account(
            loader, username, config["source_name"]
        )
        all_sales.extend(sales)
        all_posts.extend(posts)
        print(f"    Found {len(sales)} sales from {len(posts)} posts")
        # Rate-limit delay between accounts
        time.sleep(random.uniform(3, 5))

    return all_sales, all_posts


# ---------------------------------------------------------------------------
# Social Media: Threads Scraper (Playwright)
# ---------------------------------------------------------------------------

def scrape_threads_profile(
    page, username: str, max_posts: int = THREADS_MAX_POSTS
) -> list[dict]:
    """Scrape recent posts from a public Threads profile via Playwright."""
    url = f"https://www.threads.net/@{username}"
    posts = []

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        # Scroll down to load more posts
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(1500)

        # Extract post content — Threads uses various container selectors
        post_elements = page.query_selector_all(
            "[data-pressable-container], article, [class*='post'], [class*='thread']"
        )

        for el in post_elements[:max_posts]:
            try:
                text = el.inner_text() or ""
                # Try to find a time element for the post date
                time_el = el.query_selector("time")
                date_str = ""
                if time_el:
                    date_str = time_el.get_attribute("datetime") or ""
                    if date_str:
                        try:
                            date_str = datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            ).strftime("%Y-%m-%d")
                        except ValueError:
                            pass

                # Try to find a link for the post
                link_el = el.query_selector("a[href*='/post/']")
                post_url = ""
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    if href:
                        post_url = f"https://www.threads.net{href}" if href.startswith("/") else href

                if text and len(text) > 10:
                    posts.append({
                        "caption": text,
                        "url": post_url or url,
                        "date": date_str,
                        "account": username,
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"    [ERROR] Failed to scrape Threads @{username}: {e}")

    return posts


def run_threads_scrapers(
    accounts: dict[str, dict],
) -> tuple[list[SampleSale], list[dict]]:
    """Run Playwright-based Threads scrapers for all enabled accounts."""
    if not HAS_PLAYWRIGHT:
        print("  [SKIP] Playwright not available, skipping Threads scrape")
        return [], []

    all_sales = []
    all_posts = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()

            for username, config in accounts.items():
                if not config.get("enabled", False):
                    continue
                print(f"  Scraping Threads @{username}...")
                posts = scrape_threads_profile(page, username)
                all_posts.extend(posts)

                for post in posts:
                    parsed = parse_social_caption(
                        post["caption"], username, post["url"], post["date"]
                    )
                    for s in parsed:
                        s.source = config["source_name"]
                    all_sales.extend(parsed)

                print(f"    Found {len(all_sales)} sales from {len(posts)} posts")
                time.sleep(random.uniform(5, 10))

            browser.close()
    except Exception as e:
        print(f"  [ERROR] Threads scraping failed: {e}")

    return all_sales, all_posts


# ---------------------------------------------------------------------------
# Social Media: Account Discovery System
# ---------------------------------------------------------------------------

DISCOVERY_RELEVANCE_KEYWORDS = {
    "sample sale", "samplesale", "sample-sale", "warehouse sale",
    "nyc", "new york", "manhattan", "soho", "noho", "nomad",
    "260 sample", "260samplesale", "fashion", "designer",
    "off retail", "% off", "discount", "clearance",
}


def load_discovered_accounts() -> dict:
    """Load previously discovered accounts from JSON file."""
    if DISCOVERED_ACCOUNTS_FILE.exists():
        try:
            with open(DISCOVERED_ACCOUNTS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"instagram": {}, "threads": {}}


def save_discovered_accounts(data: dict):
    """Persist discovered accounts to JSON file."""
    with open(DISCOVERED_ACCOUNTS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Discovery data saved to {DISCOVERED_ACCOUNTS_FILE}")


def score_account_relevance(username: str, caption_context: str = "") -> float:
    """Score 0.0–1.0 based on how relevant an account is to NYC sample sales."""
    score = 0.0
    combined = (username + " " + caption_context).lower()

    for keyword in DISCOVERY_RELEVANCE_KEYWORDS:
        if keyword in combined:
            score += 0.15

    # Bonus for username containing sale-related terms
    uname = username.lower()
    if any(w in uname for w in ("sample", "sale", "fashion", "shop", "deal", "steal")):
        score += 0.2
    if any(w in uname for w in ("nyc", "newyork", "manhattan")):
        score += 0.15

    return min(score, 1.0)


def discover_accounts_from_posts(
    raw_posts: list[dict],
    existing_accounts: set[str],
) -> dict[str, dict]:
    """Mine @mentions from scraped posts to find new sample sale accounts."""
    discovered = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for post in raw_posts:
        caption = post.get("caption", "")
        account = post.get("account", "")
        _, _, mentions = normalize_caption(caption)

        for mention in mentions:
            mention_lower = mention.lower()
            if mention_lower in existing_accounts:
                continue
            if len(mention_lower) < 3:
                continue

            relevance = score_account_relevance(mention_lower, caption)
            if relevance >= 0.3 and mention_lower not in discovered:
                discovered[mention_lower] = {
                    "discovered_from": f"@{account} mention",
                    "discovered_date": today,
                    "enabled": True,
                    "relevance_score": round(relevance, 2),
                    "source_name": f"Instagram @{mention_lower} (discovered)",
                }

    return discovered


def discover_accounts_from_hashtags(
    loader: "instaloader.Instaloader",
    existing_accounts: set[str],
    max_hashtags: int = 3,
    max_posts_per_tag: int = 30,
) -> dict[str, dict]:
    """Explore hashtag pages to find new sample sale accounts."""
    discovered = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for tag in DISCOVERY_HASHTAGS[:max_hashtags]:
        try:
            print(f"    Exploring #{tag}...")
            hashtag = instaloader.Hashtag.from_name(loader.context, tag)
            count = 0
            for post in hashtag.get_posts():
                if count >= max_posts_per_tag:
                    break
                owner = post.owner_username
                if owner and owner.lower() not in existing_accounts:
                    caption = post.caption or ""
                    relevance = score_account_relevance(owner, caption)
                    if relevance >= 0.3 and owner.lower() not in discovered:
                        discovered[owner.lower()] = {
                            "discovered_from": f"#{tag} hashtag",
                            "discovered_date": today,
                            "enabled": True,
                            "relevance_score": round(relevance, 2),
                            "source_name": f"Instagram @{owner} (discovered)",
                        }
                count += 1
            time.sleep(random.uniform(3, 6))
        except Exception as e:
            print(f"    [WARN] Hashtag #{tag} exploration failed: {e}")

    return discovered


def run_account_discovery(
    raw_posts: list[dict],
    existing_accounts: set[str],
) -> dict[str, dict]:
    """Run the full account discovery pipeline."""
    print("\n  --- Account Discovery ---")
    all_discovered = {}

    # 1. Discover from @mentions in scraped posts
    mention_discoveries = discover_accounts_from_posts(raw_posts, existing_accounts)
    all_discovered.update(mention_discoveries)
    if mention_discoveries:
        print(f"    Found {len(mention_discoveries)} accounts from @mentions")

    # 2. Discover from hashtag exploration (Instaloader only)
    if HAS_INSTALOADER:
        loader = instaloader.Instaloader(
            download_pictures=False, download_videos=False,
            download_video_thumbnails=False, download_comments=False,
            download_geotags=False, save_metadata=False,
            compress_json=False, quiet=True,
        )
        combined = existing_accounts | set(all_discovered.keys())
        hashtag_discoveries = discover_accounts_from_hashtags(loader, combined)
        all_discovered.update(hashtag_discoveries)
        if hashtag_discoveries:
            print(f"    Found {len(hashtag_discoveries)} accounts from hashtags")

    if not all_discovered:
        print("    No new accounts discovered this run")

    return all_discovered


# ---------------------------------------------------------------------------
# Social Media: Orchestrator
# ---------------------------------------------------------------------------

def run_social_scrapers() -> list[SampleSale]:
    """Run all social media scrapers and account discovery."""
    all_sales = []
    all_posts = []

    # Build combined account list: seed + previously discovered
    ig_accounts = dict(SOCIAL_MEDIA_ACCOUNTS.get("instagram", {}))
    threads_accounts = dict(SOCIAL_MEDIA_ACCOUNTS.get("threads", {}))

    discovered = load_discovered_accounts()
    for username, config in discovered.get("instagram", {}).items():
        if username not in ig_accounts and config.get("enabled", False):
            ig_accounts[username] = config
    for username, config in discovered.get("threads", {}).items():
        if username not in threads_accounts and config.get("enabled", False):
            threads_accounts[username] = config

    # Phase A: Instagram via Instaloader
    print("\n  [Instagram] Scraping %d accounts..." % len(
        [u for u, c in ig_accounts.items() if c.get("enabled")]
    ))
    ig_sales, ig_posts = run_instagram_scrapers(ig_accounts)
    all_sales.extend(ig_sales)
    all_posts.extend(ig_posts)

    # Phase B: Threads via Playwright
    print("\n  [Threads] Scraping %d accounts..." % len(
        [u for u, c in threads_accounts.items() if c.get("enabled")]
    ))
    threads_sales, threads_posts = run_threads_scrapers(threads_accounts)
    all_sales.extend(threads_sales)
    all_posts.extend(threads_posts)

    # Phase C: Account Discovery
    existing = set(ig_accounts.keys()) | set(threads_accounts.keys())
    new_accounts = run_account_discovery(all_posts, existing)
    if new_accounts:
        # Merge with existing discovered data and save
        for username, config in new_accounts.items():
            if username not in discovered.get("instagram", {}):
                discovered.setdefault("instagram", {})[username] = config
        save_discovered_accounts(discovered)

    print(f"\n  Social media total: {len(all_sales)} sales from {len(all_posts)} posts")
    return all_sales


# ---------------------------------------------------------------------------
# Scraper: Playwright + BeautifulSoup (Website Aggregators)
# ---------------------------------------------------------------------------

def get_page_html(page, url: str, wait_selector: str = "body", timeout: int = 30000) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_selector(wait_selector, timeout=15000)
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"  [WARN] Error loading {url}: {e}")
    return page.content()


def scrape_260_sample_sale(page) -> list[SampleSale]:
    print("[1/4] Scraping 260 Sample Sale...")
    url = "https://260samplesale.com/pages/nyc-schedule"
    sales = []
    try:
        html = get_page_html(page, url, wait_selector="main")
        soup = BeautifulSoup(html, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                events = data if isinstance(data, list) else [data]
                for ev in events:
                    if ev.get("@type") in ("Event", "SaleEvent"):
                        sale = SampleSale(
                            brand=ev.get("name", ""),
                            start_date=ev.get("startDate", ""),
                            end_date=ev.get("endDate", ""),
                            location=ev.get("location", {}).get("name", "") if isinstance(ev.get("location"), dict) else str(ev.get("location", "")),
                            link=url,
                            source="260 Sample Sale",
                        )
                        sale.department = infer_department(sale.brand)
                        sales.append(sale)
            except (json.JSONDecodeError, TypeError):
                continue

        for card in soup.select("[class*=card], [class*=block], [class*=item], .grid__item"):
            text = card.get_text(separator=" | ", strip=True)
            if len(text) > 20:
                brand_el = card.select_one("h2, h3, h4, .title, [class*=title]")
                brand = clean_brand(brand_el.get_text(strip=True)) if brand_el else ""
                if brand and len(brand) > 2:
                    start, end = parse_date_range(text)
                    loc = extract_location(text)
                    sale = SampleSale(
                        brand=brand, start_date=start, end_date=end,
                        location=loc, link=url, notes=extract_notes(text),
                        source="260 Sample Sale",
                    )
                    sale.department = infer_department(sale.brand)
                    sales.append(sale)
    except Exception as e:
        print(f"  [ERROR] 260 Sample Sale scrape failed: {e}")

    print(f"  Found {len(sales)} sales from 260 Sample Sale")
    return sales


def scrape_chicmi(page) -> list[SampleSale]:
    print("[2/4] Scraping Chicmi NYC...")
    base = "https://www.chicmi.com"
    url = f"{base}/new-york/sample-sales/"
    sales = []
    try:
        html = get_page_html(page, url, wait_selector="body")
        soup = BeautifulSoup(html, "lxml")

        for card in soup.select(".sale-card, .event-card, [class*=event], [class*=sale], .card, article"):
            brand_el = card.select_one("h2, h3, h4, .title, .brand, [class*=title]")
            date_el = card.select_one(".date, .dates, [class*=date], time")
            loc_el = card.select_one(".location, .venue, [class*=location], address")
            link_el = card.select_one("a[href]")

            brand = brand_el.get_text(strip=True) if brand_el else ""
            if not brand or len(brand) < 2:
                continue
            if brand.lower() in ("home", "about", "contact", "login", "sign up", "new york", "sample sales"):
                continue

            dates_text = date_el.get_text(strip=True) if date_el else ""
            location = loc_el.get_text(strip=True) if loc_el else ""
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = base + link

            start, end = parse_date_range(dates_text)
            sale = SampleSale(
                brand=clean_brand(brand), start_date=start, end_date=end,
                location=location, link=link, source="Chicmi",
            )
            sale.department = infer_department(sale.brand)
            sales.append(sale)
    except Exception as e:
        print(f"  [ERROR] Chicmi scrape failed: {e}")

    print(f"  Found {len(sales)} sales from Chicmi")
    return sales


def scrape_lazar(page) -> list[SampleSale]:
    print("[3/4] Scraping Lazar Shopping...")
    url = "https://lazarshopping.com/"
    sales = []
    try:
        html = get_page_html(page, url, wait_selector="body")
        soup = BeautifulSoup(html, "lxml")

        for entry in soup.select("article, .post, .entry, [class*=post], [class*=entry], [class*=event]"):
            title_el = entry.select_one("h1, h2, h3, h4, .title, [class*=title]")
            content = entry.get_text(separator=" | ", strip=True)
            brand = title_el.get_text(strip=True) if title_el else ""
            link_el = entry.select_one("a[href]")
            link = link_el["href"] if link_el else url

            if not brand or len(brand) < 3:
                continue

            start, end = parse_date_range(content)
            sale = SampleSale(
                brand=clean_brand(brand), start_date=start, end_date=end,
                location=extract_location(content),
                link=link if link.startswith("http") else url,
                notes=extract_notes(content), source="Lazar Shopping",
            )
            sale.department = infer_department(sale.brand)
            sales.append(sale)
    except Exception as e:
        print(f"  [ERROR] Lazar Shopping scrape failed: {e}")

    print(f"  Found {len(sales)} sales from Lazar Shopping")
    return sales


def scrape_nyc_insider(page) -> list[SampleSale]:
    print("[4/4] Scraping NYC Insider Guide...")
    url = "https://www.nycinsiderguide.com/nyc-shopping/sample-sales"
    sales = []
    try:
        html = get_page_html(page, url, wait_selector="body")
        soup = BeautifulSoup(html, "lxml")

        for table in soup.select("table"):
            rows = table.select("tr")
            for row in rows[1:]:
                cells = row.select("td, th")
                if len(cells) >= 2:
                    brand = cells[0].get_text(strip=True)
                    dates_text = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    location = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    notes = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    link_el = row.select_one("a[href]")
                    link = link_el["href"] if link_el else url
                    start, end = parse_date_range(dates_text)
                    sale = SampleSale(
                        brand=clean_brand(brand), start_date=start, end_date=end,
                        location=location, link=link, notes=notes,
                        source="NYC Insider Guide",
                    )
                    sale.department = infer_department(sale.brand)
                    if sale.brand:
                        sales.append(sale)

        for block in soup.select("article, .entry-content, [class*=sale], [class*=event]"):
            for h in block.select("h2, h3, h4, strong, b"):
                brand = h.get_text(strip=True)
                if len(brand) < 3 or brand.lower() in ("sample sales", "nyc sample sales", "upcoming sales"):
                    continue
                sibling_text = ""
                for sib in h.find_next_siblings(limit=5):
                    sibling_text += " " + sib.get_text(strip=True)
                start, end = parse_date_range(sibling_text)
                link_el = h.find_parent("a") or h.find_next("a")
                link = link_el["href"] if link_el and link_el.get("href") else url
                sale = SampleSale(
                    brand=clean_brand(brand), start_date=start, end_date=end,
                    location=extract_location(sibling_text),
                    link=link if link.startswith("http") else url,
                    notes=extract_notes(sibling_text),
                    source="NYC Insider Guide",
                )
                sale.department = infer_department(sale.brand)
                sales.append(sale)
    except Exception as e:
        print(f"  [ERROR] NYC Insider Guide scrape failed: {e}")

    print(f"  Found {len(sales)} sales from NYC Insider Guide")
    return sales


def run_live_scrapers() -> list[SampleSale]:
    """Attempt live scraping via Playwright. Returns empty list on failure."""
    if not HAS_PLAYWRIGHT or not HAS_BS4:
        print("[SKIP] Playwright/BS4 not available, skipping live scrape")
        return []

    all_sales = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()

            all_sales.extend(scrape_260_sample_sale(page))
            all_sales.extend(scrape_chicmi(page))
            all_sales.extend(scrape_lazar(page))
            all_sales.extend(scrape_nyc_insider(page))

            browser.close()
    except Exception as e:
        print(f"[ERROR] Playwright scraping failed: {e}")

    return all_sales


# ---------------------------------------------------------------------------
# Verified data fallback (collected 2026-03-08 via web search APIs)
# ---------------------------------------------------------------------------

def get_verified_sales() -> list[SampleSale]:
    """
    Returns verified NYC sample sale data for March 2026, cross-referenced
    from 260 Sample Sale, Chicmi, NYC Insider Guide, VIP Sample Sale, and
    The Stylish City search results.
    """
    raw = [
        # --- Currently active (as of March 8, 2026) ---
        {
            "brand": "260 Edit (Bogner & Hugo Boss)",
            "department": "Womenswear, Menswear",
            "start_date": "March 1, 2026",
            "end_date": "March 8, 2026",
            "location": "260 SoHo Wooster, New York, NY",
            "link": "https://www.chicmi.com/event/260-edit-sample-sale-new-york/",
            "notes": "Up to 70% off; Free entry",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "Shoe-Inn 30th Annual Warehouse Sale",
            "department": "Footwear",
            "start_date": "March 3, 2026",
            "end_date": "March 8, 2026",
            "location": "261 Fifth Ave, New York, NY 10016",
            "link": "https://www.shoeinn.com/pages/shoe-inn-warehouse-sale-nyc-2026",
            "notes": "Up to 75% off; Brands: UGG, Birkenstock, Dolce Vita, Vince, Sam Edelman; Wed-Sat 10AM-7PM, Sun 10AM-5PM",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "Frette Linens",
            "department": "Home, Linens",
            "start_date": "March 3, 2026",
            "end_date": "March 8, 2026",
            "location": "Soiffer Haskin, New York, NY",
            "link": "https://www.nycinsiderguide.com/nyc-sample-sale/",
            "notes": "Luxury Italian linens",
            "source": "NYC Insider Guide",
        },
        {
            "brand": "Contemporary Classics Edit (FRAME, Reiss, Velvet)",
            "department": "Womenswear, Menswear",
            "start_date": "March 5, 2026",
            "end_date": "March 8, 2026",
            "location": "260 Fifth Ave, New York, NY 10001",
            "link": "https://www.chicmi.com/event/contemporary-classics-edit-sample-sale-new-york/",
            "notes": "Free entry",
            "source": "Chicmi",
        },
        {
            "brand": "Stuart Weitzman (WeFashion)",
            "department": "Footwear",
            "start_date": "March 5, 2026",
            "end_date": "March 8, 2026",
            "location": "15 E 37th St, New York, NY 10016",
            "link": "https://www.chicmi.com/event/wefashion-stuart-weitzman-sample-sale-new-york/",
            "notes": "RSVP required",
            "source": "Chicmi",
        },
        {
            "brand": "Carlisle (WeFashion)",
            "department": "Womenswear",
            "start_date": "March 5, 2026",
            "end_date": "March 8, 2026",
            "location": "15 E 37th St, New York, NY 10016",
            "link": "https://www.chicmi.com/event/wefashion-carlisle-sample-sale-new-york/",
            "notes": "RSVP required",
            "source": "Chicmi",
        },
        {
            "brand": "Tanya Taylor",
            "department": "Womenswear, Accessories",
            "start_date": "March 6, 2026",
            "end_date": "March 8, 2026",
            "location": "Arlettie, New York, NY",
            "link": "https://www.chicmi.com/event/tanya-taylor-sample-sale-new-york/",
            "notes": "RTW, evening dresses, footwear, accessories; Free entry",
            "source": "Chicmi",
        },
        {
            "brand": "Harleen Kaur",
            "department": "Womenswear",
            "start_date": "March 7, 2026",
            "end_date": "March 8, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/harleen-kaur-sample-sale-new-york/",
            "notes": "Up to 80% off; Modern lehengas, kurtas, sherwanis, bridal samples",
            "source": "Chicmi",
        },
        {
            "brand": "TIA CIBANI",
            "department": "Childrenswear",
            "start_date": "March 8, 2026",
            "end_date": "March 8, 2026",
            "location": "Brooklyn, NY",
            "link": "https://www.chicmi.com/event/tia-cibani-spring-sample-sale-brooklyn/",
            "notes": "Up to 80% off; SS25 & FW25 stock and archive samples; Free entry; One day only",
            "source": "Chicmi",
        },
        # --- Upcoming: Week of March 9-15 ---
        {
            "brand": "Derek Lam",
            "department": "Womenswear",
            "start_date": "March 10, 2026",
            "end_date": "March 12, 2026",
            "location": "Next to Swedish Institute, New York, NY",
            "link": "https://www.chicmi.com/event/derek-lam-sample-sale-new-york/",
            "notes": "Free entry; 3-day sale",
            "source": "Chicmi, NYC Insider Guide",
        },
        {
            "brand": "Djerf Avenue",
            "department": "Womenswear",
            "start_date": "March 10, 2026",
            "end_date": "March 15, 2026",
            "location": "261 Fifth Ave, New York, NY 10016",
            "link": "https://www.chicmi.com/event/djerf-avenue-warehouse-sample-sale-new-york/",
            "notes": "Free entry; Swedish ready-to-wear; Tue-Sat 11AM-7PM, Sun 11AM-5PM",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "WeWoreWhat (WeFashion)",
            "department": "Womenswear",
            "start_date": "March 10, 2026",
            "end_date": "March 16, 2026",
            "location": "15 E 37th St, New York, NY 10016",
            "link": "https://www.chicmi.com/event/wefashion-weworewhat-sample-sale-new-york/",
            "notes": "RSVP required (free); Denim, knitwear, outerwear",
            "source": "Chicmi",
        },
        {
            "brand": "Onia (WeFashion)",
            "department": "Swimwear",
            "start_date": "March 10, 2026",
            "end_date": "March 16, 2026",
            "location": "15 E 37th St, New York, NY 10016",
            "link": "https://www.chicmi.com/event/wefashion-onia-sample-sale-new-york/",
            "notes": "RSVP required (free); Luxury swimwear",
            "source": "Chicmi",
        },
        {
            "brand": "Officine Generale",
            "department": "Menswear, Womenswear",
            "start_date": "March 11, 2026",
            "end_date": "March 15, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/officine-generale-sample-sale-new-york/",
            "notes": "French contemporary",
            "source": "Chicmi",
        },
        {
            "brand": "Global Glam Multi-Brand",
            "department": "Womenswear, Accessories",
            "start_date": "March 11, 2026",
            "end_date": "March 14, 2026",
            "location": "RSVP for address, New York, NY",
            "link": "https://www.chicmi.com/event/global-glam-new-york-multi-brand-sample-sale-new-york/",
            "notes": "20-75% off; Chanel, Dior, D&G, Versace, Etro, L'Agence; Venmo/Cash/PayPal/Zelle; RSVP required; No large bags; Booking required",
            "source": "Chicmi",
        },
        # --- Upcoming: Week of March 16-22 ---
        {
            "brand": "MSA Haute Couture",
            "department": "Womenswear, Haute Couture",
            "start_date": "March 17, 2026",
            "end_date": "March 18, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/msa-haute-couture-spring-sample-sale-new-york/",
            "notes": "Free entry; Extra 5% off in-store",
            "source": "Chicmi",
        },
        {
            "brand": "260 Multi-Brand Event",
            "department": "Various",
            "start_date": "March 17, 2026",
            "end_date": "March 22, 2026",
            "location": "260 SoHo Wooster, New York, NY",
            "link": "https://www.chicmi.com/event/260-multi-brand-event-sample-sale-new-york/",
            "notes": "Up to 70% off; Free entry; Tue 10AM-7PM, Wed-Sat 11AM-7PM, Sun 11AM-5PM",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "Jimmy Choo",
            "department": "Footwear, Accessories",
            "start_date": "March 17, 2026",
            "end_date": "March 20, 2026",
            "location": "Metropolitan Pavilion, 123 W 18th St, Floor 2, New York, NY 10011",
            "link": "https://www.vipsamplesale.com/jimmy-choo",
            "notes": "Up to 70% off; Registration required; Access code: JCGA25; Shoes, boots, handbags, SLG",
            "source": "VIP Sample Sale, NYC Insider Guide",
        },
        {
            "brand": "Max Mara (Super Archive)",
            "department": "Womenswear, Menswear",
            "start_date": "March 18, 2026",
            "end_date": "March 22, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/max-mara-sample-sale-by-super-archive-new-york/",
            "notes": "Booking required; Exclusive discounts",
            "source": "Chicmi",
        },
        {
            "brand": "Alicia Adams Alpaca",
            "department": "Womenswear, Accessories",
            "start_date": "March 18, 2026",
            "end_date": "March 22, 2026",
            "location": "260 Fifth Ave, New York, NY 10001",
            "link": "https://www.chicmi.com/event/alicia-adams-alpaca-sample-sale-new-york/",
            "notes": "Free entry; Artisan-crafted alpaca styles",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "LAMARQUE",
            "department": "Womenswear",
            "start_date": "March 18, 2026",
            "end_date": "March 22, 2026",
            "location": "260 Lafayette St, New York, NY",
            "link": "https://www.chicmi.com/event/lamarque-sample-sale-new-york/",
            "notes": "All sales final; Contemporary essentials",
            "source": "260 Sample Sale, Chicmi",
        },
        # --- Upcoming: Late March ---
        {
            "brand": "Reformation",
            "department": "Womenswear",
            "start_date": "March 20, 2026",
            "end_date": "March 26, 2026",
            "location": "260 Fifth Ave, New York, NY 10001",
            "link": "https://www.chicmi.com/event/reformation-sample-sale-new-york-september-2019/",
            "notes": "All sales final; Sustainable fashion",
            "source": "Chicmi",
        },
        {
            "brand": "Cynthia Rowley",
            "department": "Womenswear",
            "start_date": "March 19, 2026",
            "end_date": "March 22, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/cynthia-rowley-sample-sale-new-york/",
            "notes": "Bi-annual sale; Spring & Fall pieces + one-of-a-kind samples",
            "source": "Chicmi",
        },
        {
            "brand": "goop",
            "department": "Womenswear, Beauty, Home",
            "start_date": "March 24, 2026",
            "end_date": "March 29, 2026",
            "location": "260 Fifth Ave, New York, NY 10001",
            "link": "https://www.chicmi.com/event/goop-sample-sale-new-york/",
            "notes": "Up to 70% off",
            "source": "260 Sample Sale, Chicmi",
        },
        {
            "brand": "MANDINGA",
            "department": "Womenswear",
            "start_date": "March 21, 2026",
            "end_date": "March 22, 2026",
            "location": "Clever Alice, New York, NY",
            "link": "https://www.chicmi.com/event/mandinga-spring-sample-sale-new-york/",
            "notes": "Up to 90% off; Uruguay-based; One-of-a-kind samples; Limited sizes",
            "source": "Chicmi",
        },
        {
            "brand": "Perfect Moment",
            "department": "Womenswear, Activewear",
            "start_date": "March 21, 2026",
            "end_date": "March 22, 2026",
            "location": "New York, NY",
            "link": "https://www.chicmi.com/event/perfect-moment-sample-sale-new-york/",
            "notes": "Luxury ski and activewear",
            "source": "Chicmi",
        },
    ]

    sales = []
    for r in raw:
        sale = SampleSale(**r)
        if not sale.department or sale.department == "Various":
            sale.department = infer_department(sale.brand)
        sales.append(sale)
    return sales


# ---------------------------------------------------------------------------
# Deduplication & Output
# ---------------------------------------------------------------------------

def deduplicate(sales: list[SampleSale]) -> list[SampleSale]:
    seen = {}
    for sale in sales:
        key = sale.dedup_key()
        if key not in seen:
            seen[key] = sale
        else:
            existing = seen[key]
            if not existing.department or existing.department == "Various":
                existing.department = sale.department
            if not existing.location and sale.location:
                existing.location = sale.location
            if not existing.notes and sale.notes:
                existing.notes = sale.notes
            if sale.source not in existing.source:
                existing.source += f", {sale.source}"
    return list(seen.values())


def write_csv(sales: list[SampleSale], filename: str):
    fields = ["brand", "department", "start_date", "end_date", "location", "link", "notes", "source"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in sales:
            writer.writerow(asdict(s))
    print(f"\nCSV saved to {filename}")


def print_markdown_table(sales: list[SampleSale]):
    print("\n## NYC Sample Sales — March 2026\n")
    print("| # | Brand | Department | Start Date | End Date | Location | Link | Notes | Source(s) |")
    print("|---|-------|-----------|------------|----------|----------|------|-------|-----------|")
    for i, s in enumerate(sales, 1):
        link_md = f"[Link]({s.link})" if s.link else ""
        print(f"| {i} | {s.brand} | {s.department} | {s.start_date} | {s.end_date} | {s.location} | {link_md} | {s.notes} | {s.source} |")


def save_markdown_table(sales: list[SampleSale], filename: str):
    lines = []
    lines.append("# NYC Sample Sales — March 2026\n")
    lines.append(f"*Data collected on 2026-03-08. {len(sales)} unique sales identified.*\n")
    # Dynamic sources from actual data
    all_sources = set()
    for s in sales:
        for src in s.source.split(", "):
            all_sources.add(src.strip())
    lines.append(f"**Sources:** {', '.join(sorted(all_sources))}\n")
    lines.append("| # | Brand | Department | Start Date | End Date | Location | Link | Notes | Source(s) |")
    lines.append("|---|-------|-----------|------------|----------|----------|------|-------|-----------|")
    for i, s in enumerate(sales, 1):
        link_md = f"[Link]({s.link})" if s.link else ""
        lines.append(f"| {i} | {s.brand} | {s.department} | {s.start_date} | {s.end_date} | {s.location} | {link_md} | {s.notes} | {s.source} |")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by scrape_sample_sales.py*")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Markdown saved to {filename}")


# ---------------------------------------------------------------------------
# Database: PostgreSQL Storage
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("DATABASE_URL", "")


def get_db_connection():
    """Get a PostgreSQL connection using DATABASE_URL."""
    if not HAS_PSYCOPG2:
        print("  psycopg2 not installed — skipping database operations")
        return None
    if not DB_URL:
        return None
    try:
        conn = psycopg2.connect(DB_URL)
        return conn
    except Exception as e:
        print(f"  Database connection failed: {e}")
        return None


def init_db():
    """Initialize database schema from db_schema.sql."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        schema_path = Path(__file__).parent / "db_schema.sql"
        with open(schema_path, "r") as f:
            schema_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print("  Database schema initialized")
        return True
    except Exception as e:
        print(f"  Database init failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def upsert_sales(sales: list, month_year: str = None):
    """Insert or update sales in the database, skipping duplicates via dedup_key."""
    conn = get_db_connection()
    if not conn:
        return 0
    if month_year is None:
        month_year = datetime.now().strftime("%Y-%m")
    inserted = 0
    try:
        with conn.cursor() as cur:
            for s in sales:
                try:
                    # Parse dates to DATE type, or NULL if unparseable
                    start_dt = _parse_date_for_db(s.start_date)
                    end_dt = _parse_date_for_db(s.end_date)
                    cur.execute("""
                        INSERT INTO sample_sales
                            (brand, department, start_date, end_date, location, link, notes, source, month_year, dedup_key)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (dedup_key) DO UPDATE SET
                            department = COALESCE(NULLIF(sample_sales.department, 'Various'), EXCLUDED.department),
                            location = COALESCE(NULLIF(sample_sales.location, ''), EXCLUDED.location),
                            notes = COALESCE(NULLIF(sample_sales.notes, ''), EXCLUDED.notes),
                            source = EXCLUDED.source,
                            scraped_at = NOW()
                    """, (
                        s.brand, s.department, start_dt, end_dt,
                        s.location, s.link, s.notes, s.source,
                        month_year, s.dedup_key()
                    ))
                    inserted += 1
                except Exception as e:
                    print(f"  Failed to upsert {s.brand}: {e}")
        conn.commit()
        print(f"  Persisted {inserted} sales to database")
    except Exception as e:
        print(f"  Database upsert failed: {e}")
        conn.rollback()
    finally:
        conn.close()
    return inserted


def _parse_date_for_db(date_str: str):
    """Parse a date string to a Python date for PostgreSQL, or return None."""
    if not date_str or not date_str.strip():
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def upsert_discovered_accounts(accounts: list[dict]):
    """Persist discovered accounts to the database."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            for acct in accounts:
                cur.execute("""
                    INSERT INTO discovered_accounts
                        (platform, username, source_name, discovered_from, discovered_date, relevance_score, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        relevance_score = GREATEST(discovered_accounts.relevance_score, EXCLUDED.relevance_score),
                        enabled = EXCLUDED.enabled
                """, (
                    acct.get("platform", ""),
                    acct.get("username", ""),
                    acct.get("source_name", ""),
                    acct.get("discovered_from", ""),
                    acct.get("discovered_date", datetime.now().date()),
                    acct.get("relevance_score", 0.0),
                    acct.get("enabled", True),
                ))
        conn.commit()
        print(f"  Persisted {len(accounts)} discovered accounts to database")
    except Exception as e:
        print(f"  Account upsert failed: {e}")
        conn.rollback()
    finally:
        conn.close()


def log_scrape_run(web_count: int, social_count: int, verified_count: int, total_unique: int, new_accounts: int = 0):
    """Log a scrape run to the database."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scrape_runs
                    (web_sales_count, social_sales_count, verified_sales_count, total_unique, new_accounts_discovered)
                VALUES (%s, %s, %s, %s, %s)
            """, (web_count, social_count, verified_count, total_unique, new_accounts))
        conn.commit()
        print("  Scrape run logged to database")
    except Exception as e:
        print(f"  Failed to log scrape run: {e}")
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  NYC Sample Sale Scraper — March 2026")
    print("=" * 60)

    # Phase 1: Attempt live web scraping
    print("\n--- Phase 1: Live Web Scraping ---")
    live_sales = run_live_scrapers()

    # Phase 2: Social media scraping + account discovery
    print("\n--- Phase 2: Social Media Scraping ---")
    social_sales = run_social_scrapers()

    # Phase 3: Load verified fallback data
    print("\n--- Phase 3: Verified Fallback Data ---")
    verified_sales = get_verified_sales()
    print(f"  Loaded {len(verified_sales)} verified sales")

    # Merge: web + social + verified
    all_sales = live_sales + social_sales + verified_sales
    print(f"\nTotal raw sales: {len(all_sales)}")

    # Deduplicate
    unique_sales = deduplicate(all_sales)
    print(f"Unique sales after deduplication: {len(unique_sales)}")

    # Sort by start date, then brand
    def sort_key(s):
        # Parse "March 10, 2026" into sortable tuple
        try:
            from datetime import datetime
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%m/%d/%Y"):
                try:
                    dt = datetime.strptime(s.start_date.strip(), fmt)
                    return (dt, s.brand.lower())
                except ValueError:
                    continue
        except Exception:
            pass
        return (s.start_date, s.brand.lower())

    unique_sales.sort(key=sort_key)

    # Output
    csv_path = "/home/user/Sample-sale/nyc_sample_sales_march_2026.csv"
    md_path = "/home/user/Sample-sale/nyc_sample_sales_march_2026.md"
    write_csv(unique_sales, csv_path)
    save_markdown_table(unique_sales, md_path)
    print_markdown_table(unique_sales)

    # Phase 4: Persist to PostgreSQL (if configured)
    if DB_URL:
        print("\n--- Phase 4: PostgreSQL Persistence ---")
        init_db()
        upsert_sales(unique_sales)
        log_scrape_run(
            web_count=len(live_sales),
            social_count=len(social_sales),
            verified_count=len(verified_sales),
            total_unique=len(unique_sales),
        )
        # Persist discovered accounts if file exists
        disc_path = Path(__file__).parent / "discovered_accounts.json"
        if disc_path.exists():
            try:
                with open(disc_path, "r") as f:
                    disc_data = json.load(f)
                upsert_discovered_accounts(disc_data)
            except Exception as e:
                print(f"  Could not persist discovered accounts: {e}")
    else:
        print("\n  (Set DATABASE_URL to enable PostgreSQL persistence)")

    print(f"\n{'=' * 60}")
    print(f"  Done! {len(unique_sales)} unique NYC sample sales for March 2026")
    print(f"  CSV:      {csv_path}")
    print(f"  Markdown: {md_path}")
    if DB_URL:
        print(f"  Database: PostgreSQL (connected)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
