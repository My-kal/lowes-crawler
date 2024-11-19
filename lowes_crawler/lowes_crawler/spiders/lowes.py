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
                        # yield scrapy.Request(product_url, callback=self.parse_product_data, meta={'store_id': store_id})

                except json.JSONDecodeError:
                    self.log("Error decoding JSON data.")
                break

         # Extract URL of next page
        next_page_url = response.css('link[rel="next"]::attr(href)').get()

        self.log(f"Next Page: {next_page_url}")

        if next_page_url:
            yield scrapy.Request(next_page_url, callback=self.parse)

    def parse_product_page(self, response):
        # Extract details from product API response

        product_data = response.data()

        # yield {
        #     'product_url': response.url
        #     'product_model_number': product_name,
        #     'product_brand': product_name,
        #     'product_price': product_price,
        # }
