import json
import sys
import os
import time
import random
import glob
import concurrent.futures
from datetime import datetime

# Thư viện Google Sheet
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Thư viện Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CẤU HÌNH ---
FOLDER_CONFIG = 'configs'
MAX_WORKERS = 10  # Số luồng chạy song song
SERVICE_ACCOUNT_FILE = 'service_account.json'

# --- QUAN TRỌNG: THAY ID FILE SHEET CỦA BẠN VÀO ĐÂY ---
# (Lấy ID từ file Master Sheet bạn đã tạo và share quyền Editor)
MASTER_SHEET_ID = '1WYj8fx8jLanw5gzb1-zxJSDyRB8aOMh8j6zEosfzJAw' 
# -----------------------------------------------------

def get_google_sheet_client():
    """Kết nối tới Google Sheet"""
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheet: {e}")
        return None

def upload_to_sheet(client, dealer_name, data_rows):
    """
    Chế độ tích lũy: 
    - Nếu chưa có Tab -> Tạo mới + Ghi tiêu đề.
    - Nếu có rồi -> Nối tiếp dữ liệu (Append).
    """
    if not client or not data_rows: return

    try:
        sh = client.open_by_key(MASTER_SHEET_ID)
        
        # Đặt tên Tab theo tên đại lý (Viết hoa, thay dấu cách bằng gạch dưới)
        tab_name = dealer_name.strip().replace(" ", "_").upper()
        
        worksheet = None
        is_new_sheet = False

        # 1. Kiểm tra Tab đã tồn tại chưa
        try:
            worksheet = sh.worksheet(tab_name)
        except:
            # Nếu chưa có thì tạo mới
            print(f"   ✨ Tab '{tab_name}' chưa có. Đang tạo mới...")
            # Tạo dư dả hàng để dùng lâu dài
            worksheet = sh.add_worksheet(title=tab_name, rows=2000, cols=10)
            is_new_sheet = True

        # 2. Chuẩn bị dữ liệu
        current_date_str = datetime.now().strftime("%d/%m/%Y")
        
        # Nếu là sheet mới tinh thì thêm dòng tiêu đề
        if is_new_sheet:
            header = ["Date", "Time", "Dealer", "Product", "Price", "Status", "URL"]
            worksheet.append_row(header)

        # Chuẩn bị danh sách các dòng dữ liệu cần thêm
        rows_to_append = []
        for item in data_rows:
            row = [
                current_date_str,   # Ngày quét
                item['Time'],       # Giờ quét
                dealer_name,        # Tên đại lý
                item['Product'],    # Tên sản phẩm
                item['Price'],      # Giá tìm được
                item['Status'],     # Trạng thái (OK/Fail)
                item['URL']         # Link gốc
            ]
            rows_to_append.append(row)
            
        # 3. Ghi nối đuôi vào cuối danh sách
        if rows_to_append:
            worksheet.append_rows(rows_to_append)
            print(f"   ✅ Đã nối thêm {len(rows_to_append)} dòng vào tab '{tab_name}'.")
        
    except Exception as e:
        print(f"   ❌ Lỗi Upload Sheet: {e}")

def get_driver():
    """Cấu hình Selenium"""
    opts = Options()
    # opts.add_argument("--headless") # Bỏ comment nếu muốn chạy ẩn
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled") 
    opts.add_argument("--window-size=1280,720")
    # Fake User Agent để đỡ bị chặn
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument("--log-level=3") # Tắt log rác

    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Driver: {e}")
        return webdriver.Chrome(options=opts)

def scrape_product(product):
    """Hàm lấy giá 1 sản phẩm"""
    driver = None
    result = {
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Product": product.get('name', 'Unknown'),
        "Price": "0",
        "Status": "Fail",
        "URL": product.get('url', '')
    }

    try:
        driver = get_driver()
        driver.get(product['url'])
        time.sleep(random.uniform(2, 4)) # Chờ load

        # Lấy giá
        selector = product.get('selector')
        sel_type = product.get('type', 'css')
        element = None
        
        if sel_type == 'xpath':
            element = driver.find_element(By.XPATH, selector)
        else:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            
        if element:
            raw_text = element.text
            clean_price = ''.join(filter(str.isdigit, raw_text))
            if clean_price:
                result['Price'] = clean_price
                result['Status'] = 'OK'
                
    except Exception:
        pass # Lỗi thì giữ nguyên Status Fail
    finally:
        if driver: driver.quit()
        
    return result

def process_dealer(config_file, gs_client):
    """Xử lý 1 đại lý: Quét xong -> Upload luôn"""
    dealer_name = os.path.basename(config_file).replace('.json', '')
    print(f"\n🔵 BẮT ĐẦU: {dealer_name.upper()}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except:
        print(f"❌ Lỗi đọc file config: {config_file}")
        return

    results = []
    
    # Chạy đa luồng quét giá
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(scrape_product, p) for p in products]
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            data = future.result()
            results.append(data)
            # In tiến độ dạng gọn: [1/100] OK
            print(f"   [{i+1}/{len(products)}] {data['Status']} - {data['Product'][:20]}...", end='\r')

    print(f"\n   ✅ Quét xong {len(results)} sản phẩm. Đang upload...")
    
    # Upload lên Sheet
    upload_to_sheet(gs_client, dealer_name, results)

def main():
    # 1. Kết nối Google Sheet trước để check
    print("🔌 Đang kết nối Google Services...")
    gs_client = get_google_sheet_client()
    if not gs_client:
        print("⛔ Không kết nối được Google Sheet. Dừng chương trình.")
        return

    # 2. Tìm file config
    if not os.path.exists(FOLDER_CONFIG):
        os.makedirs(FOLDER_CONFIG)
        # Tạo file mẫu nếu chưa có
        sample = [{"name":"Test iPhone","url":"https://www.thegioididong.com/dtdd/iphone-15-pro-max","selector":".box-price-present","type":"css"}]
        with open(os.path.join(FOLDER_CONFIG, 'test_mau.json'), 'w') as f:
            json.dump(sample, f)

    config_files = glob.glob(os.path.join(FOLDER_CONFIG, "*.json"))
    print(f"🚀 TÌM THẤY {len(config_files)} ĐẠI LÝ.")

    # 3. Chạy từng đại lý
    for config_file in config_files:
        process_dealer(config_file, gs_client)
        print("-" * 30)

    print("\n🎉🎉🎉 HOÀN TẤT TOÀN BỘ!")

if __name__ == "__main__":
    main()


