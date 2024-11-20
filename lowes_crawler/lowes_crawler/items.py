# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

class LowesProductItem(scrapy.Item):
    """
    Defines the structure for the product data that will be scraped from Lowe's.
    """

    # Fields for the product data
    item_id = scrapy.Field()  # Unique identifier for the product
    url = scrapy.Field()  # URL of the product page
    model_number = scrapy.Field()  # Product model number
    brand = scrapy.Field()  # Product brand (optional - not all products have a brand)
    price = scrapy.Field()  # Product price
    price_hidden_in_cart = scrapy.Field()  # Whether the price is hidden until added to the cart
    date = scrapy.Field()  # Date and time when the product data was scraped

    def __repr__(self):
        """Define a custom string representation for the item."""
        return f"<LowesProductItem(item_id={self['item_id']}, model_number={self['model_number']}, brand={self['brand']}, price={self['price']})>"

