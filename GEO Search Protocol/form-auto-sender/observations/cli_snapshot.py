#!/usr/bin/env python3
"""
CLI: generate a preview snapshot for one company (zero send).

Usage:
  python3 -m observations.cli_snapshot --url https://example.com --company "Example Inc" --industry 美容クリニック --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BASE))

from observations.snapshot_builder import create_preview_snapshot, public_snapshot_view


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate preview snapshot (no send)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--industry", default="")
    ap.add_argument("--area", default="")
    ap.add_argument("--campaign", default="ari_preview_v1")
    ap.add_argument("--dry-run", action="store_true", help="Build snapshot only — never persist")
    ap.add_argument(
        "--persist",
        action="store_true",
        help="Write snapshot to persistent store (requires store credentials)",
    )
    ap.add_argument("--has-llms-txt", choices=("true", "false"), default=None)
    ap.add_argument("--crawler-json", help="Path to crawler row JSON (skip CSV lookup)")
    args = ap.parse_args()

    company = {
        "website_url": args.url,
        "company_name": args.company,
        "industry_name": args.industry,
        "area_name": args.area,
    }

    crawler_data = None
    if args.crawler_json:
        crawler_data = json.loads(Path(args.crawler_json).read_text(encoding="utf-8"))

    llms = None
    if args.has_llms_txt == "true":
        llms = True
    elif args.has_llms_txt == "false":
        llms = False

    if args.persist and args.dry_run:
        print("ERROR: --persist and --dry-run are mutually exclusive", file=sys.stderr)
        return 1

    dry_run = args.dry_run or not args.persist
    try:
        snap = create_preview_snapshot(
            company,
            crawler_data=crawler_data,
            campaign_id=args.campaign,
            has_llms_txt=llms,
            dry_run=dry_run,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out = {
        "preview_url": snap["preview_url"],
        "token": snap["token"],
        "public": public_snapshot_view(snap),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
