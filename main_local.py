import json
import sys
import io
import os
import time
import random
import glob
import subprocess
import concurrent.futures
from datetime import datetime

# --- CÀI ĐẶT THƯ VIỆN ---
# pip install selenium webdriver-manager gspread oauth2client

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
# ==============================================================================

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- THAY ID SHEET CỦA BẠN VÀO ĐÂY ---
MASTER_SHEET_ID = 'THAY_ID_SHEET_CUA_BAN_VAO_DAY' 

MAX_WORKERS = 3

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = r'C:\Users\Pavlusa\OneDrive\Work\Python\Google_Token\service_account.json'
FOLDER_CONFIG = os.path.join(CURRENT_DIR, 'configs')

# ==============================================================================
# 2. CÁC HÀM XỬ LÝ
# ==============================================================================

def kill_old_drivers():
    """Chỉ tắt chromedriver cũ, KHÔNG tắt Chrome người dùng"""
    try:
        if os.name == 'nt':
            subprocess.call("taskkill /F /IM chromedriver.exe /T", shell=True, stderr=subprocess.DEVNULL)
    except: pass

def get_google_sheet_client():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ Lỗi: Không thấy file Key tại {SERVICE_ACCOUNT_FILE}")
        print(f"👉 Hãy tạo thư mục C:\\AutoPrice và copy file key vào đó!")
        return None
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Lỗi Sheet: {e}")
        return None

def upload_to_sheet(client, dealer_name, data_rows):
    if not client or not data_rows: return
    try:
        sh = client.open_by_key(MASTER_SHEET_ID)
        # Tên tab: TGDD, FPT...
        tab_name = dealer_name.strip().replace(" ", "_").upper()
        
        try:
            worksheet = sh.worksheet(tab_name)
        except:
            print(f"   ✨ Tạo Tab mới '{tab_name}'...")
            worksheet = sh.add_worksheet(title=tab_name, rows=2000, cols=10)
            worksheet.append_row(["Date", "Time", "Dealer", "Product", "Price", "Status", "URL"])

        current_date_str = datetime.now().strftime("%d/%m/%Y")
        rows_to_append = []
        for item in data_rows:
            rows_to_append.append([
                current_date_str, item['Time'], dealer_name,
                item['Product'], item['Price'], item['Status'], item['URL']
            ])
            
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
            print(f"   ✅ Đã lưu {len(rows_to_append)} dòng.")
    except Exception as e:
        print(f"   ❌ Lỗi Upload: {e}")

def get_driver():
    opts = Options()
    # Headless new: Chạy ẩn, không chiếm chuột
    opts.add_argument("--headless=new") 
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--log-level=3")
    
    # Chặn load ảnh để chạy nhanh
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except:
        return webdriver.Chrome(options=opts)

def process_dealer_smart(config_file, gs_client):
    """Phiên bản Thông Minh: Mở 1 lần - Quét tất cả"""
    dealer_name = os.path.basename(config_file).replace('.json', '')
    print(f"\n🔵 XỬ LÝ: {dealer_name.upper()}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except: return

    results = []
    driver = None

    try:
        # Mở trình duyệt 1 lần duy nhất ở đây
        print("   🚀 Đang khởi động Chrome (Chỉ 1 lần)...")
        driver = get_driver()
        
        total = len(products)
        for i, product in enumerate(products):
            try:
                # Quét từng sản phẩm
                driver.get(product['url'])
                time.sleep(2) # Nghỉ ngắn

                result = {
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Product": product.get('name', 'Unknown'),
                    "Price": "0",
                    "Status": "Fail",
                    "URL": product['url']
                }

                selector = product.get('selector')
                sel_type = product.get('type', 'css')
                element = None

                if sel_type == 'xpath':
                    element = driver.find_element(By.XPATH, selector)
                else:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                
                if element:
                    clean_price = ''.join(filter(str.isdigit, element.text))
                    if clean_price:
                        result['Price'] = clean_price
                        result['Status'] = 'OK'
                
                results.append(result)
                print(f"   [{i+1}/{total}] {result['Status']} - {result['Price']}")

            except Exception:
                # Nếu lỗi 1 link thì bỏ qua, chạy link tiếp theo
                print(f"   [{i+1}/{total}] Lỗi/Không tìm thấy giá.")
                results.append({"Time": datetime.now().strftime("%H:%M:%S"), "Product": product['name'], "Price": "0", "Status": "Error", "URL": product['url']})

    except Exception as e:
        print(f"❌ Lỗi trình duyệt: {e}")
    finally:
        # Quét xong hết mới tắt
        if driver: 
            driver.quit()
            print("   💤 Đã đóng Chrome.")

    print("   -> Upload dữ liệu...")
    upload_to_sheet(gs_client, dealer_name, results)

def main():
    # Gọi đúng tên hàm mới
    kill_old_drivers()
    
    print(f"📂 Config tại: {FOLDER_CONFIG}")
    
    gs_client = get_google_sheet_client()
    if not gs_client: return

    if not os.path.exists(FOLDER_CONFIG):
        os.makedirs(FOLDER_CONFIG)
        sample = [{"name":"iPhone 15","url":"https://www.thegioididong.com/dtdd/iphone-15","selector":".box-price-present","type":"css"}]
        with open(os.path.join(FOLDER_CONFIG, 'tgdd.json'), 'w', encoding='utf-8') as f:
            json.dump(sample, f, indent=2)

    config_files = glob.glob(os.path.join(FOLDER_CONFIG, "*.json"))
    print(f"🚀 TÌM THẤY {len(config_files)} ĐẠI LÝ.")
    
    for config_file in config_files:
        process_dealer_smart(config_file, gs_client)
        print("-" * 40)

    print("\n🎉 HOÀN TẤT!")

if __name__ == "__main__":
    main()
