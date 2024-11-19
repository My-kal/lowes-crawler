from datetime import datetime
import scrapy
import json
import re

class LowesSpider(scrapy.Spider):
    name = "lowes"
    allowed_domains = ["lowes.com"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the config file
        with open("config.json", "r") as file:
            config = json.load(file)

        # Set start_urls from config
        self.start_urls = config.get("start_urls", [])

        # Log loaded start_urls
        self.logger.info(f"Loaded start_urls: {self.start_urls}")

    def parse(self, response):
        # Extract all script tags
        scripts = response.css('script::text').getall()

        # Search for script containing window['__PRELOADED_STATE__'] and extract JSON
        for script in scripts:
            match = re.search(r"window\['__PRELOADED_STATE__'\]\s*=\s*({.*})", script, re.DOTALL)
            if match:
                # Extract JSON from regex match
                preloaded_state_json = match.group(1)

                try:
                    # Parse JSON into dictionary
                    preloaded_state = json.loads(preloaded_state_json)
                    self.logger.info("Successfully extracted and parsed __PRELOADED_STATE__ data.")

                    item_list = preloaded_state.get('itemList', [])

                    for item in item_list:
                        item_id = item["product"]["omniItemId"]
                        item_url = f'https://www.lowes.com/wpd/{item_id}/productdetail/2442/Guest/29730'
                        yield scrapy.Request(item_url, callback=self.parse_product_data, meta={'item_id': item_id})
                        break

                except json.JSONDecodeError:
                    self.log("Error decoding JSON data.")
                break

         # Extract URL of next page
        next_page_url = response.css('link[rel="next"]::attr(href)').get()

        self.log(f"Next Page: {next_page_url}")

        if next_page_url:
            yield scrapy.Request(next_page_url, callback=self.parse)

    def parse_product_data(self, response):
        # Extract details from product API response
        product_data = json.loads(response.text)

        item_id = response.meta.get("item_id") # Retrieve item_id set in request metadata

        product_details = product_data["productDetails"][item_id]
        product = product_details["product"]

        yield {
            "item_id": item_id,
            "url": response.urljoin(product["pdURL"]),
            "model_number": product["modelId"],
            "brand": product["brand"],
            "price": product_details["mfePrice"]["price"]["additionalData"]["retailPrice"],
            "date": self.get_current_datetime_iso8601()
        }

    @staticmethod
    def get_current_datetime_iso8601():
        """Returns the current UTC date and time in ISO 8601 format."""
        return datetime.utcnow().isoformat() + 'Z'