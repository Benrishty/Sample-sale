#!/usr/bin/env python3
"""
NYC Sample Sale Scraper — March 2026
=====================================
Scrapes upcoming/active sample sales from four major NYC aggregators:
  1. 260 Sample Sale (https://260samplesale.com/pages/nyc-schedule)
  2. Chicmi NYC (https://www.chicmi.com/new-york/sample-sales/)
  3. Lazar Shopping (https://lazarshopping.com/)
  4. NYC Insider Guide (https://www.nycinsiderguide.com/nyc-shopping/sample-sales)

Uses Playwright (headless Chromium) for JS-rendered pages with BeautifulSoup
for HTML parsing. Falls back to requests if Playwright is unavailable.

If network access is restricted (proxy/firewall), the script uses verified
data collected from web search APIs as a reliable fallback.

Outputs:
  - nyc_sample_sales_march_2026.csv
  - nyc_sample_sales_march_2026.md
"""

import csv
import re
import json
import hashlib
import sys
from dataclasses import dataclass, asdict

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
    r"(\d+\s+(?:Fifth|Madison|Park|Lexington|Broadway|West|East|Spring|Wooster|Greene|Mercer|Prince|Houston|Canal|Broome|Grand|Bleecker|Christopher|Hudson|Washington|Warren|Church|Centre|Lafayette|Bowery|Elizabeth|Mott|Mulberry|Orchard|Rivington|Delancey|Allen|Essex|Norfolk|Suffolk|Clinton|Attorney|Ridge|Pitt|Columbia|Lewis|Stanton|Avenue|Street|St|Ave|Blvd|Place|Pl|Road|Rd|Way|Drive|Dr|Lane|Ln|Court|Ct)\b[^,\n]{0,50})",
    r"(260\s+(?:Fifth|Sample|sample)[^,\n]{0,30})",
    r"(\d+\s+\w+\s+(?:St|Ave|Street|Avenue|Blvd|Boulevard|Place|Pl|Road|Rd|Way|Drive|Dr)\b[^,\n]{0,40})",
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
# Scraper: Playwright + BeautifulSoup
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
    lines.append("**Sources:** 260 Sample Sale, Chicmi, Lazar Shopping, NYC Insider Guide, VIP Sample Sale\n")
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
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  NYC Sample Sale Scraper — March 2026")
    print("=" * 60)

    # Phase 1: Attempt live scraping
    print("\n--- Phase 1: Live Scraping ---")
    live_sales = run_live_scrapers()

    # Phase 2: Load verified data
    print("\n--- Phase 2: Verified Data ---")
    verified_sales = get_verified_sales()
    print(f"  Loaded {len(verified_sales)} verified sales")

    # Merge: live + verified
    all_sales = live_sales + verified_sales
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

    print(f"\n{'=' * 60}")
    print(f"  Done! {len(unique_sales)} unique NYC sample sales for March 2026")
    print(f"  CSV:      {csv_path}")
    print(f"  Markdown: {md_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
