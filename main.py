#!/usr/bin/env python3
"""
Sri Lankan House Sales Scraper
Scrapes property listings from ikman.lk and lankapropertyweb.com,
detects duplicates, and writes structured data to Excel and/or Google Sheets.
"""

import argparse
import logging
import sys
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

import yaml

import scraper_factory as factory
from data_processor import build_row, row_to_list
from duplicate_detector import DuplicateDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("property_scraper")


def load_config(config_path):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _get_output_backends(config, args):
    """Return initialized (excel_writer, spreadsheet) based on output_mode config."""
    mode = config.get("output_mode", "excel").lower()
    use_excel = mode in ("excel", "both")
    use_sheets = mode in ("sheets", "both")

    excel_mod = None
    spreadsheet = None

    if use_excel:
        import excel_writer
        excel_mod = excel_writer

    if use_sheets:
        from sheets import get_spreadsheet
        spreadsheet_id = config.get("spreadsheet_id", "")
        if not spreadsheet_id or spreadsheet_id == "YOUR_SPREADSHEET_ID_HERE":
            logger.error("output_mode includes 'sheets' but no valid spreadsheet_id in config")
            sys.exit(1)
        credentials_path = config.get("credentials_path", "credentials.json")
        spreadsheet = get_spreadsheet(credentials_path, spreadsheet_id)

    return excel_mod, spreadsheet


def process_location(url, config, excel_mod, spreadsheet):
    """Scrape a single location URL and write results to configured output(s)."""
    location_name = factory.extract_location_name(url)
    logger.info("=" * 60)
    logger.info("Processing location: %s", location_name)
    logger.info("URL: %s", url)
    logger.info("=" * 60)

    # Load existing data for duplicate detection (prefer Excel when available)
    existing_data = []
    if excel_mod:
        from excel_writer import get_existing_data, get_output_path
        existing_data = get_existing_data(get_output_path(), location_name)
    elif spreadsheet:
        from sheets import get_existing_data as sheets_get_existing, get_or_create_worksheet
        ws = get_or_create_worksheet(spreadsheet, location_name)
        existing_data = sheets_get_existing(ws)

    logger.info("Found %d existing entries for '%s'", len(existing_data), location_name)

    threshold = config.get("similarity_threshold", 0.9)
    detector = DuplicateDetector(threshold=threshold)
    detector.load_existing(existing_data)

    logger.info("Fetching listing pages...")
    listings = factory.get_listings(url, config)
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
            details = factory.get_ad_details(ad_url, request_delay=request_delay)
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
        if excel_mod:
            excel_mod.append_rows(location_name, new_rows)
        if spreadsheet:
            from sheets import get_or_create_worksheet, append_rows as sheets_append
            ws = get_or_create_worksheet(spreadsheet, location_name)
            sheets_append(ws, new_rows)

    logger.info(
        "Location '%s' complete: %d new rows, %d duplicates, %d errors",
        location_name, len(new_rows), duplicates_found, errors,
    )
    return len(new_rows), duplicates_found, errors


def main():
    parser = argparse.ArgumentParser(description="Sri Lankan House Sales Scraper")
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clear all existing data before scraping",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    urls = config.get("urls", [])

    if not urls:
        logger.error("No URLs configured in %s", args.config)
        sys.exit(1)

    excel_mod, spreadsheet = _get_output_backends(config, args)

    if args.clean:
        logger.info("Cleaning all sheets before scraping...")
        for url in urls:
            location_name = factory.extract_location_name(url)
            if excel_mod:
                excel_mod.clear_sheet(location_name)
            if spreadsheet:
                from sheets import get_or_create_worksheet, clear_worksheet
                try:
                    ws = spreadsheet.worksheet(location_name)
                    clear_worksheet(ws)
                except Exception:
                    pass

    mode = config.get("output_mode", "excel")
    logger.info("Starting scraper — output_mode=%s, %d location(s)", mode, len(urls))

    total_new = 0
    total_dups = 0
    total_errors = 0

    for url in urls:
        try:
            new, dups, errs = process_location(url, config, excel_mod, spreadsheet)
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
    if excel_mod:
        logger.info("Excel output: %s", excel_mod.get_output_path())
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
