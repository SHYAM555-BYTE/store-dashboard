
import subprocess
subprocess.run(['pip', 'install', 'selenium', 'webdriver-manager', '-q'], check=True)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import csv, os, time
from datetime import datetime
# --- CONFIG ---
EMAIL = os.getenv('ALBERTA_EMAIL')
PASSWORD = os.getenv('ALBERTA_PASSWORD')
# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════
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
            key = (row['Store Name'].strip(), row['Year'].strip(), row['Month'].strip()) \
                  if 'Month' in fieldnames \
                  else (row['Store Name'].strip(), row['Year'].strip())
            data[key] = row
    print(f'  📂 Loaded {len(data)} existing records from {filepath}')
    return data, fieldnames

def write_csv(filepath, data_dict, fieldnames):
    rows = sorted(data_dict.values(), key=lambda x: (
        x.get('Store Name',''), x.get('Year',''),
        x.get('Month','') if 'Month' in fieldnames else ''
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
    wait = WebDriverWait(driver, 10)
    driver.get('https://customer.albertapayments.com/eoyreport')
    time.sleep(3)
    try:
        Select(wait.until(EC.presence_of_element_located((By.ID, 'selectYear')))).select_by_value(CURRENT_YEAR)
        time.sleep(1)
        driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        time.sleep(3)
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
    except Exception as e:
        print(f'    ❌ EOY failed: {e}')
        return None

# ══════════════════════════════════════════════════════
# SCRAPE EOM — Jan → current month only
# ══════════════════════════════════════════════════════
def scrape_eom(driver, store_name):
    wait = WebDriverWait(driver, 10)
    driver.get('https://customer.albertapayments.com/eomreport')
    time.sleep(3)
    rows = []
    for month_num in [CURRENT_MONTH]:
        month_name = MONTH_NAMES[month_num]
        month_val  = f'{month_num:02d}'
        print(f'    📅 {month_name} {CURRENT_YEAR}', end=' ... ')
        try:
            Select(wait.until(EC.presence_of_element_located((By.ID, 'year')))).select_by_value(CURRENT_YEAR)
            time.sleep(0.5)
            Select(driver.find_element(By.ID, 'month')).select_by_value(month_val)
            time.sleep(0.5)
            driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
            time.sleep(3)
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
    driver.find_element(By.ID, 'input_email').send_keys(EMAIL)
    driver.find_element(By.ID, 'input-password').send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, 'button.login-btns').click()
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'stores-menu')))
    print('✅ Login successful')
except Exception as e:
    print(f'❌ Login failed: {e}')
    driver.quit()
    raise

# Get stores
driver.find_element(By.CLASS_NAME, 'stores-menu').click()
time.sleep(2)
store_links = driver.find_elements(By.CSS_SELECTOR, 'a.change_store')
stores = []
for link in store_links:
    name    = link.text.strip()
    onclick = link.get_attribute('onclick')
    form_id = onclick.split("getElementById('")[1].split("')")[0]
    stores.append({'name': name, 'form_id': form_id})
driver.find_element(By.CLASS_NAME, 'stores-menu').click()
print(f'✅ Found {len(stores)} stores: {[s["name"] for s in stores]}')

# Loop all stores
for store in stores:
    store_name = store['name']
    print(f'\n🏪 === {store_name} ===')
    driver.execute_script(f"document.getElementById('{store['form_id']}').submit();")
    time.sleep(3)

    # EOY — overwrite current year
    eoy_row = scrape_eoy(driver, store_name)
    if eoy_row:
        eoy_data[(store_name, CURRENT_YEAR)] = eoy_row

    # EOM — overwrite Jan → current month
    for row in scrape_eom(driver, store_name):
        eom_data[(store_name, CURRENT_YEAR, row['Month'])] = row

# Save
print()
write_csv(EOY_FILE, eoy_data, eoy_fields)
write_csv(EOM_FILE, eom_data, eom_fields)

driver.quit()
print(f"\n🎉 All done: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")




