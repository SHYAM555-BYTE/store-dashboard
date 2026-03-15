import subprocess
subprocess.run(['pip', 'install', 'selenium', 'webdriver-manager', '-q'], check=True)

import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
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
            if not row.get('Store Name', '').strip():
                continue
            key = (row['Store Name'].strip(), row['Year'].strip(), row['Month'].strip()) \
                  if 'Month' in fieldnames \
                  else (row['Store Name'].strip(), row['Year'].strip())
            data[key] = row
    print(f'  📂 Loaded {len(data)} existing records from {filepath}')
    return data, fieldnames

def write_csv(filepath, data_dict, fieldnames):
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
# DYNAMIC FIELD SCRAPER — no hardcoded XPaths
# ══════════════════════════════════════════════════════
def scrape_fields(driver):
    results = {}
    rows = driver.find_elements(By.CSS_SELECTOR, "tr")

    for row in rows:
        try:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) >= 2:
                label = tds[0].text.strip()
                label = re.sub(r'\s*\([^)]*\)', '', label).strip()
                label = ' '.join(label.split())
                # ✅ Normalize to Title Case so it matches build_row keys
                label = label.title()

                try:
                    value = tds[1].find_element(By.TAG_NAME, "button").text.strip()
                except:
                    value = tds[1].text.strip()

                if label and value:
                    results[label] = value

        except StaleElementReferenceException:
            continue  # ✅ Skip stale rows instead of crashing

    if results:
        print(f'    🔍 Fields found: {list(results.keys())}')
    else:
        print(f'    ⚠️  No fields found on page')

    return results
    
def build_row(base, fields):
    row = {
        **base,
        'Taxable Sales':     fields.get('Taxable Sales',     'N/A'),
        'Non-Taxable Sales': fields.get('Non-Taxable Sales', 'N/A'),
        'Total Store Sales': fields.get('Total Store Sales', 'N/A'),
        'Cash':              fields.get('Cash',              'N/A'),
        'Credit Card':       fields.get('Credit Card',       'N/A'),
        'Transaction Count': fields.get('Transaction Count', 'N/A'),
        'Total Paidout':     fields.get('Total Paidout',     'N/A'),
    }

    bad = [k for k, v in row.items() if v == 'N/A' and k not in base]
    if bad:
        print(f'    ⚠️  Missing fields: {bad}')

    return row
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
        year_select = wait.until(EC.presence_of_element_located((By.ID, 'selectYear')))
        Select(year_select).select_by_value(CURRENT_YEAR)

        submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']")))
        submit.click()

        # Wait for table to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr td button")))

        fields = scrape_fields(driver)
        row = build_row({'Year': CURRENT_YEAR, 'Store Name': store_name}, fields)

        print(f"    ✅ EOY {CURRENT_YEAR} → Sales={row['Total Store Sales']}")
        return row

    except TimeoutException:
        print(f'    ❌ EOY timed out for {store_name}')
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

    month_name = MONTH_NAMES[CURRENT_MONTH]
    month_val  = f'{CURRENT_MONTH:02d}'
    print(f'    📅 {month_name} {CURRENT_YEAR}', end=' ... ')

    try:
        year_select = wait.until(EC.presence_of_element_located((By.ID, 'year')))
        Select(year_select).select_by_value(CURRENT_YEAR)

        month_select = wait.until(EC.element_to_be_clickable((By.ID, 'month')))
        Select(month_select).select_by_value(month_val)

        submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']")))
        submit.click()

        # Wait for table to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr td button")))

        fields = scrape_fields(driver)
        row = build_row(
            {'Store Name': store_name, 'Year': CURRENT_YEAR, 'Month': month_name},
            fields
        )

        print(f"✅ Sales={row['Total Store Sales']}")
        return [row]

    except TimeoutException:
        print(f'❌ Timed out waiting for results')
        return []
    except Exception as e:
        print(f'❌ {e}')
        return []

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
    name    = ' '.join(link.get_attribute('innerText').split())
    onclick = link.get_attribute('onclick')
    form_id = onclick.split("getElementById('")[1].split("')")[0]
    if name:
        stores.append({'name': name, 'form_id': form_id})
    else:
        print(f'  ⚠️  Skipping store link with empty name, form_id={form_id}')

wait.until(EC.element_to_be_clickable((By.CLASS_NAME, 'stores-menu'))).click()
print(f'✅ Found {len(stores)} stores: {[s["name"] for s in stores]}')

# Loop all stores
for store in stores:
    store_name = store['name']
    print(f'\n🏪 === {store_name} ===')

    driver.execute_script(f"document.getElementById('{store['form_id']}').submit();")

    def store_switched(d):
        try:
            return store_name.split('[')[0].strip().lower() in \
                   d.find_element(By.CLASS_NAME, 'stores-menu').text.strip().lower()
        except StaleElementReferenceException:
            return False

    try:
        wait.until(store_switched)
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
