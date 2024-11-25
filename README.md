# lowes-crawler

This project is designed to scrape product details for Fall Wreaths listed on Lowes' website and perform data analysis on the results.

The crawler is implemented using the Scrapy framework, with configurable parameters for flexibility.

## Features

1. **Data Collection**

    - Scrape all links to Fall Wreaths on Lowes.com.
    - Extract detailed product information for each wreath:
     - **Item Id**
     - **URL**
     - **Model Number**
     - **Brand**
     - **Price**
     - **Is Price Hidden In Cart**
     - **Store Number**
     - **ZIP Code**
2. **Data Analysis**

- Count the number of wreaths by brand.
- Identify the overall price range of wreaths.
- Break down the price range of wreaths by brand.
- Calculate the average price of wreaths for each brand.
- Highlight the top 5 most expensive wreaths.
- Generate a histogram to visualize the distribution of product prices.

3. **Configuration**

    - Configurable parameters via a `config.json` file to adapt to different store numbers, ZIP codes, and starting URLs.

- **Store Number:** Used to specify the Lowe's store ID for localized products and prices.
- **ZIP Code:** Determines the location for shipping or delivery purposes.
- **Start URLs:** A list of URLs for the spider to begin crawling.

## Installation

Install dependencies: `pip3 install -r requirements.txt`

## Usage

Before running the crawler, configure the `config.json` file to suit your requirements

### Running the crawler

1. The spider is located in the `lowes_crawler` folder. Navigate to the folder: `cd lowes_crawler`

2. To start the spider, use:  `scrapy crawl lowes`

3. The results will be stored in the `data/lowes` folder

## Analysis

1. Start Jupyter Notebook in the project root directory: `jupyter notebook`

2. In the Jupyter interface, navigate to the `20241121_fall_wreath_analysis_lowes.ipynb` file and click to open the notebook.

3. Run the notebook to view the analysis results.

## Note on Production Readiness

The current implementation of the crawler is designed for demonstration and local use, but is not fully production-ready. Below are some limitations to address before deploying the crawler in a production environment:

1. **Proxy Usage and Anti-Bot Protection**
    Lowes uses Akamai Anti-Bot protection to detect and block automated scraping activities. While the crawler works for small-scale scraping, attempting to scrape at a large scale without additional precautions may result in being blocked.

    To mitigate this, implementing proxy support with rotating proxies is recommended for large-scale or continuous scraping to make the crawler less susceptible to IP bans and anti-bot blocking.

2. **Hidden Prices**
 Some products may have prices hidden behind an "Add to Cart" requirement. The spider does not currently handle this scenario, meaning such prices will not be captured and will be noted in the output with the property `price_hidden_in_cart`. Add to cart functionality would be necessary to fetch these prices.

## Note on Location-Based Pricing

Lowes' product prices and availability can vary based on location. This is why the crawler is designed with configurable `store_number` and `zip_code` parameters in the `config.json` file. These settings allow the crawler to adapt and ensure accurate data for the desired location.

**Future Improvement:**
Currently, the crawler handles only one ZIP code and store number at a time. In the future, the crawler could be enhanced to support multiple ZIP codes and store numbers, enabling it to scrape and compare data across multiple locations in a single run. This would provide a more comprehensive view of regional pricing and product availability.
