import scrapy


class LowesSpider(scrapy.Spider):
    name = "lowes"
    allowed_domains = ["lowes.com"]
    start_urls = ["https://lowes.com"]

    def parse(self, response):
        pass
