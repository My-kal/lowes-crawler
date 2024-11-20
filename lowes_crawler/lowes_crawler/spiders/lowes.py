from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime
import scrapy
import json
import math
import uuid
import time
import re
import os

class LowesSpider(scrapy.Spider):
    """
    Scrapy spider to scrape product details from Lowe's website.

    This spider extracts product information (such as url, model number, brand, and price)
    for items from Lowe's product listings. It handles pagination and retries for
    pages that may have been blocked with a 403 response.
    """

    name = "lowes"
    allowed_domains = ["lowes.com"]

    products_per_page = 24

    def __init__(self, *args, **kwargs):
        """
        Initialize the spider with configuration values loaded from config.json.

        Parameters:
        - start_urls (list): List of URLs to start scraping from.
        - store_number (str): Store number for Lowe's location.
        - zip_code (str): Zipcode of user's residence for shipping or delivery purposes
        """

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

        self.logger.info(f"Store Number: {self.store_number} | Zipcode: {self.zip_code}")

        # Generate UUID to use as dbidv2 cookie in requests to avoid 403s and load correct # of results
        self.dbidv2 = str(uuid.uuid4())

    def start_requests(self):
        """
        Send requests to start_urls with required cookies.

        Yields:
        scrapy.Request: Request object for each URL in self.start_urls with cookies for bypassing 403 errors.

        Notes:
        - The method uses the store number and dbidv2 as cookies to avoid 403 errors when requesting pages.
        """

        for url in self.start_urls:
            yield scrapy.Request(url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number})

    def parse(self, response):
        """
        Parse the page for product links and extract next page URL from the preloaded state JSON from a <script> tag in the page.

        Parameters:
        - response (scrapy.http.Response): Response object for the current page.

        Yields:
        scrapy.Request: Request for each product page found in the preloaded state data.
        scrapy.Request: Request for the next page if available, or a calculated next page URL.

        Notes:
        - If the next page link is available, a request for the next page is yielded.
        - If no next page link is found, the method calculates the next page URL based on the current page's offset.
        """

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
                    self.logger.error("Error decoding JSON data.")
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
        """
        Parse the product details API response and extract product information.

        Extracts the url, model number, brand, price, and if there is a price restriction that prevents the price from being in the response data (e.g., "View Lower Price in Cart").

        Parameters:
        response (scrapy.http.Response): Response object for the product page.

        Yields:
        dict: A dictionary containing product details such as item_id, url, model_number, brand, price, price_hidden_in_cart, and date.

        Raises:
        Exception: If there is an error parsing the product details, the product data is stored in a json file in the failed_parses folder.
        """

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
            self.logger.error(f"An error occurred parsing data for item {item_id}... {e}")

            # Store product data on parsing failures for reference during debugging

            folder_path = "failed_parses"
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)  # Create folder if it doesn't exist

            file_name = f"item_{item_id}_{time.time()}.json"
            file_path = os.path.join(folder_path, file_name)

            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)

    @staticmethod
    def get_current_datetime_iso8601():
        """
        Returns the current UTC date and time in ISO 8601 format.

        Returns:
        str: The current date and time in ISO 8601 format, e.g., "2024-11-20T15:45:30.000Z".
        """
        return datetime.utcnow().isoformat() + "Z"