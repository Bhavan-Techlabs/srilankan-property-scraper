# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Sri Lankan House Scraper is a Python web scraper that extracts house-for-sale and house-for-rent listings from multiple Sri Lankan property sites (ikman.lk, lankapropertyweb.com, ceylonproperty.lk, house.lk, lankaland.lk) and writes structured property data to Excel (.xlsx) and/or Google Sheets. It runs every 12 hours via GitHub Actions, which uploads the Excel file as a downloadable artifact.

## Setup

```bash
pip install -r requirements.txt
# config.yaml is committed and used directly — edit output_mode and URLs as needed
```

Only one file must be present locally and is gitignored:
- `credentials.json` — Google service account key for Sheets API (only needed when output_mode includes "sheets")

## Running

```bash
# Incremental run — appends new listings, preserves existing data
python main.py

# Clear all sheets then scrape fresh
python main.py --clean

# Use a custom config file
python main.py --config path/to/config.yaml
```

## Architecture

The scraper is a linear pipeline over location URLs defined in config:

```
Config → output backend(s) init → per-location loop:
  factory dispatch → detect sale vs. rent from the URL → fetch listing pages
  → filter by price (sale or rent price_filter)/age → fetch ad detail pages
  → deduplicate → build rows → append to "City" or "City (Rent)" sheet tab
  and/or Google Sheets tab → sort & format → rebuild both Overview tabs
```

**Modules:**

- `main.py` — CLI entry point; `process_location(url, config, excel_mod, spreadsheet)` drives the per-location loop
- `scraper_factory.py` — factory that dispatches `get_listings`, `get_ad_details`, `extract_location_name` to the right scraper based on URL domain; `detect_listing_type(url)` returns `"sale"` or `"rent"` based on the URL shape
- `scraper_ikman.py` — ikman.lk scraper; HTTP fetching; extracts embedded `window.initialData` JSON; handles pagination and promoted-ad filtering
- `scraper_lankapropertyweb.py` — lankapropertyweb.com scraper; parses HTML with BeautifulSoup; handles pagination via URL query params
- `scraper_ceylonproperty.py` — ceylonproperty.lk scraper; parses server-side rendered HTML with BeautifulSoup; handles pagination via URL query params
- `scraper_houselk.py` — house.lk scraper (WPResidence theme); parses server-side rendered HTML; pagination via `/page/N/` path segment; land size and posted date come from parsing the free-text description block (not exposed as structured fields on this site)
- `scraper_lankaland.py` — lankaland.lk scraper; parses server-side rendered HTML; search filtered via `?category=house&status=sale&city=...` query params, pagination via `/search-results/page/N/?...`; posted date is not available on this site (always blank)
- `data_processor.py` — normalizes scraped data into typed flat dicts matching `COLUMNS`; `compute_value_score` scores listings by price/land/house/beds/baths
- `duplicate_detector.py` — `DuplicateDetector` class checks exact URL match first, then falls back to `difflib.SequenceMatcher` description similarity (threshold configurable, default 0.9)
- `excel_writer.py` — writes/appends rows to `output/srilanka_house_sales_YYYY-MM-DD.xlsx`; one sheet tab per location (per sale/rent split, see below); auto-column widths; typed cell storage; the **Description** column is written but hidden (kept for cross-run duplicate detection, not meant to be read); rebuilds the **Overview** and **Overview (Rent)** tabs after each write with value-scored listings (including Address) sorted by score
- `sheets.py` — Google Sheets API via service account; auto-creates tabs per location; auto-sorts by Posted date; auto-formats headers and row height

## Key Behaviors to Know

**Output mode**: Controlled by `output_mode` in `config.yaml`:
- `"excel"` — writes to `output/srilanka_house_sales_YYYY-MM-DD.xlsx` (default)
- `"sheets"` — writes to Google Sheets (requires `credentials.json` and `spreadsheet_id`)
- `"both"` — writes to both

