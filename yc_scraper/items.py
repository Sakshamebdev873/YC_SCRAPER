"""
Data models for scraped YC founder information.
"""

import scrapy


class FounderItem(scrapy.Item):
    """Represents a single YC company founder with predicted email."""
    company_name = scrapy.Field()
    batch = scrapy.Field()
    company_website = scrapy.Field()
    company_description = scrapy.Field()
    founder_name = scrapy.Field()
    founder_title = scrapy.Field()
    founder_linkedin = scrapy.Field()
    founder_twitter = scrapy.Field()
    predicted_email = scrapy.Field()
    email_pattern = scrapy.Field()
    yc_url = scrapy.Field()
