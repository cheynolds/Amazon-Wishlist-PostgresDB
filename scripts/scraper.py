import argparse
import traceback
from selenium import webdriver
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import time
from datetime import datetime
import re
import os
import psycopg2
import pickle

load_dotenv()  # This loads environment variables from the .env file
# PostgreSQL connection setup
db_config = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

# Argument parser setup for quiet mode
parser = argparse.ArgumentParser(description='Amazon Wishlist Scraper.')
parser.add_argument('-q', '--quiet', action='store_true', help='Run script in quiet mode')
args = parser.parse_args()
quiet = args.quiet

def scroll_to_end(driver):
    """Scroll to the end of the page to load all wishlist items."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Wait for new items to load
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def get_wishlist_url(file_path):
    """Reads the wishlist URL from a text file, skipping lines that start with #."""
    try:
        with open(file_path, 'r') as file:
            urls = [line.strip() for line in file.readlines() if line.strip() and not line.strip().startswith('#')]
            if not urls:
                raise ValueError("The wishlist URL file is empty or contains only commented lines.")
            return urls
    except FileNotFoundError:
        qprint(f"Error: '{file_path}' not found. Please create a text file containing the wishlist URLs.", quiet, level='error')
        exit(1)
    except Exception as e:
        qprint(f"Error reading wishlist URL file: {e}", quiet, level='error')
        exit(1)

def mark_url_as_scraped(file_path, scraped_url):
    """Marks the scraped URL in the text file by adding a # in front of it."""
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Rewrite the file with the scraped URL commented
        with open(file_path, 'w') as file:
            for line in lines:
                if line.strip() == scraped_url:
                    file.write(f"#{line.strip()}\n")  # Mark the URL as processed by adding #
                else:
                    file.write(line)

        qprint(f"Marked URL as scraped: {scraped_url}", quiet, level='info')

    except FileNotFoundError:
        qprint(f"Error: '{file_path}' not found. Could not mark URL as scraped.", quiet, level='error')
    except Exception as e:
        qprint(f"Error marking URL as scraped: {e}", quiet, level='error')

def retry_request(driver, url, retries=3, delay=5):
    for attempt in range(retries):
        try:
            driver.get(url)
            return True  # Return success
        except Exception as e:
            print(f"Failed to load URL: {e}, retrying in {delay} seconds...")
            time.sleep(delay)
    return False  # Return failure if retries are exhausted

def qprint(message, quiet, level='info'):
    levels = {
        'info': 1,
        'warning': 2,
        'error': 3
    }
    if not quiet or level == 'error':  # Always print errors
        print(f"[{level.upper()}] {message}")

def save_cookies(driver, filepath):
    """Save cookies to a file."""
    with open(filepath, 'wb') as file:
        pickle.dump(driver.get_cookies(), file)
        
def load_cookies(driver, filepath):
    """Load cookies from a file."""
    with open(filepath, 'rb') as file:
        cookies = pickle.load(file)
        for cookie in cookies:
            driver.add_cookie(cookie)

