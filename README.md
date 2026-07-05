# Sri Lanka House Sales Scraper

A Python web scraper that extracts house-for-sale listings from multiple Sri Lankan property sites — [ikman.lk](https://ikman.lk/), [lankapropertyweb.com](https://lankapropertyweb.com/), and [ceylonproperty.lk](https://ceylonproperty.lk/) — and writes structured data to Excel (.xlsx) and/or Google Sheets. Supports multiple locations, price filtering, pagination, duplicate detection, and value scoring.

**Repository:** https://github.com/Bhavan-Techlabs/srilankan-property-scraper

---

## Features

- **Multi-site scraping** — ikman.lk, lankapropertyweb.com, and ceylonproperty.lk supported out of the box
- **Multi-location** — configure any number of URLs; each location gets its own sheet tab
- **Full ad details** — visits each individual ad page to extract description, bedrooms, bathrooms, land size, house size, address, and more
- **Source tracking** — each row records which website the listing came from
- **Price filtering** — filter ads by min/max price range, globally or via URL parameters
- **Age cutoff** — only scrape ads posted within the last N days (ikman.lk)
- **Smart pagination** — handles promoted/featured/bumped ads correctly without stopping early
- **Duplicate detection** — skips ads already in the sheet by exact URL match or 90%+ description similarity (catches reposted ads with new URLs)
- **Value scoring** — Overview tab ranks all listings by space-per-rupee score across all locations and sources
- **Excel output** — one tab per location with auto-formatting, column widths, and clickable hyperlinks; uploaded as a GitHub Actions artifact
- **Google Sheets output** — auto-creates tabs, formats headers, sorts by posted date
- **Clean mode** — option to clear all sheets and start fresh
- **GitHub Actions** — runs every 12 hours on a cron schedule; Excel file available as a downloadable artifact (retained 30 days)

## How It Works

```
Config → per-location loop:
  factory dispatch (ikman / lankapropertyweb / ceylonproperty)
  → fetch listing pages → filter by price/age
  → fetch ad detail pages → deduplicate
  → build rows → append to Excel tab and/or Google Sheets tab
  → rebuild Overview tab with value scores
```

ikman.lk listings are extracted from the embedded `window.initialData` JSON on each page. lankapropertyweb.com and ceylonproperty.lk are parsed from server-rendered HTML via BeautifulSoup.

## Data Columns

| Column | Description |
|---|---|
| Title | Ad title |
| Location | Location name (derived from the URL) |
| Bedrooms | Number of bedrooms |
| Bathrooms | Number of bathrooms |
| Land Size (Perches) | Land area in perches |
| House Size (SqFt) | Built area in square feet |
| Price (LKR) | Price in Sri Lankan rupees |
| Address | Property address |
| Description | Full ad description |
| URL | Clickable link to the original ad |
| Source | Website domain the listing came from |
| Posted | Approximate date the ad was posted |
| Date Scraped | When the scraper collected this data |
| Status | For your own tracking (preserved across runs) |
| Notes | For your own notes (preserved across runs) |

The **Overview** tab is auto-rebuilt after every run and ranks all listings across all locations by a value score (space per rupee).

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

Edit `config.yaml` with your desired URLs, price range, and output mode.

```yaml
output_mode: "excel"   # "excel" | "sheets" | "both"

urls:
  - "https://ikman.lk/en/ads/colombo/houses-for-sale"
  - "https://ceylonproperty.lk/sale/property/in-colombo?toAmount=30000000"
  - "https://www.lankapropertyweb.com/sale/index.php?search=1&location=Western_Colombo&property-type=House"

price_filter:
  min: 5000000
  max: 30000000

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

The included `.github/workflows/scrape.yml` runs every 12 hours (`0 */12 * * *`) and on manual dispatch. It:

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

## Project Structure

```
├── .github/workflows/
│   └── scrape.yml              # GitHub Actions workflow (12-hour cron)
├── main.py                     # CLI entry point
├── scraper_factory.py          # Routes URLs to the correct scraper
├── scraper_ikman.py            # ikman.lk scraper
├── scraper_lankapropertyweb.py # lankapropertyweb.com scraper
├── scraper_ceylonproperty.py   # ceylonproperty.lk scraper
├── data_processor.py           # Data normalization, row building, value scoring
├── duplicate_detector.py       # URL + description similarity matching
├── excel_writer.py             # Excel output with formatting and Overview tab
├── sheets.py                   # Google Sheets read/write/format
├── config.yaml                 # Active configuration
├── config.example.yaml         # Sample configuration
└── requirements.txt            # Python dependencies
```

## Configuration Reference

| Key | Description | Default |
|---|---|---|
| `output_mode` | `"excel"` / `"sheets"` / `"both"` | `"excel"` |
| `spreadsheet_id` | Google Sheets document ID | — |
| `credentials_path` | Path to service account JSON | `credentials.json` |
| `urls` | List of property search URLs | — |
| `price_filter.min` / `.max` | Price bounds in LKR | — |
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
