#!/usr/bin/env python3
"""
Fetch invoice data from myDATA API and analyze line items.
Generates a CSV with item descriptions, total quantities, and average values.
"""
import argparse
import csv
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Constants - load from environment variables
USER_ID = os.getenv("MYDATA_USER_ID")
API_KEY = os.getenv("MYDATA_API_KEY")
API_BASE_URL = "https://mydatapi.aade.gr/myDATA/RequestDocs"

if not USER_ID or not API_KEY:
    print("Error: MYDATA_USER_ID and MYDATA_API_KEY environment variables must be set", file=sys.stderr)
    print("Please create a .env file with your credentials (see .env.example)", file=sys.stderr)
    sys.exit(1)


def convert_date_to_api_format(date_str: str) -> str:
    """Convert date from YYYY-MM-DD to DD/MM/YYYY format for API."""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%d/%m/%Y")


def fetch_invoices(
    date_from: str,
    date_to: str,
    next_partition_key: Optional[str] = None,
    next_row_key: Optional[str] = None
) -> str:
    """
    Fetch invoices from myDATA API.

    Args:
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        next_partition_key: Pagination key for next partition
        next_row_key: Pagination key for next row

    Returns:
        XML response as string
    """
    api_date_from = convert_date_to_api_format(date_from)
    api_date_to = convert_date_to_api_format(date_to)

    params = {
        "mark": "1",
        "dateFrom": api_date_from,
        "dateTo": api_date_to
    }

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
        print(f"Error fetching data: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response text: {e.response.text}", file=sys.stderr)
        return ""


def parse_invoice_items(xml_content: str) -> Tuple[List[Dict], Set[Tuple[str, str]], Optional[str], Optional[str]]:
    """
    Parse XML response and extract invoice line items.

    Args:
        xml_content: XML response as string

    Returns:
        Tuple of (list of item records, set of (vat, name) for issuers without items,
                  next_partition_key, next_row_key)
    """
    if not xml_content:
        return [], set(), None, None

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        return [], set(), None, None

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

    items = []
    issuers_without_items: Set[Tuple[str, str]] = set()

    invoices_doc = root.find("ns:invoicesDoc", ns)
    if invoices_doc is None:
        return items, issuers_without_items, next_partition_key, next_row_key

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

        # Get invoice details (line items)
        invoice_details_list = invoice.findall("ns:invoiceDetails", ns)

        if not invoice_details_list:
            # No invoice details at all
            if issuer_vat or issuer_name:
                issuers_without_items.add((issuer_vat, issuer_name))
            continue

        has_item_with_description = False

        for invoice_details in invoice_details_list:
            item_descr_elem = invoice_details.find("ns:itemDescr", ns)
            quantity_elem = invoice_details.find("ns:quantity", ns)
            net_value_elem = invoice_details.find("ns:netValue", ns)

            item_descr = item_descr_elem.text.strip() if item_descr_elem is not None and item_descr_elem.text else ""

            if not item_descr:
                # This invoiceDetails block has no item description
                continue

            has_item_with_description = True

            # Parse quantity (default to 1 if not present or invalid)
            quantity = 1.0
            if quantity_elem is not None and quantity_elem.text:
                try:
                    quantity = float(quantity_elem.text)
                except ValueError:
                    quantity = 1.0

            # Parse net value (default to 0 if not present or invalid)
            net_value = 0.0
            if net_value_elem is not None and net_value_elem.text:
                try:
                    net_value = float(net_value_elem.text)
                except ValueError:
                    net_value = 0.0

            items.append({
                "item_descr": item_descr,
                "quantity": quantity,
                "net_value": net_value
            })

        if not has_item_with_description and (issuer_vat or issuer_name):
            issuers_without_items.add((issuer_vat, issuer_name))

    return items, issuers_without_items, next_partition_key, next_row_key