**Multi-site factory**: `scraper_factory.py` inspects the URL domain and routes to `scraper_ikman.py` (ikman.lk), `scraper_lankapropertyweb.py` (lankapropertyweb.com), `scraper_ceylonproperty.py` (ceylonproperty.lk), `scraper_houselk.py` (house.lk), or `scraper_lankaland.py` (lankaland.lk). To add a new site, create a new `scraper_SITENAME.py` and add a domain check in the factory.

**Pagination cutoff (ikman)**: Stops paginating when a page has no organic (non-promoted) ads newer than `max_age_days`.

**Sale vs. rent detection**: `scraper_factory.detect_listing_type(url)` inspects the URL — a `rent`/`rental` path segment (ikman, lankapropertyweb, ceylonproperty, house.lk) or a `status=rent` query param (lankaland) marks it as `"rent"`; everything else defaults to `"sale"`. `main.py` uses this to pick the right price filter and sheet name per URL — no per-scraper changes needed to add rent support for a site.

**Price filtering**: Sale URLs use `price_filter.min`/`price_filter.max`; rent URLs use the separate `rent_price_filter.min`/`rent_price_filter.max` (monthly rent is a completely different scale to a total purchase price). Applied at config level unless the URL already contains price query parameters.

**Duplicate detection**: Catches both exact URL matches and description similarity matches (cross-batch against existing data and intra-batch). Sale and rent entries never dedupe against each other — each has its own sheet and its own existing-data lookup.

**Sheet layout**: Each location gets its own worksheet tab named after the location for sale listings (e.g. `Piliyandala`), and a second tab with ` (Rent)` appended for rentals (e.g. `Piliyandala (Rent)`). The `Location` cell value itself stays the plain city name in both — only the sheet/tab name carries the sale/rent distinction. Status and Notes columns are user-editable and preserved across incremental runs. The Description column is hidden by default (still present in the file for duplicate detection, not intended for manual review). **Overview** (sale) and **Overview (Rent)** tabs are auto-rebuilt after every write, each ranking only its own sheet type by value score, and each includes Address so the best-value result can be identified without opening its location tab.

**Value score**: `compute_value_score` in `data_processor.py` combines price, land size (perches), house size (sqft), bedrooms, and bathrooms into a composite score. It's dimensionally identical for sale and rent (space per rupee spent), but the two are never ranked together — sale price and monthly rent aren't comparable numbers, hence the separate Overview tabs. Address is not part of the numeric score (it isn't a size/price signal) but is surfaced alongside the score so a listing can actually be located.

**Public API of `excel_writer`**: `get_output_path()` (public alias for `_output_path`) and `get_existing_data(path, sheet_name)` are the two functions imported by `main.py`.

## GitHub Actions

`.github/workflows/scrape.yml` runs on a 12-hour cron (`0 */12 * * *`) and on manual dispatch. It:
1. Writes `credentials.json` from `GOOGLE_CREDENTIALS` secret (skipped if secret not set)
2. Runs the scraper
3. **Uploads `output/*.xlsx` as a downloadable artifact** named `srilanka-house-sales` (retained 30 days)
4. Cleans up `credentials.json`

The job timeout is 180 minutes.

## Repository

GitHub: https://github.com/Bhavan-Techlabs/srilankan-property-scraper

## Configuration Reference (`config.yaml`)

- `output_mode` — `"excel"` | `"sheets"` | `"both"` (default: `"excel"`)
- `spreadsheet_id` — Google Sheets document ID (only needed for Sheets output)
- `credentials_path` — path to service account JSON (default: `credentials.json`)
- `urls` — list of property search URLs (ikman.lk, lankapropertyweb.com, ceylonproperty.lk, house.lk, or lankaland.lk); sale and rent URLs are mixed in the same list, each URL's shape tells the scraper which one it is (see "Sale vs. rent detection" above)
- `price_filter.min` / `price_filter.max` — price filter in LKR, for sale URLs only
- `rent_price_filter.min` / `rent_price_filter.max` — price filter in LKR/month, for rent URLs only
- `max_age_days` — skip ads older than this (ikman.lk only)
- `max_pages` — pagination limit per location
- `similarity_threshold` — duplicate detection sensitivity (0–1, default 0.9)
- `request_delay` — seconds between HTTP requests
