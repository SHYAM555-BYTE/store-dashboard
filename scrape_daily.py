import subprocess
subprocess.run(['pip', 'install', 'selenium', 'webdriver-manager', '-q'], check=True)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import csv, os
from datetime import datetime

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════
EMAIL         = os.getenv('ALBERTA_EMAIL')
PASSWORD      = os.getenv('ALBERTA_PASSWORD')
EOY_FILE      = 'end_of_report.csv'
EOM_FILE      = 'end_of_month_report.csv'
CURRENT_YEAR  = str(datetime.now().year)
CURRENT_MONTH = datetime.now().month
MONTH_NAMES   = {
    1:'January',  2:'February', 3:'March',     4:'April',
    5:'May',      6:'June',     7:'July',       8:'August',
    9:'September',10:'October', 11:'November',  12:'December'
}

# ══════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════
def get_text(driver, xpath):
    try:
        return driver.find_element(By.XPATH, xpath).text.strip()
    except:
        return 'N/A'

def read_csv(filepath):
    data, fieldnames = {}, []
    if not os.path.exists(filepath):
        print(f'  ⚠️  {filepath} not found — will create fresh')
        return data, fieldnames
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            # Skip any rows with empty store names
            if not row.get('Store Name', '').strip():
                continue
            key = (row['Store Name'].strip(), row['Year'].strip(), row['Month'].strip()) \
                  if 'Month' in fieldnames \
                  else (row['Store Name'].strip(), row['Year'].strip())
            data[key] = row
    print(f'  📂 Loaded {len(data)} existing records from {filepath}')
    return data, fieldnames

def write_csv(filepath, data_dict, fieldnames):
    # Filter out any rows with empty store names before writing
    clean_dict = {k: v for k, v in data_dict.items()
                  if v.get('Store Name', '').strip()}

    if len(clean_dict) < len(data_dict):
        print(f'  ⚠️  Dropped {len(data_dict) - len(clean_dict)} rows with empty Store Name')

    rows = sorted(clean_dict.values(), key=lambda x: (
        x.get('Store Name', ''), x.get('Year', ''),
        x.get('Month', '') if 'Month' in fieldnames else ''
    ))
    tmp = filepath + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, filepath)
    print(f'  💾 Saved {filepath} ({len(rows)} records)')

# ══════════════════════════════════════════════════════
# SCRAPE EOY — current year only
# ══════════════════════════════════════════════════════
def scrape_eoy(driver, store_name):
    if not store_name or not store_name.strip():
        print('    ⚠️  Skipping EOY — empty store name')
        return None

    wait = WebDriverWait(driver, 15)
    driver.get('https://customer.albertapayments.com/eoyreport')

    try:
        # Wait for year dropdown to be present, then select year
        year_select = wait.until(EC.presence_of_element_located((By.ID, 'selectYear')))
        Select(year_select).select_by_value(CURRENT_YEAR)

        # Wait for submit button to be clickable, then click
        submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']")))
        submit.click()

        # Wait until results table loads
        wait.until(EC.presence_of_element_located((By.XPATH, "//td[contains(text(),'Taxable Sales')]")))

        row = {
            'Year':              CURRENT_YEAR,
            'Store Name':        store_name,
            'Taxable Sales':     get_text(driver, "//td[contains(text(),'Taxable Sales')]/following-sibling::td/button"),
            'Non-Taxable Sales': get_text(driver, "//td[contains(text(),'Non-Taxable Sales')]/following-sibling::td/button"),
            'Total Store Sales': get_text(driver, "//td[contains(., 'Total Store')]/following-sibling::td/button"),
            'Cash':              get_text(driver, "//td[contains(text(),'CASH')]/following-sibling::td/button"),
            'Credit Card':       get_text(driver, "//td[contains(text(),'CREDIT CARD')]/following-sibling::td/button"),
            'Transaction Count': get_text(driver, "//td[contains(text(),'Transaction Count')]/following-sibling::td/button"),
            'Total Paidout':     get_text(driver, "//td[contains(text(),'Total Paidout')]/following-sibling::td/button"),
        }
        print(f"    ✅ EOY {CURRENT_YEAR} → Sales={row['Total Store Sales']}")
        return row

    except TimeoutException:
        print(f'    ❌ EOY timed out waiting for results for {store_name}')
        return None
    except Exception as e:
        print(f'    ❌ EOY failed: {e}')
        return None