def fetch_all_items(date_from: str, date_to: str) -> Tuple[List[Dict], Set[Tuple[str, str]]]:
    """
    Fetch all invoice items for a date range.

    Args:
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format

    Returns:
        Tuple of (list of item records, set of (vat, name) for issuers without items)
    """
    print(f"Fetching all invoices for date range: {date_from} to {date_to}")

    all_items = []
    all_issuers_without_items: Set[Tuple[str, str]] = set()
    next_partition_key = None
    next_row_key = None
    page = 1

    while True:
        xml_content = fetch_invoices(
            date_from, date_to,
            next_partition_key=next_partition_key,
            next_row_key=next_row_key
        )

        if not xml_content:
            break

        items, issuers_without_items, next_partition_key, next_row_key = parse_invoice_items(xml_content)
        all_items.extend(items)
        all_issuers_without_items.update(issuers_without_items)

        print(f"  Page {page}: Found {len(items)} item(s)")
        page += 1

        if not next_partition_key or not next_row_key:
            break

    print(f"\nTotal line items fetched: {len(all_items)}")
    print(f"Issuers without item descriptions: {len(all_issuers_without_items)}")

    return all_items, all_issuers_without_items


def aggregate_items(items: List[Dict]) -> List[Dict]:
    """
    Aggregate items by description, calculating total quantity and average net value.

    Args:
        items: List of item records

    Returns:
        List of aggregated records with item_descr, total_quantity, avg_net_value
    """
    # Group by item description
    aggregated: Dict[str, Dict] = defaultdict(lambda: {"total_quantity": 0.0, "net_values": []})

    for item in items:
        descr = item["item_descr"]
        aggregated[descr]["total_quantity"] += item["quantity"]
        aggregated[descr]["net_values"].append(item["net_value"])

    # Calculate averages and build result
    result = []
    for descr, data in sorted(aggregated.items()):
        avg_value = sum(data["net_values"]) / len(data["net_values"]) if data["net_values"] else 0.0
        result.append({
            "item_descr": descr,
            "total_quantity": data["total_quantity"],
            "avg_net_value": round(avg_value, 2)
        })

    return result


def write_items_csv(aggregated_items: List[Dict], output_file: str):
    """Write aggregated items to CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Item Description", "Total Quantity", "Average Net Value"])
        for item in aggregated_items:
            writer.writerow([item["item_descr"], item["total_quantity"], item["avg_net_value"]])

    print(f"Wrote {len(aggregated_items)} item(s) to {output_file}")


def write_issuers_without_items(issuers: Set[Tuple[str, str]], output_file: str):
    """Write issuers without item descriptions to file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        for vat, name in sorted(issuers):
            f.write(f"{vat}\t{name}\n")

    print(f"Wrote {len(issuers)} issuer(s) to {output_file}")


def validate_date(date_str: str) -> bool:
    """Validate date format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch invoice data from myDATA API and analyze line items"
    )
    parser.add_argument(
        "--from-date",
        help="Start date in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--to-date",
        help="End date in YYYY-MM-DD format (default: today)"
    )
    parser.add_argument(
        "--output",
        default="items.csv",
        help="Output CSV file for items (default: items.csv)"
    )
    parser.add_argument(
        "--issuers-output",
        default="issuers_without_items.txt",
        help="Output file for issuers without item descriptions (default: issuers_without_items.txt)"
    )

    args = parser.parse_args()

    # Set default dates to today if not provided
    today = datetime.now().strftime("%Y-%m-%d")
    date_from = args.from_date if args.from_date else today
    date_to = args.to_date if args.to_date else today

    # Validate dates
    if not validate_date(date_from):
        print(f"Error: Invalid start date '{date_from}'. Use YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)

    if not validate_date(date_to):
        print(f"Error: Invalid end date '{date_to}'. Use YYYY-MM-DD format.", file=sys.stderr)
        sys.exit(1)

    # Fetch all items
    items, issuers_without_items = fetch_all_items(date_from, date_to)

    if not items and not issuers_without_items:
        print("\nNo invoice data found")
        sys.exit(0)

    # Aggregate items by description
    if items:
        aggregated = aggregate_items(items)
        write_items_csv(aggregated, args.output)

    # Write issuers without item descriptions
    if issuers_without_items:
        write_issuers_without_items(issuers_without_items, args.issuers_output)

    print("\nDone!")


if __name__ == "__main__":
    main()
