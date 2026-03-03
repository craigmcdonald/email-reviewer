#!/usr/bin/env python3
"""Fetch tracked emails from HubSpot CRM v3 Search API with server-side date filtering."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS")
BASE_URL = "https://api.hubapi.com"

# HubSpot rate limit: 100 requests per 10 seconds for private apps
REQUEST_DELAY = 0.15
MAX_RETRIES = 5
PAGE_SIZE = 100  # v3 search max is 100

PROPERTIES = [
    "hs_timestamp",
    "hs_email_subject",
    "hs_email_text",
    "hs_email_html",
    "hs_email_from_email",
    "hs_email_from_firstname",
    "hs_email_from_lastname",
    "hs_email_to_email",
    "hs_email_to_firstname",
    "hs_email_to_lastname",
    "hs_email_cc_email",
    "hs_email_bcc_email",
    "hs_email_direction",
    "hs_email_status",
    "hs_email_tracker_key",
    "hubspot_owner_id",
    "hs_createdate",
]


def build_search_body(start_date=None, after=None):
    """Build the search request body with optional date filter."""
    body = {
        "limit": PAGE_SIZE,
        "properties": PROPERTIES,
        "sorts": [
            {"propertyName": "hs_createdate", "direction": "ASCENDING"}
        ],
    }

    if start_date:
        start_ms = str(int(start_date.timestamp() * 1000))
        body["filterGroups"] = [
            {
                "filters": [
                    {
                        "propertyName": "hs_createdate",
                        "operator": "GTE",
                        "value": start_ms,
                    }
                ]
            }
        ]

    if after:
        body["after"] = after

    return body


def fetch_emails(max_count=None, start_date=None):
    """Fetch tracked emails via v3 CRM search with server-side date filtering."""
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    all_emails = []
    after = None
    request_count = 0

    target = max_count or "all"
    print(f"Fetching {target} tracked emails...")
    if start_date:
        print(f"  From: {start_date.strftime('%Y-%m-%d')}")

    while True:
        if max_count and len(all_emails) >= max_count:
            break

        body = build_search_body(start_date=start_date, after=after)
        retries = 0

        while retries < MAX_RETRIES:
            resp = requests.post(
                f"{BASE_URL}/crm/v3/objects/emails/search",
                headers=headers,
                json=body,
            )
            request_count += 1

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                print(f"  Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                retries += 1
                continue
            elif resp.status_code != 200:
                print(f"  Error {resp.status_code}: {resp.text}")
                retries += 1
                time.sleep(2 ** retries)
                continue

            break
        else:
            print("Max retries hit. Saving what we have.")
            break

        data = resp.json()

        for result in data.get("results", []):
            props = result.get("properties", {})
            all_emails.append({
                "id": result["id"],
                "created_at": props.get("hs_createdate", ""),
                "timestamp": props.get("hs_timestamp", ""),
                "subject": props.get("hs_email_subject", ""),
                "from_email": props.get("hs_email_from_email", ""),
                "from_name": f"{props.get('hs_email_from_firstname', '')} {props.get('hs_email_from_lastname', '')}".strip(),
                "to_email": props.get("hs_email_to_email", ""),
                "to_name": f"{props.get('hs_email_to_firstname', '')} {props.get('hs_email_to_lastname', '')}".strip(),
                "cc": props.get("hs_email_cc_email", ""),
                "bcc": props.get("hs_email_bcc_email", ""),
                "direction": props.get("hs_email_direction", ""),
                "status": props.get("hs_email_status", ""),
                "body_text": props.get("hs_email_text", ""),
                "body_html": props.get("hs_email_html", ""),
                "owner_id": props.get("hubspot_owner_id", ""),
            })

            if max_count and len(all_emails) >= max_count:
                break

        total = data.get("total", "?")
        print(f"  Page {request_count} | Fetched: {len(all_emails)} | Total available: {total}")

        # v3 search pagination uses cursor-based "after"
        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")

        if not after:
            break

        time.sleep(REQUEST_DELAY)

    return all_emails


def main():
    parser = argparse.ArgumentParser(description="Fetch tracked emails from HubSpot")
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=None,
        help="Max number of emails to fetch (default: all)",
    )
    parser.add_argument(
        "-s", "--start-date",
        type=str,
        default=None,
        help="Only fetch emails from this date onwards (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="emails.json",
        help="Output file (default: emails.json)",
    )
    args = parser.parse_args()

    if not ACCESS_TOKEN:
        print("Error: HUBSPOT_ACCESS not set in .env")
        return

    start_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")

    emails = fetch_emails(max_count=args.count, start_date=start_date)

    Path(args.output).write_text(json.dumps(emails, indent=2, ensure_ascii=False))
    print(f"\nDone. {len(emails)} emails saved to {args.output}")


if __name__ == "__main__":
    main()