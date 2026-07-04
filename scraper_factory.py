"""
Factory that dispatches scraping calls to the right scraper based on URL domain.
"""
from urllib.parse import urlparse

import scraper as ikman_scraper
import scraper_lankapropertyweb as lpw_scraper


def _domain(url):
    return urlparse(url).netloc.lower()


def get_listings(url, config):
    """Return listings from the appropriate scraper for the given URL."""
    domain = _domain(url)
    if "lankapropertyweb.com" in domain:
        return lpw_scraper.get_listings(url, config)
    return ikman_scraper.get_listings(url, config)


def get_ad_details(ad_url, request_delay=1.5):
    """Fetch ad details using the appropriate scraper."""
    domain = _domain(ad_url)
    if "lankapropertyweb.com" in domain:
        return lpw_scraper.get_ad_details(ad_url, request_delay=request_delay)
    return ikman_scraper.get_ad_details(ad_url, request_delay=request_delay)


def extract_location_name(url):
    """Extract human-readable location name using the appropriate scraper."""
    domain = _domain(url)
    if "lankapropertyweb.com" in domain:
        return lpw_scraper.extract_location_name(url)
    return ikman_scraper.extract_location_name(url)
