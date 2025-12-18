#!/usr/bin/env python3
"""
Fetch expense invoice data from myDATA API and append to Google Sheets.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from .env file
load_dotenv()

# API Constants - load from environment variables
USER_ID = os.getenv("MYDATA_USER_ID")
API_KEY = os.getenv("MYDATA_API_KEY")
API_BASE_URL = "https://mydatapi.aade.gr/myDATA/RequestDocs"
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json")

if not USER_ID or not API_KEY:
    print("Error: MYDATA_USER_ID and MYDATA_API_KEY environment variables must be set", file=sys.stderr)
    print("Please create a .env file with your credentials (see .env.example)", file=sys.stderr)
    sys.exit(1)

if not GOOGLE_SPREADSHEET_ID:
    print("Error: GOOGLE_SPREADSHEET_ID environment variable must be set", file=sys.stderr)
    print("Please create a .env file with your credentials (see .env.example)", file=sys.stderr)
    sys.exit(1)


def convert_date_to_api_format(date_str: str) -> str:
    """
    Convert date from YYYY-MM-DD to DD/MM/YYYY format for API.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Date in DD/MM/YYYY format
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%d/%m/%Y")


def fetch_invoices(
    date_from: str,
    date_to: str,
    receiver_vat_number: Optional[str] = None,
    next_partition_key: Optional[str] = None,
    next_row_key: Optional[str] = None
) -> str:
    """
    Fetch invoices from myDATA API.

    Args:
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        receiver_vat_number: VAT number of the receiver (optional, if not provided fetches all)
        next_partition_key: Pagination key for next partition
        next_row_key: Pagination key for next row

    Returns:
        XML response as string
    """
    # Convert dates to DD/MM/YYYY format for API
    api_date_from = convert_date_to_api_format(date_from)
    api_date_to = convert_date_to_api_format(date_to)

    params = {
        "mark": "1",
        "dateFrom": api_date_from,
        "dateTo": api_date_to
    }

    # Only add receiverVatNumber if provided
    if receiver_vat_number:
        params["receiverVatNumber"] = receiver_vat_number

    if next_partition_key:
        params["nextPartitionKey"] = next_partition_key
    if next_row_key:
        params["nextRowKey"] = next_row_key

    headers = {
        "aade-user-id": USER_ID,
        "Ocp-Apim-Subscription-Key": API_KEY
    }

    try:
        response = requests.get(API_BASE_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for VAT {receiver_vat_number}: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response text: {e.response.text}", file=sys.stderr)
        return ""


def parse_invoices(xml_content: str) -> Tuple[List[Dict], Optional[str], Optional[str]]:
    """
    Parse XML response and extract invoice data.

    Args:
        xml_content: XML response as string

    Returns:
        Tuple of (list of invoice records, next_partition_key, next_row_key)
    """
    if not xml_content:
        return [], None, None

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        return [], None, None

    # Define namespace
    ns = {'ns': 'http://www.aade.gr/myDATA/invoice/v1.0'}

    # Extract pagination tokens
    next_partition_key = None
    next_row_key = None

    continuation_token = root.find("ns:continuationToken", ns)
    if continuation_token is not None:
        npk = continuation_token.find("ns:nextPartitionKey", ns)
        nrk = continuation_token.find("ns:nextRowKey", ns)
        if npk is not None:
            next_partition_key = npk.text
        if nrk is not None:
            next_row_key = nrk.text

    # Extract invoice data
    records = []
    # Find invoicesDoc container first
    invoices_doc = root.find("ns:invoicesDoc", ns)
    if invoices_doc is None:
        return records, next_partition_key, next_row_key

    invoices = invoices_doc.findall("ns:invoice", ns)

    for invoice in invoices:
        # Get issuer information
        issuer = invoice.find("ns:issuer", ns)
        if issuer is None:
            continue

        issuer_vat_elem = issuer.find("ns:vatNumber", ns)
        issuer_name_elem = issuer.find("ns:name", ns)

        issuer_vat = issuer_vat_elem.text.strip() if issuer_vat_elem is not None and issuer_vat_elem.text else ""
        issuer_name = issuer_name_elem.text.strip() if issuer_name_elem is not None and issuer_name_elem.text else ""

        # Get counterpart (receiver) information
        counterpart = invoice.find("ns:counterpart", ns)
        receiver_vat = ""
        if counterpart is not None:
            receiver_vat_elem = counterpart.find("ns:vatNumber", ns)
            receiver_vat = receiver_vat_elem.text.strip() if receiver_vat_elem is not None and receiver_vat_elem.text else ""

        # Get invoice header
        invoice_header = invoice.find("ns:invoiceHeader", ns)
        if invoice_header is None:
            continue

        issue_date_elem = invoice_header.find("ns:issueDate", ns)
        series_elem = invoice_header.find("ns:series", ns)
        aa_elem = invoice_header.find("ns:aa", ns)

        issue_date = issue_date_elem.text.strip() if issue_date_elem is not None and issue_date_elem.text else ""
        series = series_elem.text.strip() if series_elem is not None and series_elem.text else ""
        aa = aa_elem.text.strip() if aa_elem is not None and aa_elem.text else ""

        # Get payment methods
        payment_methods_list = []
        total_amount = 0.0

        payment_methods = invoice.find("ns:paymentMethods", ns)
        if payment_methods is not None:
            for payment_detail in payment_methods.findall("ns:paymentMethodDetails", ns):
                # Get payment type
                payment_type_elem = payment_detail.find("ns:type", ns)
                if payment_type_elem is not None and payment_type_elem.text:
                    payment_methods_list.append(payment_type_elem.text.strip())

                # Get payment amount
                amount_elem = payment_detail.find("ns:amount", ns)
                if amount_elem is not None and amount_elem.text:
                    try:
                        total_amount += float(amount_elem.text)
                    except ValueError:
                        pass

        # Create payment methods comma-separated string
        payment_methods_str = ", ".join(payment_methods_list) if payment_methods_list else ""

        # Only add records with valid issue date
        if issue_date:
            records.append({
                "issue_date": issue_date,
                "vat": issuer_vat,
                "name": issuer_name,
                "series": series,
                "aa": aa,
                "payment_methods": payment_methods_str,
                "total_amount": total_amount,
                "receiver_vat": receiver_vat
            })

    return records, next_partition_key, next_row_key


def fetch_all_invoices(date_from: str, date_to: str, vat_numbers: List[str]) -> List[Dict]:
    """
    Fetch all invoices for a date range and filter by VAT numbers locally.

    Args:
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        vat_numbers: List of VAT numbers to filter by

    Returns:
        List of filtered invoice records
    """
    # Convert VAT numbers list to a set for faster lookup and strip whitespace
    vat_set = {vat.strip() for vat in vat_numbers if vat.strip()}

    print(f"Fetching all invoices for date range (single API call)")
    print(f"Will filter results for {len(vat_set)} VAT number(s)")

    all_records = []
    next_partition_key = None
    next_row_key = None
    page = 1

    # Fetch all invoices without VAT filter
    while True:
        xml_content = fetch_invoices(
            date_from, date_to,
            receiver_vat_number=None,  # No VAT filter in API call
            next_partition_key=next_partition_key,
            next_row_key=next_row_key
        )

        if not xml_content:
            break

        records, next_partition_key, next_row_key = parse_invoices(xml_content)
        all_records.extend(records)

        print(f"  Page {page}: Fetched {len(records)} invoice(s)")
        page += 1

        # If no pagination tokens, we're done
        if not next_partition_key or not next_row_key:
            break

    print(f"\nTotal invoices fetched: {len(all_records)}")

    # Filter records by issuer VAT numbers
    filtered_records = [
        record for record in all_records
        if record.get("vat", "").strip() in vat_set
    ]

    print(f"Filtered to {len(filtered_records)} invoice(s) matching the VAT numbers")

    return filtered_records


def read_vat_numbers(filename: str) -> List[str]:
    """
    Read VAT numbers from file.
    Lines starting with # are treated as comments and ignored.

    Args:
        filename: Path to file containing VAT numbers

    Returns:
        List of VAT numbers
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            vat_numbers = []
            for line in f:
                # Remove comments (anything after #)
                line = line.split('#')[0].strip()
                # Skip empty lines
                if not line:
                    continue
                vat_numbers.append(line)
            return vat_numbers
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


def get_google_sheets_service():
    """
    Create and return Google Sheets API service.

    Returns:
        Google Sheets API service object
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except FileNotFoundError:
        print(f"Error: Google credentials file '{GOOGLE_CREDENTIALS_FILE}' not found", file=sys.stderr)
        print("Please create a service account in Google Cloud Console and download the JSON file", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error creating Google Sheets service: {e}", file=sys.stderr)
        sys.exit(1)


def append_to_google_sheets(service, records: List[Dict], sheet_name: str = "Sheet1"):
    """
    Append invoice records to Google Sheets.
    Only appends records if the combination of columns 4 & 5 (series + aa) doesn't already exist.

    Args:
        service: Google Sheets API service
        records: List of invoice records
        sheet_name: Name of the sheet to append to
    """
    if not records:
        print("No records to append")
        return

    try:
        # Read existing data from the sheet to check for duplicates
        existing_data = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SPREADSHEET_ID,
            range=f"{sheet_name}!A:G"
        ).execute()

        existing_rows = existing_data.get('values', [])

        # Create a set of composite keys (series + aa) from existing data
        # Columns 4 & 5 are indices 3 & 4 in the array (0-indexed)
        existing_keys = set()
        for row in existing_rows:
            if len(row) >= 5:  # Ensure row has at least 5 columns
                series = row[3] if len(row) > 3 else ""
                aa = row[4] if len(row) > 4 else ""
                composite_key = f"{series}|{aa}"
                existing_keys.add(composite_key)

        print(f"Found {len(existing_keys)} existing record(s) in spreadsheet")

        # Filter out records that already exist
        new_rows = []
        skipped_count = 0
        for record in records:
            series = str(record["series"]) if record["series"] else ""
            aa = str(record["aa"]) if record["aa"] else ""
            composite_key = f"{series}|{aa}"

            if composite_key not in existing_keys:
                new_rows.append([
                    record["issue_date"],
                    record["vat"],
                    record["name"],
                    record["series"],
                    record["aa"],
                    record["payment_methods"],
                    record["total_amount"]
                ])
            else:
                skipped_count += 1

        if skipped_count > 0:
            print(f"Skipped {skipped_count} duplicate record(s)")

        if not new_rows:
            print("No new records to append (all records already exist)")
            return

        # Append only new data to sheet
        body = {
            'values': new_rows
        }
        result = service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SPREADSHEET_ID,
            range=f"{sheet_name}!A:G",
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()

        updates = result.get('updates', {})
        updated_rows = updates.get('updatedRows', 0)
        print(f"\nSuccessfully appended {updated_rows} new row(s) to Google Sheets")

    except HttpError as e:
        print(f"Error accessing Google Sheets: {e}", file=sys.stderr)
        sys.exit(1)


def validate_date(date_str: str) -> bool:
    """Validate date format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch expense invoice data from myDATA API and append to Google Sheets"
    )
    parser.add_argument(
        "--from-date",
        help="Start date in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--from-date-offset",
        type=int,
        help="Number of days to add/subtract from the start date (can be negative)"
    )
    parser.add_argument(
        "--to-date",
        help="End date in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--to-date-offset",
        type=int,
        help="Number of days to add/subtract from the end date (can be negative)"
    )
    parser.add_argument(
        "--vat-file",
        default="vat_numbers.txt",
        help="File containing VAT numbers (default: vat_numbers.txt)"
    )
    parser.add_argument(
        "--sheet-name",
        default="Sheet1",
        help="Name of the Google Sheet to append to (default: Sheet1)"
    )

    args = parser.parse_args()

    # Set default dates to today if not provided
    today = datetime.now().strftime("%Y-%m-%d")
    date_from = args.from_date if args.from_date else today
    date_to = args.to_date if args.to_date else today

    # Apply offset to from_date if provided
    if args.from_date_offset is not None:
        from_date_obj = datetime.strptime(date_from, "%Y-%m-%d")
        from_date_obj = from_date_obj + timedelta(days=args.from_date_offset)
        date_from = from_date_obj.strftime("%Y-%m-%d")

    # Apply offset to to_date if provided
    if args.to_date_offset is not None:
        to_date_obj = datetime.strptime(date_to, "%Y-%m-%d")
        to_date_obj = to_date_obj + timedelta(days=args.to_date_offset)
        date_to = to_date_obj.strftime("%Y-%m-%d")

    # Validate dates
    if not validate_date(date_from):
        print(f"Error: Invalid start date '{date_from}'. Use YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)

    if not validate_date(date_to):
        print(f"Error: Invalid end date '{date_to}'. Use YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)

    # Read VAT numbers
    vat_numbers = read_vat_numbers(args.vat_file)
    if not vat_numbers:
        print("Error: No VAT numbers found in file", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(vat_numbers)} VAT number(s) to process")
    print(f"Date range: {date_from} to {date_to}\n")

    # Fetch all invoices
    records = fetch_all_invoices(date_from, date_to, vat_numbers)

    if not records:
        print("\nNo invoice data found")
        sys.exit(0)

    print(f"\nTotal invoices fetched: {len(records)}")

    # Get Google Sheets service
    sheets_service = get_google_sheets_service()

    # Append to Google Sheets
    append_to_google_sheets(sheets_service, records, args.sheet_name)

    print("\nDone!")


if __name__ == "__main__":
    main()
