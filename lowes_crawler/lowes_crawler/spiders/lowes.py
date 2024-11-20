from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime
import scrapy
import json
import math
import uuid
import time
import re

class LowesSpider(scrapy.Spider):
    name = "lowes"
    allowed_domains = ["lowes.com"]

    products_per_page = 24

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the config file
        with open("config.json", "r") as file:
            config = json.load(file)

        # Set start_urls from config
        self.start_urls = config.get("start_urls", [])

        # Log loaded start_urls
        self.logger.info(f"Loaded start_urls: {self.start_urls}")

        # Store Number and Zipcode for a Lowe's Location
        self.store_number = config.get("store_number", "0416")
        self.zip_code = config.get("zip_code", "28278")

        self.logger.info(f"Store Number: {store_number} | Zipcode: {zip_code}")

        # Generate UUID to use as dbidv2 cookie in requests to avoid 403s and load correct # of results
        self.dbidv2 = str(uuid.uuid4())
    def start_requests(self):
        """Include dbidv2 and sn cookies to bypass 403 response."""

        for url in self.start_urls:
            yield scrapy.Request(url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number})

    def parse(self, response):
        """Extract urls of products on results page."""

        # Extract all script tags
        scripts = response.css("script::text").getall()

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

                    item_list = preloaded_state.get("itemList", [])

                    for item in item_list:
                        item_id = item["product"]["omniItemId"]

                        item_url = f"https://www.lowes.com/wpd/{item_id}/productdetail/{self.store_number}/Guest/{self.zip_code}"

                        yield scrapy.Request(item_url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number}, callback=self.parse_product_data, meta={"item_id": item_id})
                except json.JSONDecodeError:
                    self.log("Error decoding JSON data.")
                break

         # Extract URL of next page
        next_page_url = response.css('link[rel="next"]::attr(href)').get()

        if next_page_url:
            yield scrapy.Request(next_page_url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number}, callback=self.parse)
        else:
            """If next page url is unable to be extracted from HTML, build the url by calculating the next offset based on # of results"""

            # Extract number of results
            results_text = response.css("p.results::text").get()
            total_products = int("".join(filter(str.isdigit, results_text)))

            # Calculate how many pages of products exist
            total_pages = math.ceil(total_products / self.products_per_page)

            # Extract current offset from URL
            parsed_url = urlparse(response.url)
            query_params = parse_qs(parsed_url.query, keep_blank_values=True)
            current_offset = int(query_params.get("offset", [0])[0]) or 0

            # Determine if there are more pages
            if current_offset + self.products_per_page < total_products:
                next_offset = current_offset + self.products_per_page

                # Update query parameters with new offset
                query_params.update({ "offset": next_offset })

                # Rebuild URL with updated offset
                next_page_url = parsed_url._replace(query=urlencode(query_params, doseq=True)).geturl()

                yield scrapy.Request(next_page_url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number}, callback=self.parse)

    def parse_product_data(self, response):
        """Extract product details from API response."""

        item_id = response.meta.get("item_id") # Retrieve item_id set in request metadata

        data = response.json()

        try:
            product_details = data["productDetails"][item_id]
            product = product_details["product"]

            product_url = product["pdURL"]
            model_number = product["modelId"]

            # Not all products have a brand
            brand = product.get("brand", None)

            # Extract pricing information
            price_data = product_details["mfePrice"]["price"]

            map_price_msg = price_data.get("mapPriceMessage")

            if map_price_msg is not None and map_price_msg == "View Lower Price In Cart":
                # TODO: add item to cart to get price
                price_hidden_in_cart = True
                price = None
            else:
                price_hidden_in_cart = False
                price = price_data["additionalData"]["sellingPrice"]

            yield {
                "item_id": item_id,
                "url": response.urljoin(product_url),
                "model_number": model_number,
                "brand": brand,
                "price_hidden_in_cart": price_hidden_in_cart,
                "price": price,
                "date": self.get_current_datetime_iso8601(),
            }
        except Exception as e:
            self.log(f"An error occurred parsing data for item {item_id}... {e}")

            with open(f"item_{item_id}_{time.time()}.json", "w") as f:
                json.dump(data, f, indent=4)

    @staticmethod
    def get_current_datetime_iso8601():
        """Returns the current UTC date and time in ISO 8601 format."""
        return datetime.utcnow().isoformat() + "Z"