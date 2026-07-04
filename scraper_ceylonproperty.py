"""
Scraper for ceylonproperty.lk property listings.
Parses HTML with BeautifulSoup (server-side rendered, no embedded JSON).
"""
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://ceylonproperty.lk"

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
    """Extract a readable location name from a ceylonproperty URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if "city" in qs:
        return qs["city"][0].replace("-", " ").replace("_", " ").title()
    if "district" in qs:
        return qs["district"][0].replace("-", " ").replace("_", " ").title()

    # /sale/property/in-{city} URL pattern
    match = re.search(r"/in-([^/?]+)", parsed.path)
    if match:
        return match.group(1).replace("-", " ").replace("_", " ").title()

    return "CeylonProperty"


def _build_page_url(base_url, page_no):
    """Build the URL for a given page number."""
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    if page_no == 1:
        qs.pop("page", None)
    else:
        qs["page"] = [str(page_no)]

    # ceylonproperty uses sort=boosted on paginated pages
    if page_no > 1 and "sort" not in qs:
        qs["sort"] = ["boosted"]

    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))


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
    """Extract a numeric LKR value from strings like '50 Million (neg)' or '50,000,000 LKR'."""
    if not text:
        return None, ""
    clean = text.strip()

    # Format: "50,000,000 LKR ..."
    match = re.search(r"([\d,]+)\s*LKR", clean, re.IGNORECASE)
    if match:
        numeric = int(match.group(1).replace(",", ""))
        return numeric, clean

    # Format: "50 Million" / "1.5 Billion"
    match = re.search(r"([\d.]+)\s*(Million|Billion|Thousand|M|B|K)", clean, re.IGNORECASE)
    if match:
        val = float(match.group(1))
        mult = {"million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "b": 1_000_000_000,
                "thousand": 1_000, "k": 1_000}.get(match.group(2).lower(), 1)
        return int(val * mult), clean

    return None, clean


def _parse_posted_date(text):
    """Convert 'X minutes/hours/days ago' text to YYYY-MM-DD."""
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
    """Parse rp-item cards from a search results page (/sale/property/in-{city} layout)."""
    soup = BeautifulSoup(html, "lxml")
    ads = []
    seen_urls = set()

    for card in soup.find_all("div", class_="rp-item"):
        # URL: first <a href="/property/..."> or full URL
        a_tag = card.find("a", href=re.compile(r"/property/\d+"))
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        ad_url = urljoin(BASE_URL, href) if href.startswith("/") else href
        if ad_url in seen_urls:
            continue
        seen_urls.add(ad_url)

        # Title: h5 > a inside rp-info
        rp_info = card.find("div", class_="rp-info")
        title = ""
        if rp_info:
            h5 = rp_info.find("h5")
            if h5:
                title = h5.get_text(strip=True)

        # Price: a.rp-price
        price_tag = card.find("a", class_="rp-price")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        numeric_price, price_raw = _parse_price(price_text)

        if price_min and numeric_price and numeric_price < price_min:
            continue
        if price_max and numeric_price and numeric_price > price_max:
            continue

        # Location text: first <p> inside rp-info (has map-marker icon + city name)
        location_text = ""
        if rp_info:
            p = rp_info.find("p")
            if p:
                location_text = p.get_text(strip=True)

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
    """Check whether a next page link exists in the pagination section."""
    soup = BeautifulSoup(html, "lxml")
    next_page = str(current_page + 1)
    pagination = soup.find("div", class_="pagination") or soup.find("ul", class_=re.compile(r"paginat"))
    if pagination:
        for a in pagination.find_all("a", href=True):
            if f"page={next_page}" in a["href"]:
                return True
    # Fallback: search all links
    for a in soup.find_all("a", href=True):
        if f"page={next_page}" in a["href"]:
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

    logger.info("Collected %d ads from ceylonproperty.lk", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch and parse a single property detail page."""
    time.sleep(request_delay)
    html = _fetch_html(ad_url)
    soup = BeautifulSoup(html, "lxml")

    # Specs: div.box_property contains label + value, e.g. "Bedrooms3", "Land Area8.5Perches"
    bedrooms = bathrooms = land_size = house_size = address = ""
    for box in soup.find_all("div", class_="box_property"):
        txt = box.get_text(strip=True)
        if txt.lower().startswith("bedrooms"):
            bedrooms = txt[len("Bedrooms"):].strip()
        elif txt.lower().startswith("bathrooms"):
            bathrooms = txt[len("Bathrooms"):].strip()
        elif txt.lower().startswith("floor area"):
            house_size = txt[len("Floor Area"):].strip()
        elif txt.lower().startswith("land area"):
            land_size = txt[len("Land Area"):].strip()
        elif txt.lower().startswith("address"):
            address = txt[len("Address"):].strip()

    # Description
    description = ""
    desc_div = soup.find("div", class_="description")
    if desc_div:
        p = desc_div.find("p")
        description = p.get_text(strip=True) if p else desc_div.get_text(strip=True)

    # Posted date: "Posted / edited: 7 months ago"
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
