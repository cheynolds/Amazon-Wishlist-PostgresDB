# Amazon Wishlist Scraper

This project is a Python-based web scraper that collects data from Amazon wishlists. The scraper extracts information such as product names, prices, availability, ratings, and more. It can handle multiple wishlist URLs and uses Selenium to scroll through the pages.

## Features

- Scrape product details such as name, price, stock status, and more.
- Supports multiple wishlist URLs.
- Automatically scrolls to the end of each wishlist.
- CAPTCHA handling in place in case of issues.
- Stores scraped data in a PostgreSQL database.

## Setup and Installation

### Prerequisites

- Python 3.x
- `pip` (Python package manager)
- PostgreSQL (if using a database to store scraped data)
- BrowserDriver (e.g., Chrome WebDriver)

### Installation

1. Clone the repository:

    ```bash
    git clone https://your-repo-url.git
    cd your-repo-directory
    ```

2. Set up a Python virtual environment (recommended):

    ```bash
    python3 -m venv venv
    source venv/bin/activate   # On Windows: venv\Scripts\activate
    ```

3. Install the required packages:

    ```bash
    pip install -r requirements.txt
    ```

4. Set up environment variables:
   - Create a `.env` file in the project root directory and add your database credentials:
   
     **File**: `.env`
     ```bash
     DB_USER=your_postgres_username
     DB_PASSWORD=your_postgres_password
     DB_HOST=localhost
     DB_PORT=5432
     DB_NAME=your_postgres_db
     ```

5. Set up your wishlist URLs:
   - The scraper reads wishlist URLs from a `wishlist_url.txt` file.
   - Copy the sample file provided (`wishlist_url_sample.txt`) and rename it to `wishlist_url.txt`:
     
     ```bash
     cp wishlist_url_sample.txt wishlist_url.txt
     ```

   - Replace the sample URLs with actual Amazon wishlist URLs.

### Running the Scraper

1. To run the scraper, use the following command:

    ```bash
    python scraper.py
    ```

   The scraper will automatically navigate through the wishlists provided in `wishlist_url.txt`, extract the product information, and store it in your desired format (CSV or database).

### Example Output

The scraper outputs the collected data to a CSV file (`output.csv`) or can store it in a PostgreSQL database if configured.

## Configuration

The scraper can be configured to store the scraped data in a PostgreSQL database. To do this, make sure you have PostgreSQL installed and the correct credentials in your `.env` file. 

## Sample Files

- **`.env.example`**: Provides the structure for your environment variables. Copy this file and rename it to `.env` to configure your credentials.
- **`wishlist_url_sample.txt`**: A sample file with placeholder URLs. Rename this file to `wishlist_url.txt` and update it with actual wishlist URLs.

## Contributing

Feel free to submit pull requests for new features, improvements, or bug fixes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
