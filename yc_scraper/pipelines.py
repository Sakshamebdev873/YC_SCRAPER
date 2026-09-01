"""
Pipelines for YC Scraper:
  1. GeminiEmailPipeline — Uses Google Gemini to predict founder emails.
  2. CsvExportPipeline — Exports all items to a CSV file.
"""

import csv
import os
import time
import logging
from urllib.parse import urlparse

from openai import OpenAI

logger = logging.getLogger(__name__)


class GeminiEmailPipeline:
    """Uses Google Gemini to predict the most likely email for each founder."""

    def __init__(self, api_key, model=None, base_url=None):
        self.api_key = api_key
        self.model = model or "gemini-flash-latest"
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        self.client = None
        self.request_count = 0
        self.last_request_time = 0
        # Rate limit: be polite with API calls
        self.min_delay = 1.0  # seconds between Gemini requests

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            api_key=crawler.settings.get("GEMINI_API_KEY"),
            model=crawler.settings.get("GEMINI_MODEL"),
            base_url=crawler.settings.get("GEMINI_BASE_URL"),
        )

    def open_spider(self):
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info("Gemini client initialized (model=%s)", self.model)

    def close_spider(self):
        logger.info(f"Gemini pipeline processed {self.request_count} requests")

    def _extract_domain(self, website_url):
        """Extract clean domain from a URL."""
        if not website_url:
            return ""
        # Add scheme if missing
        if not website_url.startswith(("http://", "https://")):
            website_url = "https://" + website_url
        try:
            parsed = urlparse(website_url)
            domain = parsed.netloc or parsed.path
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return website_url

    def _rate_limit(self):
        """Enforce rate limiting for the Gemini API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def process_item(self, item):
        """Predict email for each founder using Gemini."""
        founder_name = item.get("founder_name", "")
        company_name = item.get("company_name", "")
        website = item.get("company_website", "")
        domain = self._extract_domain(website)

        # Skip if no useful data
        if not founder_name or founder_name == "Unknown" or not domain:
            if domain and founder_name and founder_name != "Unknown":
                item["predicted_email"] = self._basic_email_guess(founder_name, domain)
                item["email_pattern"] = "firstname@domain (basic guess)"
            return item

        # Rate limit
        self._rate_limit()

        try:
            prompt = self._build_prompt(founder_name, company_name, domain)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an email pattern expert. Given a founder's name "
                            "and their company domain, predict the most likely professional "
                            "email address. Respond with ONLY two lines:\n"
                            "Line 1: The predicted email address\n"
                            "Line 2: The pattern used (e.g., 'firstname@domain')\n"
                            "Do not include any other text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=100,
            )

            # Parse the Gemini response
            result = response.choices[0].message.content.strip()
            self._parse_response(item, result, founder_name, domain)
            self.request_count += 1

            if self.request_count % 10 == 0:
                logger.info(f"Gemini: Processed {self.request_count} email predictions")

        except Exception as e:
            logger.warning(f"Gemini API error for {founder_name} at {company_name}: {e}")
            # Fallback to basic guess
            item["predicted_email"] = self._basic_email_guess(founder_name, domain)
            item["email_pattern"] = "firstname@domain (fallback)"

        return item

    def _build_prompt(self, founder_name, company_name, domain):
        """Build the Gemini prompt for email prediction."""
        return (
            f"Founder Name: {founder_name}\n"
            f"Company Name: {company_name}\n"
            f"Company Domain: {domain}\n\n"
            f"Common email patterns for startups:\n"
            f"1. firstname@domain (most common for startups)\n"
            f"2. first.last@domain\n"
            f"3. firstlast@domain\n"
            f"4. first@domain\n"
            f"5. flast@domain (first initial + last name)\n\n"
            f"Rules:\n"
            f"- Use lowercase only\n"
            f"- Remove any special characters or accents from names\n"
            f"- For the domain, use exactly: {domain}\n"
            f"- Pick the SINGLE most likely pattern"
        )

    def _parse_response(self, item, response_text, founder_name, domain):
        """Parse the model's response to extract email and pattern."""
        lines = [l.strip() for l in response_text.strip().split("\n") if l.strip()]

        if len(lines) >= 2:
            item["predicted_email"] = lines[0].lower()
            item["email_pattern"] = lines[1]
        elif len(lines) == 1:
            item["predicted_email"] = lines[0].lower()
            item["email_pattern"] = "chatgpt prediction"
        else:
            # Fallback
            item["predicted_email"] = self._basic_email_guess(founder_name, domain)
            item["email_pattern"] = "firstname@domain (fallback)"

    def _basic_email_guess(self, name, domain):
        """Generate a basic email guess without using the API."""
        if not name or not domain:
            return ""
        # Use first name @ domain as the most common startup pattern
        first_name = name.split()[0].lower()
        # Remove non-alpha characters
        first_name = "".join(c for c in first_name if c.isalpha())
        return f"{first_name}@{domain}"


class CsvExportPipeline:
    """Exports all scraped items to a CSV file."""

    CSV_COLUMNS = [
        "company_name",
        "batch",
        "company_website",
        "founder_name",
        "founder_title",
        "founder_linkedin",
        "founder_twitter",
        "predicted_email",
        "email_pattern",
        "yc_url",
        "company_description",
    ]

    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.file = None
        self.writer = None
        self.items_count = 0

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            output_dir=crawler.settings.get("OUTPUT_DIR"),
        )

    def open_spider(self):
        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.join(self.output_dir, "yc_founders_emails.csv")
        file_exists = os.path.isfile(filepath) and os.path.getsize(filepath) > 0
        self.file = open(filepath, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=self.CSV_COLUMNS, extrasaction="ignore")
        if not file_exists:
            self.writer.writeheader()
        logger.info(f"CSV output file (append mode): {filepath}")

    def close_spider(self):
        if self.file:
            self.file.close()
            logger.info(f"CSV export complete: {self.items_count} rows written")

    def process_item(self, item):
        """Write item to CSV."""
        row = {col: item.get(col, "") for col in self.CSV_COLUMNS}
        self.writer.writerow(row)
        self.items_count += 1

        if self.items_count % 50 == 0:
            logger.info(f"CSV: Written {self.items_count} rows")
            self.file.flush()

        return item
