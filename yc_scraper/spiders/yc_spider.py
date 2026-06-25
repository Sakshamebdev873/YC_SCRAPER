"""
YC Founders Spider — Scrapes Y Combinator company directory using Algolia API
and individual company pages to extract founder information.
"""

import json
import scrapy

from yc_scraper.items import FounderItem

# Map short codes (W25, S25) → Algolia full batch names
BATCH_NAME_MAP = {
    # 2026
    "F26": "Fall 2026",
    "SU26": "Summer 2026",
    "SP26": "Spring 2026",
    "W26": "Winter 2026",
    # 2025
    "F25": "Fall 2025",
    "S25": "Summer 2025",
    "SP25": "Spring 2025",
    "W25": "Winter 2025",
    # 2024
    "F24": "Fall 2024",
    "S24": "Summer 2024",
    "W24": "Winter 2024",
}

# Default: 4 most recent batches by company count
DEFAULT_BATCHES = [
    "Winter 2026",
    "Spring 2026",
    "Summer 2025",
    "Fall 2025",
]


class YCSpider(scrapy.Spider):
    name = "yc_founders"

    start_urls = ["https://www.ycombinator.com/companies"]

    HITS_PER_PAGE = 100

    def __init__(self, max_companies=0, batch=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_companies = int(max_companies)
        # Accept short code (W25) or full name (Winter 2025)
        if batch:
            self.batch_filter = BATCH_NAME_MAP.get(batch.upper(), batch)
        else:
            self.batch_filter = None
        self.companies_scraped = 0

    def parse(self, response):
        self.logger.info("Starting Algolia API scrape...")

        app_id = self.settings.get("ALGOLIA_APP_ID")
        api_key = self.settings.get("ALGOLIA_API_KEY_B64")
        index_name = self.settings.get("ALGOLIA_INDEX")

        self.algolia_url = (
            f"https://{app_id}-dsn.algolia.net/1/indexes/{index_name}/query"
        )
        self.algolia_headers = {
            "x-algolia-application-id": app_id,
            "x-algolia-api-key": api_key,
            "Content-Type": "application/json",
            "Referer": "https://www.ycombinator.com/",
            "Origin": "https://www.ycombinator.com",
        }

        if self.batch_filter:
            batches_to_scrape = [self.batch_filter]
            self.logger.info(f"Filtering to batch: {self.batch_filter}")
        else:
            batches_to_scrape = DEFAULT_BATCHES
            self.logger.info(f"Using default recent batches: {DEFAULT_BATCHES}")

        for batch_name in batches_to_scrape:
            yield self._build_algolia_request(page=0, batch_name=batch_name)

    def _build_algolia_request(self, page=0, batch_name=None):
        """Build an Algolia search request using JSON body (not params string)."""
        body = {
            "hitsPerPage": self.HITS_PER_PAGE,
            "page": page,
        }

        if batch_name:
            body["facetFilters"] = [[f"batch:{batch_name}"]]

        return scrapy.Request(
            url=self.algolia_url,
            method="POST",
            headers=self.algolia_headers,
            body=json.dumps(body),
            callback=self.parse_algolia,
            meta={"page": page, "batch_name": batch_name},
            dont_filter=True,
        )

    def parse_algolia(self, response):
        data = json.loads(response.text)
        hits = data.get("hits", [])
        total_pages = data.get("nbPages", 0)
        current_page = data.get("page", 0)
        batch_name = response.meta.get("batch_name", "")

        self.logger.info(
            f"[{batch_name}] Algolia page {current_page + 1}/{total_pages} "
            f"— {len(hits)} companies"
        )

        for hit in hits:
            if self.max_companies > 0 and self.companies_scraped >= self.max_companies:
                self.logger.info(
                    f"Reached max_companies limit ({self.max_companies}). Stopping."
                )
                return

            company_name = hit.get("name", "")
            slug = hit.get("slug", "")
            batch = hit.get("batch", batch_name)
            website = hit.get("website", "") or hit.get("url", "")
            one_liner = hit.get("one_liner", "")

            if slug:
                yc_url = f"https://www.ycombinator.com/companies/{slug}"
                self.companies_scraped += 1

                yield scrapy.Request(
                    url=yc_url,
                    callback=self.parse_company_page,
                    meta={
                        "company_name": company_name,
                        "batch": batch,
                        "website": website,
                        "one_liner": one_liner,
                        "yc_url": yc_url,
                    },
                    priority=1,
                )

        # Paginate
        next_page = current_page + 1
        if next_page < total_pages:
            if self.max_companies == 0 or self.companies_scraped < self.max_companies:
                yield self._build_algolia_request(
                    page=next_page, batch_name=batch_name
                )

    def parse_company_page(self, response):
        meta = response.meta
        company_name = meta["company_name"]
        batch = meta["batch"]
        website = meta["website"]
        one_liner = meta["one_liner"]
        yc_url = meta["yc_url"]

        founders = []

        # YC site uses Inertia.js — data is in div[data-page]
        data_page = response.css("div[data-page]::attr(data-page)").get()
        if data_page:
            try:
                page_data = json.loads(data_page)
                props = page_data.get("props", {})
                company = props.get("company", {})

                if not website and company:
                    website = company.get("website", "") or company.get("url", "")

                for f in company.get("founders", []) if company else []:
                    name = f.get("full_name", "") or f.get("name", "")
                    if name:
                        founders.append(
                            {
                                "name": name,
                                "title": f.get("title", "") or "Founder",
                                "linkedin": f.get("linkedin_url", ""),
                                "twitter": f.get("twitter_url", ""),
                            }
                        )
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.warning(
                    f"Could not parse page data for {company_name}: {e}"
                )

        if not founders:
            self.logger.warning(f"No founders found for {company_name}")
            item = FounderItem()
            item["company_name"] = company_name
            item["batch"] = batch
            item["company_website"] = website
            item["company_description"] = one_liner
            item["founder_name"] = "Unknown"
            item["founder_title"] = "Founder"
            item["founder_linkedin"] = ""
            item["founder_twitter"] = ""
            item["predicted_email"] = ""
            item["email_pattern"] = ""
            item["yc_url"] = yc_url
            yield item
            return

        for founder in founders:
            item = FounderItem()
            item["company_name"] = company_name
            item["batch"] = batch
            item["company_website"] = website
            item["company_description"] = one_liner
            item["founder_name"] = founder["name"]
            item["founder_title"] = founder.get("title", "Founder")
            item["founder_linkedin"] = founder.get("linkedin", "")
            item["founder_twitter"] = founder.get("twitter", "")
            item["predicted_email"] = ""
            item["email_pattern"] = ""
            item["yc_url"] = yc_url
            yield item
