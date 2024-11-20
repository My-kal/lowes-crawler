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
                        item_url = response.urljoin(item["product"]["pdURL"])

                        yield scrapy.Request(item_url, callback=self.parse_product_page, meta={'item_id': item_id})
                        break

                except json.JSONDecodeError:
                    self.log("Error decoding JSON data.")
                break

         # Extract URL of next page
        next_page_url = response.css('link[rel="next"]::attr(href)').get()

        if next_page_url:
            yield scrapy.Request(next_page_url, callback=self.parse)

    def parse_product_page(self, response):
        """ Extract product details from HTML on product page."""

        item_id = response.meta.get("item_id") # Retrieve item_id set in request metadata

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

                    product_details = preloaded_state["productDetails"][item_id]

                    model_number = product_details["product"]["modelId"]
                    brand = product_details["product"]["brand"]

                    # Extract pricing information
                    price_data = product_details["mfePrice"]["price"]

                    map_price_msg = price_data["mapPriceMessage"]

                    if map_price_msg and map_price_msg == "View Lower Price In Cart":
                        # TODO: add item to cart to get price
                        price_hidden_in_cart = True
                        price = None
                    else:
                        price_hidden_in_cart = False
                        price = price_data["additionalData"]["sellingPrice"]

                    yield {
                        "item_id": item_id,
                        "url": response.url,
                        "model_number": model_number,
                        "brand": brand,
                        "price_hidden_in_cart": price_hidden_in_cart,
                        "price": price,
                        "date": self.get_current_datetime_iso8601(),
                    }

                except json.JSONDecodeError:
                    self.log("Error decoding JSON data.")

                break


    @staticmethod
    def get_current_datetime_iso8601():
        """Returns the current UTC date and time in ISO 8601 format."""
        return datetime.utcnow().isoformat() + 'Z'