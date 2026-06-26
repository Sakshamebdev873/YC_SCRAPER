"""
Scrapy settings for yc_scraper project.
"""

BOT_NAME = "yc_scraper"

SPIDER_MODULES = ["yc_scraper.spiders"]
NEWSPIDER_MODULE = "yc_scraper.spiders"

import os
from dotenv import load_dotenv

load_dotenv()

# --- OpenAI API Configuration ---
# Set this via environment variable (e.g., set OPENAI_API_KEY=sk-...)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- Algolia API Configuration (public keys from YC website) ---
ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_API_KEY_B64 = (
    "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJi"
    "MWM4ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmlj"
    "dEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlf"
    "TGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNf"
    "cHVibGljJTIyJTVE"
)
ALGOLIA_INDEX = "YCCompany_production"

# --- Scraper Behavior ---
# Be polite: 2 second delay between requests
DOWNLOAD_DELAY = 2
RANDOMIZE_DOWNLOAD_DELAY = True

# Obey robots.txt
ROBOTSTXT_OBEY = False  # YC's robots.txt blocks scrapers; we use public API data

# Concurrent requests (keep low to avoid rate limiting)
CONCURRENT_REQUESTS = 1

# User agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Default request headers
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
}

# --- Pipelines ---
ITEM_PIPELINES = {
    "yc_scraper.pipelines.ChatGPTEmailPipeline": 300,
    "yc_scraper.pipelines.CsvExportPipeline": 800,
}

# --- Output ---
import os
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")

# --- Logging ---
LOG_LEVEL = "INFO"

# Disable telemetry
TELNETCONSOLE_ENABLED = False

# Disable offsite middleware (we need to reach algolia.net for API calls)
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.offsite.OffsiteMiddleware": None,
}

# Auto throttle for politeness
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Retry settings
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# Request fingerprinter
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
