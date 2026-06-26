"""
YC Founders Email Scraper — Entry Point

Usage:
    # Scrape 20 companies from 4 most recent batches (default)
    python run_scraper.py

    # Target a specific batch (recent examples):
    #   W26  = Winter 2026   (198 companies)
    #   SP26 = Spring 2026   (197 companies)
    #   SU26 = Summer 2026   (38 companies, newest)
    #   W25  = Winter 2025   (167 companies)
    #   SP25 = Spring 2025   (143 companies)
    #   S25  = Summer 2025   (166 companies)
    #   F25  = Fall 2025     (149 companies)
    python run_scraper.py --batch W26

    # Scrape all companies in a batch
    python run_scraper.py --batch W26 --all

    # Custom limit
    python run_scraper.py --batch SP26 --max 50
"""

import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


def main():
    parser = argparse.ArgumentParser(
        description="Scrape YC founders and predict their email addresses"
    )
    parser.add_argument(
        "--batch",
        type=str,
        default=None,
        help=(
            "YC batch short code: W26, SP26, SU26, F26, W25, SP25, S25, F25, W24, S24. "
            "Default: scrapes 4 most recent batches (W26+SP26+S25+F25)"
        ),
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20,
        help="Maximum number of companies to scrape. Default: 20",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape ALL companies (overrides --max). This will take a long time!",
    )
    args = parser.parse_args()

    max_companies = 0 if args.all else args.max
    batch = args.batch

    # Print banner
    print("=" * 60)
    print("  YC Founders Email Scraper")
    print("=" * 60)
    print(f"  Batch filter : {batch or 'Recent batches (W26, SP26, S25, F25)'}")
    print(f"  Max companies: {'Unlimited' if max_companies == 0 else max_companies}")
    print(f"  Output       : output/yc_founders_emails.csv")
    print("=" * 60)
    print()

    # Get Scrapy settings
    os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "yc_scraper.settings")
    settings = get_project_settings()

    # Create output directory
    output_dir = settings.get("OUTPUT_DIR")
    os.makedirs(output_dir, exist_ok=True)

    # Start the crawler
    process = CrawlerProcess(settings)
    process.crawl(
        "yc_founders",
        max_companies=max_companies,
        batch=batch,
    )
    process.start()

    # Print summary
    csv_path = os.path.join(output_dir, "yc_founders_emails.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f) - 1  # Subtract header
        print()
        print("=" * 60)
        print(f"  [DONE] {line_count} founders exported to:")
        print(f"  -> {os.path.abspath(csv_path)}")
        print("=" * 60)
    else:
        print()
        print("  [WARNING] No output file generated. Check the logs above.")


if __name__ == "__main__":
    main()
