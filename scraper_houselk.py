"""
Scraper for house.lk property listings.
Parses HTML with BeautifulSoup (server-side rendered WPResidence theme, no embedded JSON).
"""
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://house.lk"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_location_name(url):
    """Extract a readable location name from a house.lk URL (/sale/{district}/{city}/house/)."""
    parsed = urlparse(url)
    match = re.search(r"/(?:sale|rent)/[^/]+/([^/]+)/house/?", parsed.path)
    if match:
        return match.group(1).replace("-", " ").replace("_", " ").title()
    return "House.lk"


def _build_page_url(base_url, page_no):
    """Build the URL for a given page number."""
    base = base_url if base_url.endswith("/") else base_url + "/"
    if page_no == 1:
        return base
    return urljoin(base, f"page/{page_no}/")


def _fetch_html(url, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.text
            logger.warning("Attempt %d/%d HTTP %d for %s", attempt, max_retries, resp.status_code, url)
        except requests.RequestException as e:
            logger.warning("Attempt %d/%d error for %s: %s", attempt, max_retries, url, e)
        if attempt < max_retries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


def _parse_price(text):
    """Extract a numeric LKR value from strings like 'Rs. 175M' or 'Rs. 35,000,000'."""
    if not text:
        return None, ""
    clean = text.strip()

    match = re.search(r"Rs\.?\s*([\d,]+(?:\.\d+)?)\s*([MBK])?", clean, re.IGNORECASE)
    if not match:
        return None, clean

    raw = match.group(1).replace(",", "")
    multiplier = {"M": 1_000_000, "B": 1_000_000_000, "K": 1_000}.get(
        (match.group(2) or "").upper(), 1
    )
    try:
        return int(float(raw) * multiplier), clean
    except ValueError:
        return None, clean


def _parse_posted_date(text):
    """Convert 'Posted/edited: X ago' style text to YYYY-MM-DD."""
    if not text:
        return ""
    ts = text.strip().lower()
    now = datetime.now()

    if "just now" in ts or "today" in ts:
        return now.strftime("%Y-%m-%d")

    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?", ts)
    if not match:
        return ""
    value = int(match.group(1))
    unit = match.group(2)
    deltas = {
        "second": timedelta(seconds=value),
        "minute": timedelta(minutes=value),
        "hour": timedelta(hours=value),
        "day": timedelta(days=value),
        "week": timedelta(weeks=value),
        "month": timedelta(days=value * 30),
        "year": timedelta(days=value * 365),
    }
    return (now - deltas.get(unit, timedelta())).strftime("%Y-%m-%d")


def _parse_listing_cards(html, price_min, price_max):
    """Parse property_listing cards from a search results page."""
    soup = BeautifulSoup(html, "lxml")
    ads = []
    seen_urls = set()

    for card in soup.find_all("div", class_="property_listing"):
        a_tag = card.find("a", href=re.compile(r"/details/"))
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        ad_url = urljoin(BASE_URL, href)
        if ad_url in seen_urls:
            continue
        seen_urls.add(ad_url)

        h4 = card.find("h4")
        title = h4.get_text(strip=True) if h4 else ""

        price_tag = card.find("div", class_="listing_unit_price_wrapper")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        numeric_price, price_raw = _parse_price(price_text)

        if price_min and numeric_price and numeric_price < price_min:
            continue
        if price_max and numeric_price and numeric_price > price_max:
            continue

        location_tag = card.find("div", class_="action_tag_location_wrapper")
        location_text = location_tag.get_text(strip=True) if location_tag else ""

        ads.append({
            "title": title,
            "price_raw": price_raw,
            "price_numeric": numeric_price,
            "location": location_text,
            "ad_url": ad_url,
            "time_stamp": "",
        })

    return ads


def _has_next_page(html, current_page):
    """Check whether a next page link exists."""
    soup = BeautifulSoup(html, "lxml")
    next_page = str(current_page + 1)
    for a in soup.find_all("a", href=True):
        if f"/page/{next_page}/" in a["href"]:
            return True
    return False


def get_listings(base_url, config):
    """Scrape all listing pages and return summary dicts."""
    max_pages = config.get("max_pages", 20)
    request_delay = config.get("request_delay", 1.5)
    pf = config.get("price_filter") or {}
    price_min = pf.get("min")
    price_max = pf.get("max")

    all_ads = []

    for page_no in range(1, max_pages + 1):
        page_url = _build_page_url(base_url, page_no)
        logger.info("Fetching listing page %d: %s", page_no, page_url)

        html = _fetch_html(page_url)
        ads = _parse_listing_cards(html, price_min, price_max)
        logger.info("Page %d: found %d ads", page_no, len(ads))

        if not ads:
            logger.info("No ads found on page %d, stopping", page_no)
            break

        all_ads.extend(ads)

        if not _has_next_page(html, page_no):
            logger.info("No next page after page %d, stopping", page_no)
            break

        time.sleep(request_delay)

    logger.info("Collected %d ads from house.lk", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch and parse a single property detail page."""
    time.sleep(request_delay)
    html = _fetch_html(ad_url)
    soup = BeautifulSoup(html, "lxml")

    # Address: div.property_categs directly after the <h1> title
    address = ""
    addr_div = soup.find("div", class_="property_categs")
    if addr_div:
        address = addr_div.get_text(strip=True)

    # Specs: repeating <ul class="overview_element"><li class="first_overview_date">VALUE</li></ul>
    bedrooms = bathrooms = house_size = ""
    for ul in soup.find_all("ul", class_="overview_element"):
        li = ul.find("li", class_="first_overview_date")
        if not li:
            continue
        text = li.get_text(strip=True)
        if re.search(r"bedroom", text, re.I):
            m = re.search(r"([\d.]+)", text)
            bedrooms = m.group(1) if m else ""
        elif re.search(r"bathroom", text, re.I):
            m = re.search(r"([\d.]+)", text)
            bathrooms = m.group(1) if m else ""
        elif re.search(r"sq\.?\s*ft", text, re.I):
            house_size = text

    # Description (also carries "Land Extent: N Perches" — not exposed as an icon stat)
    description = ""
    land_size = ""
    desc_div = soup.find("div", class_="wpestate_property_description")
    if desc_div:
        description = desc_div.get_text(separator=" ", strip=True)
        m = re.search(r"Land\s*Extent[:\s]*([\d.]+)\s*Perch", description, re.I)
        if m:
            land_size = m.group(1)

    # Posted date: "Posted/edited: Today" / "Posted/edited: 3 days ago"
    posted_date = ""
    for tag in soup.find_all(string=re.compile(r"Posted\s*/\s*edited", re.I)):
        posted_date = _parse_posted_date(tag.strip())
        if posted_date:
            break

    return {
        "description": description,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "land_size": land_size,
        "house_size": house_size,
        "address": address,
        "posted_date": posted_date,
    }
