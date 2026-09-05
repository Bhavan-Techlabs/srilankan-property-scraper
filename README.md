# Sri Lanka House Sales Scraper

A Python web scraper that extracts house-for-sale and house-for-rent listings from multiple Sri Lankan property sites — [ikman.lk](https://ikman.lk/), [lankapropertyweb.com](https://lankapropertyweb.com/), [ceylonproperty.lk](https://ceylonproperty.lk/), [house.lk](https://house.lk/), and [lankaland.lk](https://www.lankaland.lk/) — and writes structured data to Excel (.xlsx) and/or Google Sheets. Supports multiple locations, sale and rental listings, price filtering, pagination, duplicate detection, and value scoring.

**Repository:** https://github.com/Bhavan-Techlabs/srilankan-property-scraper

---

## Features

- **Multi-site scraping** — ikman.lk, lankapropertyweb.com, ceylonproperty.lk, house.lk, and lankaland.lk supported out of the box
- **Multi-location** — configure any number of URLs; each location gets its own sheet tab
- **Sale and rent support** — each URL's own shape tells the scraper whether it's a sale or rental listing; each city gets a separate `City` (sale) and `City (Rent)` sheet, each with its own price filter and its own Overview ranking
- **Full ad details** — visits each individual ad page to extract bedrooms, bathrooms, land size, house size, address, and more
- **Source tracking** — each row records which website the listing came from
- **Price filtering** — separate min/max price ranges for sale (`price_filter`) and rent (`rent_price_filter`), globally or via URL parameters
- **Age cutoff** — only scrape ads posted within the last N days (ikman.lk)
- **Smart pagination** — handles promoted/featured/bumped ads correctly without stopping early
- **Duplicate detection** — skips ads already in the sheet by exact URL match or 90%+ title similarity (catches reposted ads with new URLs); sale and rent entries are never compared against each other
- **Value scoring** — separate **Overview** (sale) and **Overview (Rent)** tabs rank listings by space-per-rupee score, each including Address so the best-value result can be located without opening its location tab
- **Excel output** — one tab per location (×2 for sale/rent) with auto-formatting, column widths, and clickable hyperlinks; uploaded as a GitHub Actions artifact
- **Google Sheets output** — auto-creates tabs, formats headers, sorts by posted date
- **Clean mode** — option to clear all sheets and start fresh
- **GitHub Actions** — runs every 24 hours on a cron schedule; Excel file available as a downloadable artifact (retained 30 days)

## How It Works

```
Config → per-location loop:
  factory dispatch (ikman / lankapropertyweb / ceylonproperty / house.lk / lankaland)
  → detect sale vs. rent from the URL → fetch listing pages
  → filter by price (sale or rent price_filter) / age → fetch ad detail pages
  → deduplicate → build rows → append to "City" or "City (Rent)" Excel/Sheets tab
  → rebuild the Overview and Overview (Rent) tabs with value scores
```

ikman.lk listings are extracted from the embedded `window.initialData` JSON on each page. lankapropertyweb.com, ceylonproperty.lk, house.lk, and lankaland.lk are parsed from server-rendered HTML via BeautifulSoup.

> **Known limitation:** house.lk and lankapropertyweb.com sit behind Cloudflare, which blocks GitHub Actions' hosted-runner IP ranges with an HTTP 403 on every request (confirmed not to be a scraper bug — the same request succeeds from a residential IP). The scheduled workflow degrades gracefully: those two sites error out per-location while the other three keep scraping normally. See `.github/workflows/scrape-selfhosted.yml` below for a manual workaround.

## Data Columns

| Column | Description |
|---|---|
| Title | Ad title |
| Location | Location name (derived from the URL) |
| Bedrooms | Number of bedrooms |
| Bathrooms | Number of bathrooms |
| Land Size (Perches) | Land area in perches |
| House Size (SqFt) | Built area in square feet |
| Price (LKR) | Price (total for sale, monthly for rent) |
| Address | Property address |
| URL | Clickable link to the original ad |
| Source | Website domain the listing came from |
| Posted | Approximate date the ad was posted |
| Date Scraped | When the scraper collected this data |
| Status | For your own tracking (preserved across runs) |
| Notes | For your own notes (preserved across runs) |

The **Overview** and **Overview (Rent)** tabs are auto-rebuilt after every run, each ranking its own listing type across all locations by a value score (space per rupee spent).

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Bhavan-Techlabs/srilankan-property-scraper.git
cd srilankan-property-scraper
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Edit `config.yaml` with your desired URLs, price range, and output mode. Sale and rent URLs are mixed in the same `urls` list — each URL's own shape tells the scraper which one it is.

```yaml
output_mode: "excel"   # "excel" | "sheets" | "both"

urls:
  - "https://ikman.lk/en/ads/colombo/houses-for-sale"
  - "https://ikman.lk/en/ads/colombo/houses-for-rent"
  - "https://ceylonproperty.lk/sale/property/in-colombo?toAmount=30000000"
  - "https://www.lankapropertyweb.com/sale/index.php?search=1&location=Western_Colombo&property-type=House"
  - "https://house.lk/sale/colombo/colombo/house/"
  - "https://www.lankaland.lk/search-results/?category=house&status=sale&city=colombo"

price_filter:            # sale URLs only (total purchase price, LKR)
  min: 5000000
  max: 30000000

rent_price_filter:        # rent URLs only (monthly rent, LKR)
  min: 20000
  max: 150000

max_age_days: 15
max_pages: 20
```

### 4. (Optional) Google Sheets output

Only needed when `output_mode` is `"sheets"` or `"both"`:

1. Go to [Google Cloud Console](https://console.cloud.google.com/), create a project, and enable the **Google Sheets API** and **Google Drive API**
2. Create a **Service Account** and download its JSON key as `credentials.json` in the project root
3. Share your Google Sheet with the service account's `client_email` as an **Editor**
4. Add the spreadsheet ID to `config.yaml` under `spreadsheet_id`

## Usage

```bash
# Incremental run — appends new listings, preserves existing data
python main.py

# Clear all sheets then scrape fresh
python main.py --clean

# Use a custom config file
python main.py --config path/to/config.yaml
```

## GitHub Actions

The included `.github/workflows/scrape.yml` runs every 24 hours (`0 0 * * *`) and on manual dispatch, on a GitHub-hosted `ubuntu-latest` runner. It:

1. Writes `credentials.json` from the `GOOGLE_CREDENTIALS` secret (skipped if not set)
2. Runs the scraper
3. Uploads `output/*.xlsx` as a downloadable artifact named `srilanka-house-sales` (retained 30 days)

### Setup

1. Push the repository to GitHub
2. Add secrets under **Settings > Secrets and variables > Actions**:
   - `GOOGLE_CREDENTIALS` — full contents of `credentials.json` (only if using Sheets output)

### Manual trigger

```bash
gh workflow run scrape.yml
```

Or click **Run workflow** from the Actions tab on GitHub.

### Self-hosted runner (manual, for the house.lk / lankapropertyweb.com Cloudflare block)

`.github/workflows/scrape-selfhosted.yml` is a second, manually-triggered-only workflow (never scheduled) that targets a `self-hosted-local` runner instead of GitHub's hosted infrastructure — this runs from your own IP, which isn't blocked by Cloudflare. It reuses this project's existing `venv/` directly with no install step.

```bash
# 1. Start the runner listener (from repo root; blocks in the foreground)
cd .actions-runner && ./run.sh

# 2. In another terminal, once it shows "Listening for Jobs":
gh workflow run scrape-selfhosted.yml

# 3. When done, stop the listener:
pkill -f "actions-runner/bin/Runner.Listener"
```

The runner isn't set up by default — see `CLAUDE.md` for full registration/removal steps.

## Project Structure

```
├── .github/workflows/
│   ├── scrape.yml               # Scheduled GitHub-hosted workflow (24-hour cron)
│   └── scrape-selfhosted.yml    # Manual-only workflow for the self-hosted runner
├── main.py                      # CLI entry point
├── scraper_factory.py           # Routes URLs to the correct scraper, detects sale vs. rent
├── scraper_ikman.py             # ikman.lk scraper
├── scraper_lankapropertyweb.py  # lankapropertyweb.com scraper
├── scraper_ceylonproperty.py    # ceylonproperty.lk scraper
├── scraper_houselk.py           # house.lk scraper
├── scraper_lankaland.py         # lankaland.lk scraper
├── data_processor.py            # Data normalization, row building, value scoring
├── duplicate_detector.py        # URL + title similarity matching
├── excel_writer.py              # Excel output with formatting and Overview/Overview (Rent) tabs
├── sheets.py                    # Google Sheets read/write/format
├── config.yaml                  # Active configuration
└── requirements.txt             # Python dependencies
```

## Configuration Reference

| Key | Description | Default |
|---|---|---|
| `output_mode` | `"excel"` / `"sheets"` / `"both"` | `"excel"` |
| `spreadsheet_id` | Google Sheets document ID | — |
| `credentials_path` | Path to service account JSON | `credentials.json` |
| `urls` | List of property search URLs (sale and rent mixed) | — |
| `price_filter.min` / `.max` | Price bounds in LKR, sale URLs only | — |
| `rent_price_filter.min` / `.max` | Monthly rent bounds in LKR, rent URLs only | — |
| `max_age_days` | Skip ads older than N days (ikman only) | `14` |
| `max_pages` | Pagination limit per location | `20` |
| `similarity_threshold` | Duplicate detection sensitivity (0–1) | `0.9` |
| `request_delay` | Seconds between HTTP requests | `1.5` |

## Credits

This project is a fork of [ikman-scraper](https://github.com/randikabanura/ikman-scraper) by [@randikabanura](https://github.com/randikabanura), originally built as a single-site ikman.lk scraper. It has since been substantially extended with multi-site support, Excel output, value scoring, GitHub Actions artifact upload, and more.

## Disclaimer

This project is for educational and personal use only. Please respect each website's terms of service and use reasonable request delays.

## License

See [LICENSE](LICENSE)
