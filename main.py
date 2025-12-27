import json
import csv
import sys
import os
import time
import random
import concurrent.futures
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CẤU HÌNH ---
# 1. ID thư mục Google Drive (Thay bằng ID thật của bạn)
PARENT_FOLDER_ID = 'DÁN_ID_THƯ_MỤC_DRIVE_VÀO_ĐÂY'

# 2. Tên file key (Đảm bảo file này nằm cùng thư mục)
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']

# 3. Số luồng chạy song song (Giảm xuống 3 cho an toàn)
MAX_WORKERS = 3

def get_drive_service():
    """Kết nối API Google Drive"""
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Drive: {e}")
        return None

def create_daily_folder(service):
    """Tạo folder theo ngày trên Drive"""
    if not service: return None
    
    folder_name = datetime.now().strftime("%Y-%m-%d")
    
    query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [PARENT_FOLDER_ID]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def get_price_selenium(product):
    """Hàm vào web lấy giá"""
    
    # --- CẤU HÌNH CHROME (CHỐNG CHẶN) ---
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Tắt tính năng báo hiệu Robot
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    # User Agent mới nhất
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    result = None
    try:
        # Random thời gian nghỉ để giống người dùng
        time.sleep(random.uniform(2, 4))
        
        print(f"▶️ Check: {product['name']}...")
        driver.get(product['url'])
        
        # Đợi web tải
        time.sleep(6) 
        
        # --- DEBUG QUAN TRỌNG: Kiểm tra xem có bị chặn không ---
        page_title = driver.title
        # Nếu title là "Access Denied" hoặc "Just a moment..." nghĩa là bị chặn
        print(f"   ℹ️ [DEBUG] Tiêu đề trang: {page_title}") 

        element = None
        selector = product.get('selector')
        sel_type = product.get('type', 'css')
        
        if sel_type == 'xpath':
            element = driver.find_element(By.XPATH, selector)
        else:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            
        if element:
            raw_text = element.text
            # Lọc chỉ lấy số
            clean_price = ''.join(filter(str.isdigit, raw_text))
            
            if clean_price:
                print(f"   ✅ GIÁ: {clean_price}")
                result = {
                    "Time": datetime.now().strftime("%H:%M:%S"),
                    "Product": product['name'],
                    "Price": clean_price,
                    "Source": product.get('source', 'Unknown'),
                    "URL": product['url']
                }
            else:
                 print(f"   ⚠️ Thấy element nhưng RỖNG text (Check lại selector).")
        
    except Exception as e:
        # In lỗi ngắn gọn
        print(f"   ❌ Lỗi {product['name']}: Không tìm thấy Selector hoặc Web chặn.")
    finally:
        driver.quit()
        
    return result

def main():
    # --- XỬ LÝ THAM SỐ (Đã sửa lỗi thụt đầu dòng ở đây) ---
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # Mặc định file mbw.json để test
        config_path = 'configs/mbw.json' 
        print(f"⚠️ Không có tham số. Đang chạy chế độ Test với file: {config_path}")

    # Kiểm tra file config tồn tại không
    if not os.path.exists(config_path):
        print(f"⛔ File cấu hình không tồn tại: {config_path}")
        return

    print(f"\n🚀 BẮT ĐẦU QUÉT: {config_path}")
    
    # 1. Đọc file JSON
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except Exception as e:
        print(f"⛔ Lỗi đọc file JSON (Kiểm tra dấu phẩy/ngoặc): {e}")
        return

    results = []
    
    # 2. Chạy đa luồng
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(get_price_selenium, p) for p in products]
        for future in concurrent.futures.as_completed(futures):
            data = future.result()
            if data:
                results.append(data)

    # 3. Ghi file kết quả
    if not results:
        print("\n⚠️ KẾT THÚC: Không lấy được dữ liệu nào.")
        return

    print(f"\n✅ Thu được {len(results)} kết quả. Đang lưu file...")
    
    base_name = os.path.basename(config_path).replace('.json', '.csv')
    csv_filename = f"Report_{base_name}"
    
    keys = ["Time", "Product", "Price", "Source", "URL"]
    
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"💾 Đã lưu file CSV: {csv_filename}")
    except Exception as e:
        print(f"❌ Lỗi ghi file CSV: {e}")
        return

    # 4. Upload lên Drive
    print("☁️ Đang upload lên Google Drive...")
    service = get_drive_service()
    if service:
        try:
            folder_id = create_daily_folder(service)
            
            file_metadata = {
                'name': csv_filename,
                'parents': [folder_id]
            }
            media = MediaFileUpload(csv_filename, mimetype='text/csv')
            
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f"🎉 THÀNH CÔNG! File ID: {file.get('id')}")
        except Exception as e:
            print(f"❌ Lỗi upload Drive: {e}")

if __name__ == "__main__":
    main()
