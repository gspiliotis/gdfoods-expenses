# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python CLI tool that fetches expense invoice data from the Greek AADE myDATA API and appends it to a Google Sheets spreadsheet. It's designed to track invoices from specific suppliers (identified by VAT numbers) and automatically deduplicate records.

## Commands

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Applications

**fetch_expenses.py** - Fetch invoices and append to Google Sheets:
```bash
# Fetch today's invoices
python fetch_expenses.py

# Fetch invoices for a specific date range
python fetch_expenses.py --from-date 2025-01-01 --to-date 2025-01-31

# Use date offsets (e.g., yesterday)
python fetch_expenses.py --from-date-offset -1 --to-date-offset -1

# Specify custom VAT file and sheet name
python fetch_expenses.py --vat-file vat_numbers.txt --sheet-name "Expenses"
```

**analyze_items.py** - Analyze invoice line items and generate CSV:
```bash
# Analyze today's invoices
python analyze_items.py

# Analyze for a date range
python analyze_items.py --from-date 2025-01-01 --to-date 2025-01-31

# Custom output files
python analyze_items.py --output my_items.csv --issuers-output missing_items.txt
```

### Docker
```bash
# Build locally
docker build -t expenses-fetcher .

# Pull from GHCR
docker pull ghcr.io/gspiliotis/expenses:latest
```

## Architecture

Two Python scripts share similar API fetching patterns:

**fetch_expenses.py** - Fetch invoices and append to Google Sheets:
- **`fetch_invoices()`** - Makes API requests to myDATA with pagination support
- **`parse_invoices()`** - Parses XML responses, extracts invoice data, handles invoice types (5.1/5.2 are credit notes with reversed amounts)
- **`fetch_all_invoices()`** - Fetches all invoices then filters locally by issuer VAT numbers
- **`append_to_google_sheets()`** - Appends to Google Sheets with deduplication based on series+aa composite key

**analyze_items.py** - Analyze invoice line items:
- **`parse_invoice_items()`** - Extracts `invoiceDetails` elements (itemDescr, quantity, netValue)
- **`aggregate_items()`** - Groups by item description, calculates total quantity and average net value
- Outputs CSV with aggregated items and separate file for issuers missing item descriptions

## Key Technical Details

- **VAT file format**: `vat_numbers.txt` contains VAT numbers with optional names: `VAT_NUMBER<whitespace>NAME`
- **Deduplication**: Records are identified by combining `series` and `aa` (invoice number) columns
- **Invoice types 5.1/5.2**: Credit notes - amounts are negated when these types are encountered
- **API date format**: Internally converts YYYY-MM-DD to DD/MM/YYYY for the myDATA API

## Environment Variables

Required in `.env` (see `.env.example`):
- `MYDATA_USER_ID` - myDATA API user ID
- `MYDATA_API_KEY` - myDATA API subscription key
- `GOOGLE_SPREADSHEET_ID` - Target Google Spreadsheet ID
- `GOOGLE_CREDENTIALS_FILE` - Path to service account JSON (default: `google-credentials.json`)

## CI/CD

GitHub Actions workflow (`.github/workflows/docker-publish.yml`) automatically builds and publishes Docker images to ghcr.io when relevant files are changed on main branch.
