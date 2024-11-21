from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from datetime import datetime
from scrapy.spidermiddlewares.httperror import HttpError
import scrapy
import json
import math
import uuid
import time
import re
import os

from ..items import LowesProductItem

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
        - store_number (str): Store number of a Lowe's location.
        - zip_code (str): Zipcode of location for shipping or delivery purposes
        """

        super().__init__(*args, **kwargs)

        # Load the config file
        with open("config.json", "r") as file:
            config = json.load(file)

        # Set start_urls from config
        self.start_urls = config.get("start_urls")
        if not self.start_urls:
            self.logger.warning("No start URLs found in config.json. Exiting.")
            raise ValueError("start_urls is required.")

        # Log loaded start_urls
        self.logger.info(f"Loaded start_urls: {self.start_urls}")

        # Store Number and Zipcode for a Lowe's Location
        self.store_number = config.get("store_number")
        if not self.store_number.isdigit() or len(self.store_number) != 4:
            self.logger.warning("Invalid store number format. Using default.")
            self.store_number = "0416"

        self.zip_code = config.get("zip_code")
        if not self.zip_code.isdigit() or len(self.zip_code) != 5:
            self.logger.warning("Invalid zip code format. Using default.")
            self.zip_code = "28278"

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
            yield scrapy.Request(url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number}, errback=self.handle_404_error)

    def handle_404_error(self, failure):
        """
        Handles 404 errors

        Parameters:
        - failure (scrapy.Failure): Contains the details of the error.
        """
        if failure.check(HttpError):
            response = failure.value.response
            if response.status == 404:
                self.logger.warning(f"404 Not Found: {response.url}")

                self.logger.warning(f"Store number or zipcode may be invalid. Please try with different values.")
                self.store_failed_url(response.url, response.status)
            else:
                self.logger.error(f"HTTP Error {response.status} for {response.url}")
        else:
            self.logger.error(f"Request failed: {failure}")

    def build_product_url(self, item_id):
        """
        Builds the product URL using the item ID, store number, and zip code.
        """

        if item_id:
            return f"https://www.lowes.com/wpd/{item_id}/productdetail/{self.store_number}/Guest/{self.zip_code}"
        else:
            self.logger.error("Cannot build URL without item ID.")
            return None

    def has_query_params(self, url):
        """
        Checks if a given URL contains query parameters.

        Parameters:
        url (str): URL to be checked.

        Returns:
        bool:
            - True if the URL contains query parameters.
            - False if no query parameters are present.
        """
        parsed_url = urlparse(url)
        return bool(parsed_url.query)

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

        if not scripts:
            self.logger.warning("No scripts found in response. Storing HTML for debugging.")
            self.store_failed_html(response)
            return

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

                    if "itemList" not in preloaded_state:
                        self.logger.error("itemList not found in preloaded state.")
                        self.store_failed_html(response)
                        return

                    item_list = preloaded_state.get("itemList", [])

                    for item in item_list:
                        item_id = item["product"]["omniItemId"]
                        item_url = self.build_product_url(item_id)

                        if item_url:
                            yield scrapy.Request(item_url, cookies={"dbidv2": self.dbidv2, "sn": self.store_number}, callback=self.parse_product_data, meta={"item_id": item_id})
                except json.JSONDecodeError:
                    self.logger.error("Error decoding JSON data.")
                    self.store_failed_html(response)
                    return
                break

        if not preloaded_state_json:
            self.logger.error("Preloaded state data not found in response. Storing HTML for debugging.")
            self.store_failed_html(response)
            return

         # Extract URL of next page
        next_page_url = response.css('link[rel="next"]::attr(href)').get()

        # Calculate next page url if current url has parameters
        # There are cases where the next page url
        # doesn't include the query parameters of the starter url
        # which causes a redirect to a different page
        if not self.has_query_params(response.url) and next_page_url:
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
            else:
                self.logger.warning("No 'next' page URL found. This may be the last page.")
                return

    def parse_product_data(self, response):
        """
        Parse the product details API response and extract product information.

        Extracts the url, model number, brand, price, and if there is a price restriction that prevents the price from being in the response data (e.g., "View Lower Price in Cart").

        Parameters:
        response (scrapy.http.Response): Response object for the product page.

        Yields:
        LowesProductItem: A `LowesProductItem` containing the extracted product information such as item_id, url, model_number, brand, price, price_hidden_in_cart, store_number, zip_code, and date.

        Raises:
        Exception: If there is an error parsing the product details, the product data is stored in a json file in the failed_parses folder.
        """

        item_id = response.meta.get("item_id") # Retrieve item_id set in request metadata

        data = response.json()

        item = LowesProductItem()
        item["item_id"] = item_id
        item["store_number"] = self.store_number
        item["zip_code"] = self.zip_code
        item["date"] = self.get_current_datetime_iso8601()

        try:
            product_details = data["productDetails"][item_id]
            product = product_details["product"]
        except KeyError as e:
            self.logger.error(f"KeyError: Missing expected product details for item {item_id}. Error: {e}")
            self.store_failed_product_data(item_id, data)
            return

        try:
            product_url = product.get("pdURL", None)
            if (product_url):
                item["url"] = response.urljoin(product_url)
            else:
                item["url"] = None

            item["model_number"] = product.get("modelId", None)

            # Not all products have a brand
            item["brand"] = product.get("brand", None)

            # Extract pricing information
            if isinstance(product_details.get("mfePrice"), dict): # There were a few cases were mfePrice was False
                price_data = product_details.get("mfePrice", {}).get("price", {})

                if price_data:
                    map_price_msg = price_data.get("mapPriceMessage")

                    if map_price_msg is not None and map_price_msg == "View Lower Price In Cart":
                        # TODO: add item to cart to get price
                        item["price_hidden_in_cart"] = True
                        item["price"] = None
                    else:
                        item["price_hidden_in_cart"] = False
                        item["price"] = price_data["additionalData"]["sellingPrice"]
                else:
                    self.logger.warning(f"No price data for item {item_id}. Setting price to None.")
                    item["price"] = None
            else:
                    self.logger.warning(f"No price data for item {item_id}. Setting price to None.")
                    item["price"] = None

            yield item
        except Exception as e:
            self.logger.error(f"An error occurred extracting product data for item {item_id}... {e}")
            self.store_failed_product_data(item_id, data)

    def store_failed_url(self, url, status_code):
        """
        Stores the details of a failed request (URL and status code) in a file for later review.

        This method logs the failed URL and its corresponding HTTP status code to a file to keep track of failed requests.
        The file is stored in the 'failed_requests' folder.

        Parameters:
        - url (str): The URL of the failed request.
        - status_code (int): The HTTP status code returned for the failed request (e.g., 404, 500).

        Returns:
        - None: This method does not return anything, it only stores the failed URL and status code in a file.

        Notes:
        - The file is appended with each new failed URL. If the file doesn't exist, it will be created.
        """

        folder_path = "failed_requests"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        timestamp = int(time.time())
        file_path = os.path.join(folder_path, f"failed_urls_{timestamp}.txt")

        with open(file_path, "w") as file:
            file.write(f"{status_code} - {url}\n")

        self.logger.info(f"Stored failed URL in {file_path}")

    def store_failed_html(self, response):
        """
        Stores the HTML content of a page when parsing preloaded state JSON fails, for debugging purposes.

        This method is used to store the raw HTML of a failed page in the 'failed_html' folder when
        the spider encounters an error while attempting to parse preloaded state JSON.

        Parameters:
        - response (scrapy.http.Response): Response object containing the URL and HTML content
        of the failed page.

        Returns:
        - None: This method does not return anything. It stores the HTML content in a file.
        """

        MAX_FILENAME_LENGTH = 75

        sanitized_url = quote(response.url, safe="")
        sanitized_url = sanitized_url[:MAX_FILENAME_LENGTH]

        folder_path = "failed_html"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        file_name = f"{sanitized_url}_{int(time.time())}.html"
        file_path = os.path.join(folder_path, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(response.text)

    def store_failed_product_data(self, item_id, data):
        """
        Stores product data when parsing fails, for later analysis and debugging.

        It saves the raw product data (JSON) to a file in the 'failed_parses' folder, with the file named using
        the product's item ID and a timestamp.

        Parameters:
        - item_id (str): The unique identifier for the product.
        - data (dict): The raw product data (in JSON format) retrieved from the response before parsing
        failed.

        Returns:
        - None: This method does not return anything. It stores the product data in a file.
        """

        folder_path = "failed_parses"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        file_name = f"item_{item_id}_{int(time.time())}.json"
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