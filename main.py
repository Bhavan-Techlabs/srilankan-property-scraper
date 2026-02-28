#!/usr/bin/env python3
"""
ikman.lk Property Scraper
Scrapes house-for-sale ads from ikman.lk, detects duplicates,
and writes structured data to Google Sheets.
"""

import argparse
import logging
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

import yaml

from scraper import get_listings, get_ad_details, extract_location_name
from data_processor import build_row, row_to_list
from duplicate_detector import DuplicateDetector
from sheets import get_spreadsheet, get_or_create_worksheet, get_existing_data, append_rows, clear_worksheet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ikman_scraper")


def load_config(config_path):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def process_location(url, config, spreadsheet):
    """Scrape a single location URL and write results to its worksheet."""
    location_name = extract_location_name(url)
    logger.info("=" * 60)
    logger.info("Processing location: %s", location_name)
    logger.info("URL: %s", url)
    logger.info("=" * 60)

    worksheet = get_or_create_worksheet(spreadsheet, location_name)

    existing_data = get_existing_data(worksheet)
    logger.info("Found %d existing entries in sheet '%s'", len(existing_data), location_name)

    threshold = config.get("similarity_threshold", 0.9)
    detector = DuplicateDetector(threshold=threshold)
    detector.load_existing(existing_data)

    logger.info("Fetching listing pages...")
    listings = get_listings(url, config)
    logger.info("Found %d ads in listings", len(listings))

    request_delay = config.get("request_delay", 1.5)
    new_rows = []
    duplicates_found = 0
    errors = 0

    for i, listing in enumerate(listings, 1):
        ad_url = listing.get("ad_url")
        if not ad_url:
            continue

        logger.info("[%d/%d] Fetching details: %s", i, len(listings), listing.get("title", "")[:60])

        try:
            details = get_ad_details(ad_url, request_delay=request_delay)
        except Exception as e:
            logger.error("Failed to fetch ad details for %s: %s", ad_url, e)
            errors += 1
            continue

        description = details.get("description", "")

        is_dup, match_type, matching_url = detector.check(ad_url, description)

        if is_dup:
            duplicates_found += 1
            logger.info("  -> Skipped duplicate (%s match with %s)", match_type, matching_url)
            continue

        detector.add_entry(ad_url, description)
        row = build_row(listing, details, location_name)
        new_rows.append(row_to_list(row))

    if new_rows:
        append_rows(worksheet, new_rows)

    logger.info(
        "Location '%s' complete: %d new rows, %d duplicates, %d errors",
        location_name, len(new_rows), duplicates_found, errors,
    )
    return len(new_rows), duplicates_found, errors


def main():
    parser = argparse.ArgumentParser(description="ikman.lk Property Scraper")
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clear all existing data from sheets before scraping",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    spreadsheet_id = config.get("spreadsheet_id", "")
    if not spreadsheet_id or spreadsheet_id == "YOUR_SPREADSHEET_ID_HERE":
        logger.error("Please set a valid 'spreadsheet_id' in %s", args.config)
        sys.exit(1)

    credentials_path = config.get("credentials_path", "credentials.json")
    urls = config.get("urls", [])

    if not urls:
        logger.error("No URLs configured in %s", args.config)
        sys.exit(1)

    logger.info("Starting ikman.lk scraper with %d location(s)", len(urls))

    spreadsheet = get_spreadsheet(credentials_path, spreadsheet_id)

    if args.clean:
        logger.info("Cleaning all sheets before scraping...")
        for url in urls:
            location_name = extract_location_name(url)
            try:
                ws = spreadsheet.worksheet(location_name)
                clear_worksheet(ws)
                logger.info("Cleared sheet: %s", location_name)
            except Exception:
                pass

    total_new = 0
    total_dups = 0
    total_errors = 0

    for url in urls:
        try:
            new, dups, errs = process_location(url, config, spreadsheet)
            total_new += new
            total_dups += dups
            total_errors += errs
        except Exception as e:
            logger.error("Failed to process %s: %s", url, e, exc_info=True)
            total_errors += 1

    logger.info("=" * 60)
    logger.info("SCRAPING COMPLETE")
    logger.info("Total rows written: %d", total_new)
    logger.info("Total duplicates found: %d", total_dups)
    logger.info("Total errors: %d", total_errors)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