def connect_to_db():
    """Connect to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        qprint("Connected to PostgreSQL database.", quiet, level='info')
        return conn, cursor
    except Exception as e:
        qprint(f"Failed to connect to PostgreSQL: {e}", quiet, level='error')
        exit(1)

def clean_price(price):
    """Clean up price and convert to float."""
    if not price:  # If the price is None or empty
        return None
    
    try:
        # Remove any non-numeric characters except for dots
        price = re.sub(r'[^\d.]', '', price)
        
        # Ensure there is only one dot (in case multiple are found)
        price = re.sub(r'\.+', '.', price)
        
        # Convert the cleaned string to a float
        price_value = float(price) if price else None
        
        return price_value
    except (ValueError, TypeError):
        # If conversion fails, return None
        return None

def update_product_in_postgresql(cursor, product_data):
    """Update or add product data to PostgreSQL."""
    try:
        asin = product_data['asin']
        if asin is None:
            qprint("Invalid ASIN: skipping product update.", quiet)
            return

        # Ensure price and price_added are never None
        price = product_data['price'] if product_data['price'] is not None else 0.0
        price_added = product_data['price_added'] if product_data['price_added'] is not None else price
        price_drop_percent = float(product_data['price_drop_percent']) if product_data['price_drop_percent'] is not None else 0.0
        stock_status = product_data['stock_status']
        date_added = product_data['date_added']
        title = product_data['title']
        pattern = product_data['pattern']
        style = product_data['style']
        subtitle = product_data['subtitle']
        link = product_data['link']
        affiliate_link = product_data['affiliate_link']
        image_url = product_data['image_url']
        reviews = int(product_data['reviews']) if isinstance(product_data['reviews'], int) else 0
        stars = float(product_data['stars']) if product_data['stars'] is not None else None
        wishlist_name = product_data['wishlist_name']  # Ensure wishlist_name is included
        needs_product = int(product_data['needs_product']) if isinstance(product_data['needs_product'], int) else 0
        has_product = int(product_data['has_product']) if isinstance(product_data['has_product'], int) else 0

        # Ensure 'wishlist_name' is included in the SQL query
        query = """
            WITH old_data AS (
                SELECT asin, title, price, stock_status, date_added, product_link, 
                       affiliate_link, image_url, reviews, stars, pattern, style, 
                       subtitle, price_added, price_drop_percent, needs_product, has_product, wishlist_name
                FROM product_data
                WHERE asin = %(asin)s
            ),
            upsert AS (
                INSERT INTO product_data (
                    asin, title, price, stock_status, date_added, product_link, 
                    affiliate_link, image_url, reviews, stars, pattern, style, 
                    subtitle, price_added, price_drop_percent, needs_product, has_product, wishlist_name
                )
                VALUES (
                    %(asin)s, %(title)s, %(price)s, %(stock_status)s, %(date_added)s, %(product_link)s, 
                    %(affiliate_link)s, %(image_url)s, %(reviews)s, %(stars)s, %(pattern)s, %(style)s, 
                    %(subtitle)s, %(price_added)s, %(price_drop_percent)s, %(needs_product)s, %(has_product)s, %(wishlist_name)s
                )
                ON CONFLICT (asin) DO UPDATE
                SET 
                    title = EXCLUDED.title,
                    price = EXCLUDED.price,
                    stock_status = EXCLUDED.stock_status,
                    date_added = EXCLUDED.date_added,
                    product_link = EXCLUDED.product_link,
                    affiliate_link = EXCLUDED.affiliate_link,
                    image_url = EXCLUDED.image_url,
                    reviews = EXCLUDED.reviews,
                    stars = EXCLUDED.stars,
                    pattern = EXCLUDED.pattern,
                    style = EXCLUDED.style,
                    subtitle = EXCLUDED.subtitle,
                    price_added = EXCLUDED.price_added,
                    price_drop_percent = EXCLUDED.price_drop_percent,
                    needs_product = EXCLUDED.needs_product,
                    has_product = EXCLUDED.has_product,
                    wishlist_name = EXCLUDED.wishlist_name
                RETURNING *
            )
            INSERT INTO product_data_history (
                asin, title, price, stock_status, date_added, product_link, 
                affiliate_link, image_url, reviews, stars, pattern, style, 
                subtitle, price_added, price_drop_percent, needs_product, has_product, wishlist_name, updated_at
            )
            SELECT asin, title, price, stock_status, date_added, product_link, 
                   affiliate_link, image_url, reviews, stars, pattern, style, 
                   subtitle, price_added, price_drop_percent, needs_product, has_product, wishlist_name, NOW()
            FROM old_data;
        """
        
        # Using individual variables to match the SQL placeholders
        values = {
            'asin': asin, 
            'title': title, 
            'price': price, 
            'stock_status': stock_status, 
            'date_added': date_added, 
            'product_link': link, 
            'affiliate_link': affiliate_link, 
            'image_url': image_url, 
            'reviews': reviews, 
            'stars': stars, 
            'pattern': pattern, 
            'style': style, 
            'subtitle': subtitle, 
            'price_added': price_added, 
            'price_drop_percent': price_drop_percent, 
            'needs_product': needs_product, 
            'has_product': has_product,
            'wishlist_name': wishlist_name  # Ensure wishlist_name is passed as a value
        }

        cursor.execute(query, values)
        # Attempt to fetch the returned old data
        try:
            old_data = cursor.fetchone()
            if old_data:
                qprint(f"Product {asin} updated/added in PostgreSQL with old data returned.", quiet)
            else:
                qprint(f"Product {asin} updated/added in PostgreSQL without any old data.", quiet)
        except psycopg2.ProgrammingError:
            # Handle the case where no rows were returned
            qprint(f"Product {asin} updated/added in PostgreSQL but no old data was returned.", quiet)

    except psycopg2.ProgrammingError as pe:
        # Handling a case where no rows are returned
        qprint(f"Failed to update product {asin} in PostgreSQL: {pe.pgcode} - {pe.pgerror}", quiet)

    except Exception as e:
        qprint(f"Failed to update product {asin} in PostgreSQL: {e}", quiet)


############################################################


# Get wishlist URLs
wishlist_urls = get_wishlist_url('wishlist_URL.txt')

for wishlist_url in wishlist_urls:
    qprint(f"Processing wishlist: {wishlist_url}", quiet, level='info')

    
    # Initialize the WebDriver
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)  # This will keep the browser open
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(3)

    # Navigate to Amazon before loading cookies
    driver.get('https://www.amazon.com')
    
    # Load cookies if available
    try:
        load_cookies(driver, 'cookies.pkl')
        qprint("Cookies loaded successfully.", quiet, level='info')
    except FileNotFoundError:
        qprint("No cookies file found. You may need to log in.", quiet, level='warning')
    
    success = retry_request(driver, wishlist_url)
    if not success:
        qprint(f"Failed to load wishlist {wishlist_url} after retries. Skipping.", quiet, level='error')
        continue
        
    # Scroll to the end to load all items
    scroll_to_end(driver)
    time.sleep(15)  # Give time for the page to fully load after scrolling
    
    # Save cookies for future runs
    save_cookies(driver, 'cookies.pkl')
    time.sleep(15)  # Give time for the page to fully load after scrolling
    qprint("Cookies saved successfully.", quiet, level='info')

    # Play a system sound
    os.system("afplay /System/Library/Sounds/Glass.aiff")
    
    input("Press Enter after solving the CAPTCHA and SCROLLING TO LAST ITEM.")

    # Connect to PostgreSQL
    conn, cursor = connect_to_db()

    ######---------------###########
    # Wait until the wishlist name appears
    try:
        wishlist_name = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span#profile-list-name'))
        ).text.strip()
        qprint(f"Wishlist Name: {wishlist_name}", quiet, level='info')
    except Exception as e:
        qprint(f"Error retrieving wishlist name: {e}", quiet, level='error')
        wishlist_name = 'Unknown Wishlist'

    while True:
        try:
            # Loop for extracting ASIN and Title (container for title and ASIN)
            items_asin_title = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'h2.a-size-base'))
            )

            # Loop for extracting Price, Date, etc. (container for price and other details)
            items_details = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.g-item-sortable'))
            )

            if not items_asin_title or not items_details:
                qprint("No items found on this page.", quiet, level='warning')
                break

            # Ensure the two loops handle the same number of products
            if len(items_asin_title) != len(items_details):
                qprint(f"Mismatch in product counts: Titles ({len(items_asin_title)}) and Details ({len(items_details)})", quiet, level='error')
                break

            # Pair the ASIN/Title and Details (matching by index)
            for index, (item_title, item_details) in enumerate(zip(items_asin_title, items_details)):
                try:
                    # ASIN and Title extraction
                    try:
                        link_element = item_title.find_element(By.CSS_SELECTOR, 'a.a-link-normal')
                        title = link_element.get_attribute('title').strip()
                        link = link_element.get_attribute('href')
                        asin = link.split("dp/")[-1].split("/")[0] if "dp/" in link else None
                        qprint(f"Product {index + 1} - Extracted ASIN: {asin}, Title: {title}, Link: {link}", quiet, level='info')
                    except NoSuchElementException:
                        title = ''
                        asin = None
                        link = 'javascript:void(0)'
                        qprint(f"Product {index + 1} - Title and ASIN not found.", quiet, level='error')

                    # Subtitle (author/maker) extraction
                    try:
                        subtitle_element = item_details.find_element(By.CSS_SELECTOR, 'span[id^="item-byline"]')
                        subtitle = subtitle_element.text.strip().replace('by ', '') if subtitle_element else 'No subtitle'
                        qprint(f"Product {index + 1} - Extracted Subtitle: {subtitle}", quiet, level='info')
                    except NoSuchElementException:
                        subtitle = 'No subtitle'
                        qprint(f"Product {index + 1} - Subtitle not found.", quiet, level='warning')


                    # Price extraction logic
                    try:
                        price = item_details.get_attribute('data-price')
    
                        # If price is not available in data-price, try other methods
                        if not price:
                            price_element = item_details.find_element(By.CSS_SELECTOR, 'span.a-price > span.a-offscreen')
                            price = price_element.text.strip().replace('$', '').replace(',', '') if price_element else None

                        if not price:
                            # Try extracting the whole and fractional parts separately
                            price_whole = item_details.find_element(By.CSS_SELECTOR, 'span.a-price-whole').text.strip()
                            price_fraction = item_details.find_element(By.CSS_SELECTOR, 'span.a-price-fraction').text.strip()
                            price = f"{price_whole}.{price_fraction}" if price_whole and price_fraction else None
    
                        # Clean and convert the price
                        price = clean_price(price)
    
                        if price is None:
                            price = 0.0  # Set default price if extraction failed
                        qprint(f"Product {index + 1} - Extracted Price: {price}", quiet, level='info')

                    except NoSuchElementException:
                        price = 0.0  # Default to 0 if no price found
                        qprint(f"Product {index + 1} - Price not found.", quiet, level='warning')
                    
                    
                    
                     # Stock status extraction based on "Prime" or "Free Delivery"
                    try:
                        stock_status_element = item_details.find_element(By.CSS_SELECTOR, 'i.a-icon-prime')
                        stock_status = 'In Stock' if stock_status_element else 'Unknown stock status'
                        qprint(f"Product {index + 1} - Extracted Stock Status: {stock_status}", quiet, level='info')
                    except NoSuchElementException:
                        stock_status = 'Unknown stock status'
                        qprint(f"Product {index + 1} - Stock status not found.", quiet, level='warning')


                    # Reviews count extraction
                    try:
                        reviews_element = item_details.find_element(By.CSS_SELECTOR, 'a[id^="review_count_"]')
                        reviews_text = reviews_element.text.strip()
                        qprint(f"Extracted raw reviews text: {reviews_text}", quiet, level='info')  # Debug print

                        try:
                            reviews = int(reviews_text.replace(',', ''))  # Remove commas and convert to int
                        except ValueError:
                            reviews = 0  # Default to 0 if conversion fails
                        qprint(f"Product {index + 1} - Extracted Reviews: {reviews}", quiet, level='info')
                    except NoSuchElementException:
                        reviews = 0  # Default to 0 if an error occurs
                        qprint(f"Product {index + 1} - Failed to extract reviews.", quiet, level='warning')
                    
                    

                    # Needs extraction
                    try:
                        needs_element = item_details.find_element(By.CSS_SELECTOR, 'span[id^="itemRequested_I"]')
                        needs_text = needs_element.text.strip()
                        try:
                            needs_product = int(needs_text.replace(',', ''))  # Remove commas and convert to int
                        except ValueError:
                            needs_product = 0
                        qprint(f"Product {index + 1} - Extracted Needs: {needs_product}", quiet, level='info')
                    except NoSuchElementException:
                        needs_product = 0
                        qprint(f"Product {index + 1} - Needs not found.", quiet, level='warning')

                    # Has extraction
                    try:
                        has_element = item_details.find_element(By.CSS_SELECTOR, 'span[id^="itemPurchased_I"]')
                        has_text = has_element.text.strip()
                        try:
                            has_product = int(has_text.replace(',', ''))  # Remove commas and convert to int
                        except ValueError:
                            has_product = 0
                        qprint(f"Product {index + 1} - Extracted Has: {has_product}", quiet, level='info')
                    except NoSuchElementException:
                        has_product = 0
                        qprint(f"Product {index + 1} - Has not found.", quiet, level='warning')

                    # PriceAdded and Price Drop extraction
                    try:
                        price_added_element = item_details.find_element(By.CSS_SELECTOR, '.a-row.itemPriceDrop')
                        if price_added_element:
                            price_added_text = price_added_element.text
                            price_added = re.search(r'was \$(\d+\.?\d*)', price_added_text).group(1) if 'was' in price_added_text else None
                            price_added = clean_price(price_added)  # Clean the extracted priceAdded
                            if price_added is None:
                                price_added = price  # If priceAdded is None, use the current price
                            price_drop_percent_match = re.search(r'Price dropped (\d+)%', price_added_text)
                            price_drop_percent = float(price_drop_percent_match.group(1)) / 100 if price_drop_percent_match else 0.0
                            qprint(f"Product {index + 1} - Price Added: {price_added}, Price Drop: {price_drop_percent}", quiet, level='info')
                        else:
                            price_added = price  # Default to the current price if no priceAdded is found
                            price_drop_percent = 0.0  # No price drop
                            qprint(f"Product {index + 1} - PriceAdded not found, using current price.", quiet, level='warning')

                    except NoSuchElementException:
                        price_added = price  # Fallback to current price if priceAdded not found
                        price_drop_percent = 0.0  # No price drop
                        qprint(f"Product {index + 1} - PriceAdded not found, using current price.", quiet, level='warning')
                
                    # Date added extraction
                    try:
                        date_added_element = item_details.find_element(By.CSS_SELECTOR, 'span[id^="itemAddedDate"]')
                        date_added_text = date_added_element.text.strip().replace('Item added ', '')
                        date_added = datetime.strptime(date_added_text, '%B %d, %Y') if date_added_text else None
                        qprint(f"Product {index + 1} - Extracted Date Added: {date_added}", quiet, level='info')
                    except (NoSuchElementException, ValueError):
                        date_added = None
                        qprint(f"Product {index + 1} - Date added not found.", quiet, level='warning')

                    # Image URL extraction
                    try:
                        image_element = item_details.find_element(By.CSS_SELECTOR, 'a.a-link-normal img')
                        image_url = image_element.get_attribute('src') if image_element else None
                        qprint(f"Product {index + 1} - Extracted Image URL: {image_url}", quiet, level='info')
                    except NoSuchElementException:
                        image_url = None
                        qprint(f"Product {index + 1} - Image URL not found.", quiet, level='warning')

                    # Stars extraction
                    try:
                        stars_element = item_details.find_element(By.CSS_SELECTOR, 'a[aria-label*="out of 5 stars"]')
                        stars_text = stars_element.get_attribute('aria-label').strip()
                        stars = float(stars_text.split(" ")[0]) if stars_text else None
                        qprint(f"Product {index + 1} - Extracted Stars: {stars}", quiet, level='info')
                    except NoSuchElementException:
                        stars = None
                        qprint(f"Product {index + 1} - Stars not found.", quiet, level='warning')

                    # Pattern and Style extraction
                    try:
                        twister_elements = item_details.find_elements(By.CSS_SELECTOR, 'span[id^="twisterText"]')
                        pattern = 'No pattern'
                        style = 'No style'
                        for twister_element in twister_elements:
                            twister_text = twister_element.text.strip()
                            if "Pattern Name" in twister_text:
                                pattern = twister_text.split(":")[1].strip() if ":" in twister_text else 'No pattern'
                            if "Style" in twister_text:
                                style = twister_text.split(":")[1].strip() if ":" in twister_text else 'No style'
                        qprint(f"Product {index + 1} - Extracted Pattern: {pattern}", quiet, level='info')
                        qprint(f"Product {index + 1} - Extracted Style: {style}", quiet, level='info')
                    except NoSuchElementException:
                        pattern = 'No pattern'
                        style = 'No style'
                        qprint(f"Product {index + 1} - Pattern or Style not found.", quiet, level='warning')

                    # Log all extracted fields
                    qprint(f"Product {index + 1} - Title: {title}, Subtitle: {subtitle}, Price: {price}, Price Added: {price_added}, Needs Product: {needs_product}, Has Product: {has_product}, Date Added: {date_added}, Reviews: {reviews}, Image URL: {image_url}, Stars: {stars}, Style: {style}, Pattern: {pattern}, Wishlist Name: {wishlist_name}, Price Drop Percent: {price_drop_percent}", quiet, level='info')

                    # Construct product data dictionary and update PostgreSQL
                    product_data = {
                        'title': title,
                        'price': price,
                        'price_added': price_added,
                        'price_drop_percent': price_drop_percent,
                        'link': link,
                        'asin': asin,
                        'image_url': image_url,
                        'reviews': reviews,
                        'date_added': date_added or None,
                        'stock_status': stock_status,
                        'stars': stars,
                        'pattern': pattern,
                        'style': style,
                        'subtitle': subtitle,
                        'needs_product': needs_product,
                        'has_product': has_product,
                        'affiliate_link': f"{link}&linkCode=ll1&tag=prographer-20" if asin else None,
                        'wishlist_name': wishlist_name or 'Unknown Wishlist'
                    }
                    if asin:
                        update_product_in_postgresql(cursor, product_data)
                        conn.commit()
                

                
                
                except Exception as e:
                    qprint(f"Product {index + 1} - Failed to extract product data: {e}", quiet, level='error')

            # Check for next page button and click if available
            try:
                next_page_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'ul.a-pagination li.a-last a'))
                )
                driver.execute_script("arguments[0].click();", next_page_button)
                time.sleep(3)
            except Exception as e:
                qprint("No next page button found or failed to click", quiet, level='info')
                break

        except Exception as e:
            qprint(f"Failed to load page: {e}", quiet, level='error')
            break
           

            
    # Commit and close DB connection at the end of the script
    conn.commit()
    cursor.close()
    conn.close()
    driver.quit()

    # After successfully scraping, mark the URL as scraped
    mark_url_as_scraped('wishlist_URL.txt', wishlist_url)       
    qprint(f"Finished processing wishlist: {wishlist_url}", quiet, level='info')
    
    