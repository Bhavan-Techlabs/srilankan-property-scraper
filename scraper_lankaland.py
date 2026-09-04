"""
Scraper for lankaland.lk property listings.
Parses HTML with BeautifulSoup (server-side rendered WordPress theme, no embedded JSON).
"""
import logging
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lankaland.lk"

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
    """Extract a readable location name from a lankaland.lk search-results URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    if "city" in qs:
        return qs["city"][0].replace("-", " ").replace("_", " ").title()
    if "district" in qs:
        return qs["district"][0].replace("-", " ").replace("_", " ").title()

    return "LankaLand"


def _build_page_url(base_url, page_no):
    """Build the URL for a given page number (WP-style /search-results/page/N/?query)."""
    if page_no == 1:
        return base_url

    parsed = urlparse(base_url)
    new_path = "/search-results/" + f"page/{page_no}/"
    return urljoin(BASE_URL, new_path) + (f"?{parsed.query}" if parsed.query else "")


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
    """Extract a numeric LKR value from strings like 'LKR 225,000,000 Whole property'."""
    if not text:
        return None, ""
    clean = text.strip()

    match = re.search(r"LKR\s*([\d,]+(?:\.\d+)?)", clean, re.IGNORECASE)
    if not match:
        return None, clean

    try:
        return int(float(match.group(1).replace(",", ""))), clean
    except ValueError:
        return None, clean


def _parse_listing_cards(html, price_min, price_max):
    """Parse property-item search-listing-item cards from a search results page."""
    soup = BeautifulSoup(html, "lxml")
    ads = []
    seen_urls = set()

    for card in soup.find_all("div", class_="search-listing-item"):
        a_tag = card.find("a", class_="full-link", href=True)
        if not a_tag:
            continue
        ad_url = urljoin(BASE_URL, a_tag["href"])
        if ad_url in seen_urls:
            continue
        seen_urls.add(ad_url)

        title_tag = card.find("h3")
        title = title_tag.get_text(strip=True) if title_tag else ""

        price_tag = card.find("div", class_="price")
        price_value = price_tag.find("span", class_="value") if price_tag else None
        price_text = price_value.get_text(strip=True) if price_value else ""
        numeric_price, price_raw = _parse_price(price_text)

        if price_min and numeric_price and numeric_price < price_min:
            continue
        if price_max and numeric_price and numeric_price > price_max:
            continue

        location_parts = [
            item.find("span", class_="value").get_text(strip=True)
            for item in card.find_all("div", class_="item")
            if item.find("span", class_="value")
        ]
        location_text = ", ".join(location_parts)

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
    """Check whether a next page link exists in the pagination widget."""
    soup = BeautifulSoup(html, "lxml")
    next_page = str(current_page + 1)
    pagination = soup.find("div", class_="pagination-wrapper")
    if not pagination:
        return False
    for a in pagination.find_all("a", href=True):
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

    logger.info("Collected %d ads from lankaland.lk", len(all_ads))
    return all_ads


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch and parse a single property detail page."""
    time.sleep(request_delay)
    html = _fetch_html(ad_url)
    soup = BeautifulSoup(html, "lxml")

    # Property Overview: repeating <li class="list-group-item"><strong>Label</strong><span>Value</span></li>
    spec_map = {}
    for li in soup.find_all("li", class_="list-group-item"):
        label = li.find("strong")
        value = li.find("span")
        if label and value:
            spec_map[label.get_text(strip=True).lower().rstrip(":")] = value.get_text(strip=True)

    address = spec_map.get("location", "")

    # Description: div#Property_Details holds the free-text specification paragraphs
    description = ""
    prop_details_div = soup.find("div", id="Property_Details")
    if prop_details_div:
        description = prop_details_div.get_text(separator=" ", strip=True)

    bedrooms = spec_map.get("rooms", "")
    bathrooms = spec_map.get("bathrooms", "")
    land_size = spec_map.get("land area (perches)", "")
    house_size = spec_map.get("floor area", "")

    # Description text is more reliable for bed/bath counts than the generic "Rooms" field
    m = re.search(r"bedrooms?[:\s]*([\d]+)", description, re.I)
    if m:
        bedrooms = m.group(1)
    m = re.search(r"bathrooms?[:\s]*([\d]+)", description, re.I)
    if m:
        bathrooms = m.group(1)

    return {
        "description": description,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "land_size": land_size,
        "house_size": house_size,
        "address": address,
        "posted_date": "",
    }
