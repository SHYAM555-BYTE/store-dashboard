#!/usr/bin/env python
# coding: utf-8

# In[9]:


get_ipython().system('pip install selenium webdriver-manager')


# In[9]:


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import csv
import os
from datetime import datetime
import time

# --- CONFIG ---
EMAIL = os.getenv('ALBERTA_EMAIL')
PASSWORD = os.getenv('ALBERTA_PASSWORD')
OUTPUT_FILE = "eoy_report.csv"
TEMP_FILE = "eoy_report_temp.csv"

# --- INIT DRIVER ---
service = Service(ChromeDriverManager().install())
options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(service=service, options=options)
driver.maximize_window()
driver.get("https://customer.albertapayments.com/login")

wait = WebDriverWait(driver, 20)

# --- LOGIN ---
try:
    driver.find_element(By.ID, "input_email").send_keys(EMAIL)
    driver.find_element(By.ID, "input-password").send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button.login-btns").click()
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stores-menu")))
    print("✅ Login successful")
except Exception as e:
    print(f"❌ Login failed: {e}")
    driver.quit()
    exit()

# --- GET STORES ---
store_links = driver.find_elements(By.CSS_SELECTOR, "a.change_store")
print(f"Found {len(store_links)} stores. Processing daily data...")

# --- READ EXISTING DATA ---
store_data = {}
existing_store_years = {}

if os.path.exists(OUTPUT_FILE):
    print("Reading existing data...")
    with open(OUTPUT_FILE, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            store_name = row["Store Name"].strip()
            year = row["Year"].strip()
            if store_name not in existing_store_years:
                existing_store_years[store_name] = []
            existing_store_years[store_name].append(year)
            store_data[f"{store_name}_{year}"] = row

print(f"Found existing data for {len(store_data)} store-year combinations")

# --- PROCESS STORES ---
for i in range(len(store_links)):
    try:
        # Reopen store menu
        driver.find_element(By.CLASS_NAME, "stores-menu").click()
        time.sleep(2)
        
        store_links = driver.find_elements(By.CSS_SELECTOR, "a.change_store")
        store_name = store_links[i].text.strip()
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Switching to store: {store_name}")
        store_links[i].click()
        time.sleep(3)
        
        # Go to EOY report page with retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver.get("https://customer.albertapayments.com/eoyreport")
                time.sleep(5)
                
                # Try multiple ways to find year dropdown
                year_selectors = [
                    (By.ID, "selectYear"),
                    (By.CSS_SELECTOR, "select"),
                    (By.XPATH, "//select")
                ]
                
                year_element = None
                for by, selector in year_selectors:
                    try:
                        year_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((by, selector))
                        )
                        break
                    except TimeoutException:
                        continue
                
                if year_element:
                    break
                else:
                    raise TimeoutException("No year dropdown found")
                    
            except Exception as e:
                print(f"  ⚠️  Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    print(f"  ❌ Skipping {store_name} - could not load EOY page")
                    continue
                time.sleep(3)
        
        # **GET CURRENTLY SELECTED YEAR**
        try:
            year_dropdown = Select(year_element)
            current_year = year_dropdown.first_selected_option.get_attribute("value")
            if not current_year:
                current_year = year_dropdown.first_selected_option.text.strip()
        except:
            current_year = "Current"
        
        print(f"  📅 Current year: {current_year}")
        
        # Check if this store-year combo exists
        key = f"{store_name}_{current_year}"
        if store_name in existing_store_years and current_year in existing_store_years[store_name]:
            print(f"  🔄 UPDATING {store_name} {current_year}")
        else:
            print(f"  ➕ NEW entry for {store_name} {current_year}")
        
        # Click Generate button (if exists)
        try:
            generate_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            generate_btn.click()
            time.sleep(4)
        except:
            print("  ℹ️  No generate button found or already generated")
        
        # --- SCRAPE DATA ---
        def safe_text(xpath):
            try:
                element = driver.find_element(By.XPATH, xpath)
                return element.text.strip()
            except:
                return "N/A"
        
        taxable_sales = safe_text("//td[contains(text(),'Taxable Sales')]/following-sibling::td/button")
        non_taxable_sales = safe_text("//td[contains(text(),'Non-Taxable Sales')]/following-sibling::td/button")
        store_sales = safe_text("//td[contains(., 'Store Sales')]/following-sibling::td/button")
        total_tax = safe_text("//td[contains(text(),'Total Tax')]/following-sibling::td/button")
        total_paidout = safe_text("//td[contains(text(),'Total Paidout')]/following-sibling::td/button")
        transaction_count = safe_text("//td[contains(text(),'Transaction Count')]/following-sibling::td/button")
        
        # Save data
        new_entry = {
            "Year": current_year,
            "Store Name": store_name,
            "Taxable Sales": taxable_sales,
            "Non-Taxable Sales": non_taxable_sales,
            "Store Sales": store_sales,
            "Total Tax": total_tax,
            "Total Paidout": total_paidout,
            "Transaction Count": transaction_count
        }
        
        store_data[key] = new_entry
        print(f"  ✅ Saved: Sales=${store_sales}, Txns={transaction_count}")
        
    except Exception as e:
        print(f"  ❌ Error processing {store_name}: {e}")
        continue

# --- WRITE CSV ---
print("\n📊 Writing final data...")
try:
    with open(TEMP_FILE, "w", newline="") as csvfile:
        fieldnames = [
            "Year", "Store Name", "Taxable Sales", "Non-Taxable Sales", 
            "Store Sales", "Total Tax", "Total Paidout", "Transaction Count"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for store_year_key in sorted(store_data.keys()):
            if store_data[store_year_key]:
                writer.writerow(store_data[store_year_key])
    
    os.replace(TEMP_FILE, OUTPUT_FILE)
    print("✅ CSV saved successfully")
except Exception as e:
    print(f"❌ Failed to save CSV: {e}")

driver.quit()

print(f"\n🎉 Daily update complete!")
print(f"📈 Total entries: {len([v for v in store_data.values() if v])}")
print(f"🕐 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# In[7]:





# In[ ]:




