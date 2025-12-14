# Expense Invoice Fetcher

This Python project fetches expense invoice data from the Greek AADE myDATA API and appends it to a Google Workspace spreadsheet.

## Features

- Fetches invoice data from AADE myDATA API for multiple suppliers
- Extracts key invoice information including dates, VAT numbers, payment methods, and amounts
- Appends data directly to Google Sheets
- Supports pagination for large result sets
- Optional date range parameters (defaults to current date)

## Prerequisites

1. Python 3.7 or higher (or Docker)
2. AADE myDATA API credentials (User ID and API Key)
3. Google Cloud Service Account with Google Sheets API access
4. Google Spreadsheet ID where data will be appended

## Installation

### Option 1: Local Python Installation

1. Create a virtual environment (recommended):
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Option 2: Docker

The application is available as a Docker container and is automatically built and published to GitHub Container Registry when changes are pushed to the main branch.

#### Pull from GitHub Container Registry:

```bash
docker pull ghcr.io/gspiliotis/expenses:latest
```

#### Or build locally:

```bash
docker build -t expenses-fetcher .
```

## Configuration

### 1. Set up AADE myDATA API credentials

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and add:
- `MYDATA_USER_ID`: Your myDATA API user ID
- `MYDATA_API_KEY`: Your myDATA API subscription key
- `GOOGLE_SPREADSHEET_ID`: The ID from your Google Spreadsheet URL
- `GOOGLE_CREDENTIALS_FILE`: Path to your service account JSON file (default: google-credentials.json)

### 2. Set up Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API
4. Create a Service Account:
   - Go to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Give it a name and click "Create"
   - Click "Continue" and then "Done"
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to the "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose "JSON" and click "Create"
   - Save the downloaded file as `google-credentials.json` in this directory
6. Share your Google Spreadsheet with the service account email address
   - Open your Google Spreadsheet
   - Click "Share"
   - Add the service account email (found in google-credentials.json as "client_email")
   - Give it "Editor" permissions

### 3. Configure VAT numbers

Edit `vat_numbers.txt` and add the VAT numbers of suppliers you want to fetch invoices from, one per line:

```
094254743
998117733
998603201
```

Lines starting with `#` are treated as comments.

## Usage

### Python (Local Installation)

#### Basic usage (fetch today's invoices):

```bash
python fetch_expenses.py
```

#### Fetch invoices for a specific date range:

```bash
python fetch_expenses.py --from-date 2025-01-01 --to-date 2025-01-31
```

#### Specify a different sheet name:

```bash
python fetch_expenses.py --sheet-name "Expenses"
```

#### All options:

```bash
python fetch_expenses.py \
  --from-date 2025-01-01 \
  --to-date 2025-01-31 \
  --vat-file vat_numbers.txt \
  --sheet-name "Sheet1"
```

### Docker

When using Docker, you need to:
1. Mount your credentials file
2. Mount your VAT numbers file (or use the default one included in the image)
3. Pass environment variables for configuration

#### Basic usage with Docker:

```bash
docker run --rm \
  -v $(pwd)/google-credentials.json:/app/google-credentials.json \
  -e MYDATA_USER_ID="your_user_id" \
  -e MYDATA_API_KEY="your_api_key" \
  -e GOOGLE_SPREADSHEET_ID="your_spreadsheet_id" \
  -e GOOGLE_CREDENTIALS_FILE="/app/google-credentials.json" \
  ghcr.io/gspiliotis/expenses:latest
```

#### Fetch invoices for a specific date range with Docker:

```bash
docker run --rm \
  -v $(pwd)/google-credentials.json:/app/google-credentials.json \
  -e MYDATA_USER_ID="your_user_id" \
  -e MYDATA_API_KEY="your_api_key" \
  -e GOOGLE_SPREADSHEET_ID="your_spreadsheet_id" \
  -e GOOGLE_CREDENTIALS_FILE="/app/google-credentials.json" \
  ghcr.io/gspiliotis/expenses:latest \
  --from-date 2025-01-01 \
  --to-date 2025-01-31
```