# ══════════════════════════════════════════════════════
# SCRAPE EOM — current month only
# ══════════════════════════════════════════════════════
def scrape_eom(driver, store_name):
    if not store_name or not store_name.strip():
        print('    ⚠️  Skipping EOM — empty store name')
        return []

    wait = WebDriverWait(driver, 15)
    driver.get('https://customer.albertapayments.com/eomreport')

    rows = []
    month_name = MONTH_NAMES[CURRENT_MONTH]
    month_val  = f'{CURRENT_MONTH:02d}'
    print(f'    📅 {month_name} {CURRENT_YEAR}', end=' ... ')

    try:
        # Wait for year dropdown and select year
        year_select = wait.until(EC.presence_of_element_located((By.ID, 'year')))
        Select(year_select).select_by_value(CURRENT_YEAR)

        # Wait for month dropdown to be ready, then select month
        month_select = wait.until(EC.element_to_be_clickable((By.ID, 'month')))
        Select(month_select).select_by_value(month_val)

        # Wait for submit to be clickable, then click
        submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']")))
        submit.click()

        # Wait until results table loads
        wait.until(EC.presence_of_element_located((By.XPATH, "//td[contains(text(),'Taxable Sales')]")))

        row = {
            'Store Name':        store_name,
            'Year':              CURRENT_YEAR,
            'Month':             month_name,
            'Taxable Sales':     get_text(driver, "//td[contains(text(),'Taxable Sales')]/following-sibling::td/button"),
            'Non-Taxable Sales': get_text(driver, "//td[contains(text(),'Non-Taxable Sales')]/following-sibling::td/button"),
            'Total Store Sales': get_text(driver, "//td[contains(., 'Total Store')]/following-sibling::td/button"),
            'Cash':              get_text(driver, "//td[contains(text(),'CASH')]/following-sibling::td/button"),
            'Credit Card':       get_text(driver, "//td[contains(text(),'CREDIT CARD')]/following-sibling::td/button"),
            'Transaction Count': get_text(driver, "//td[contains(text(),'Transaction Count')]/following-sibling::td/button"),
            'Total Paidout':     get_text(driver, "//td[contains(text(),'Total Paidout')]/following-sibling::td/button"),
        }
        print(f"✅ Sales={row['Total Store Sales']}")
        rows.append(row)

    except TimeoutException:
        print(f'❌ Timed out waiting for results')
    except Exception as e:
        print(f'❌ {e}')

    return rows

# ══════════════════════════════════════════════════════
# MAIN RUN
# ══════════════════════════════════════════════════════
print(f"{'='*55}")
print(f"🚀 Scrape started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*55}")

# Load existing CSVs
eoy_data, eoy_fields = read_csv(EOY_FILE)
eom_data, eom_fields = read_csv(EOM_FILE)

if not eoy_fields:
    eoy_fields = ['Year','Store Name','Taxable Sales','Non-Taxable Sales',
                  'Total Store Sales','Cash','Credit Card','Transaction Count','Total Paidout']
if not eom_fields:
    eom_fields = ['Store Name','Year','Month','Taxable Sales','Non-Taxable Sales',
                  'Total Store Sales','Cash','Credit Card','Transaction Count','Total Paidout']

# Init driver
service = Service(ChromeDriverManager().install())
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(service=service, options=options)
driver.maximize_window()
wait = WebDriverWait(driver, 20)

# Login
driver.get('https://customer.albertapayments.com/login')
try:
    wait.until(EC.presence_of_element_located((By.ID, 'input_email'))).send_keys(EMAIL)
    driver.find_element(By.ID, 'input-password').send_keys(PASSWORD)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.login-btns'))).click()
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'stores-menu')))
    print('✅ Login successful')
except TimeoutException:
    print('❌ Login timed out')
    driver.quit()
    raise
except Exception as e:
    print(f'❌ Login failed: {e}')
    driver.quit()
    raise

# Get stores
wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'stores-menu'))).click()
wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a.change_store')))
store_links = driver.find_elements(By.CSS_SELECTOR, 'a.change_store')
stores = []
for link in store_links:
    name    = link.text.strip()
    onclick = link.get_attribute('onclick')
    form_id = onclick.split("getElementById('")[1].split("')")[0]
    if name:  # only add stores with a valid name
        stores.append({'name': name, 'form_id': form_id})
    else:
        print(f'  ⚠️  Skipping store link with empty name, form_id={form_id}')

# Close the menu
wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'stores-menu'))).click()
print(f'✅ Found {len(stores)} stores: {[s["name"] for s in stores]}')

# Loop all stores
for store in stores:
    store_name = store['name']
    print(f'\n🏪 === {store_name} ===')

    driver.execute_script(f"document.getElementById('{store['form_id']}').submit();")

    # Wait until the stores-menu confirms the store switch
    try:
        wait.until(lambda d: store_name.split('[')[0].strip().lower() in
                   d.find_element(By.CLASS_NAME, 'stores-menu').text.strip().lower())
        print(f'  ✅ Store switch confirmed')
    except TimeoutException:
        print(f'  ❌ Store switch timed out for {store_name}, skipping')
        continue

    # EOY — overwrite current year
    eoy_row = scrape_eoy(driver, store_name)
    if eoy_row:
        eoy_data[(store_name, CURRENT_YEAR)] = eoy_row

    # EOM — overwrite current month
    for row in scrape_eom(driver, store_name):
        eom_data[(store_name, CURRENT_YEAR, row['Month'])] = row

# Save
print()
write_csv(EOY_FILE, eoy_data, eoy_fields)
write_csv(EOM_FILE, eom_data, eom_fields)

driver.quit()
print(f"\n🎉 All done: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