#### Using a custom VAT numbers file:

```bash
docker run --rm \
  -v $(pwd)/google-credentials.json:/app/google-credentials.json \
  -v $(pwd)/my-vat-numbers.txt:/app/vat_numbers.txt \
  -e MYDATA_USER_ID="your_user_id" \
  -e MYDATA_API_KEY="your_api_key" \
  -e GOOGLE_SPREADSHEET_ID="your_spreadsheet_id" \
  -e GOOGLE_CREDENTIALS_FILE="/app/google-credentials.json" \
  ghcr.io/gspiliotis/expenses:latest \
  --vat-file vat_numbers.txt
```

#### Using an environment file with Docker:

Create a `.env` file with your credentials and use it with Docker:

```bash
docker run --rm \
  -v $(pwd)/google-credentials.json:/app/google-credentials.json \
  --env-file .env \
  ghcr.io/gspiliotis/expenses:latest \
  --from-date 2025-01-01 \
  --to-date 2025-01-31
```

## Output Format

The script appends the following columns to your Google Sheet:

1. **Issue Date**: Invoice issue date (YYYY-MM-DD)
2. **VAT**: Supplier VAT number
3. **Name**: Supplier name
4. **Series**: Invoice series
5. **AA**: Invoice number
6. **Payment Methods**: Comma-separated list of payment method types
7. **Total Amount**: Total invoice amount (sum of all payment amounts)

## Troubleshooting

### Authentication errors

- Verify your AADE myDATA credentials in the `.env` file
- Ensure your API key is active and has the necessary permissions

### Google Sheets errors

- Verify that the service account email has "Editor" access to your spreadsheet
- Check that the `GOOGLE_SPREADSHEET_ID` in `.env` is correct
- Ensure the `google-credentials.json` file exists and is valid
- Make sure the sheet name specified with `--sheet-name` exists in your spreadsheet

### No data found

- Verify the VAT numbers in `vat_numbers.txt` are correct
- Check the date range - there may be no invoices for the specified period
- Review the API response for any error messages

## Example

```bash
# Fetch all invoices from January 1-31, 2025
python fetch_expenses.py --from-date 2025-01-01 --to-date 2025-01-31

# Output:
# Found 4 VAT number(s) to process
# Date range: 2025-01-01 to 2025-01-31
#
# Fetching invoices for VAT: 094254743
#   Page 1: Found 15 invoice(s)
#   Total invoices for 094254743: 15
# ...
# Total invoices fetched: 45
# Successfully appended 45 row(s) to Google Sheets
# Done!
```

## CI/CD and Container Registry

This project includes a GitHub Actions workflow that automatically builds and publishes the Docker image to GitHub Container Registry (ghcr.io) when changes are pushed to the main branch.

### Automatic Builds

The workflow triggers on:
- Pushes to the `main` branch that modify:
  - `fetch_expenses.py`
  - `requirements.txt`
  - `Dockerfile`
  - `.github/workflows/docker-publish.yml`
- Manual workflow dispatch

### Image Tags

Published images are tagged with:
- `main` - Latest build from the main branch
- `main-<commit-sha>` - Specific commit SHA for reproducibility
- `latest` - Latest stable release (when on default branch)

### Pulling Images

After the workflow runs successfully, you can pull the image:

```bash
docker pull ghcr.io/gspiliotis/expenses:latest
docker pull ghcr.io/gspiliotis/expenses:main
docker pull ghcr.io/gspiliotis/expenses:main-abc1234
```

### Setting up the Workflow

The workflow uses the default `GITHUB_TOKEN` which is automatically available. No additional secrets are required.

To enable the workflow:
1. Push your code to a GitHub repository
2. The workflow will run automatically on the next push to main
3. Published packages will appear in your repository's "Packages" section

## License

This project is for internal use only.
