import json
import csv
import sys
import os
import time
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
# ID thư mục gốc trên Google Drive (Lấy ở Bước 1)
# Bot sẽ tạo thư mục con theo ngày bên trong thư mục này
PARENT_FOLDER_ID = '1udCflvt7ujbLCDS2cU1YtNZ9K58i84q5' 
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'service_account.json'

# Lấy tên file config từ tham số truyền vào (VD: configs/tgdd.json)
config_path = sys.argv[1]

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def create_daily_folder(service):
    # Tạo tên thư mục theo ngày: VD "2025-12-26"
    folder_name = datetime.now().strftime("%Y-%m-%d")
    
    # Kiểm tra xem folder đã tồn tại chưa
    query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    else:
        # Nếu chưa có thì tạo mới
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [PARENT_FOLDER_ID]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def get_price_selenium(product):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        driver.get(product['url'])
        time.sleep(3) # Chỉnh thời gian chờ tùy mạng
        
        element = None
        selector = product.get('selector')
        sel_type = product.get('type', 'css')
        
        if sel_type == 'css':
            element = driver.find_element(By.CSS_SELECTOR, selector)
        elif sel_type == 'xpath':
            element = driver.find_element(By.XPATH, selector)
            
        if element:
            clean_price = ''.join(filter(str.isdigit, element.text))
            return {
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Product": product['name'],
                "Price": clean_price,
                "URL": product['url']
            }
    except:
        pass # Lỗi thì bỏ qua hoặc log lại
    finally:
        driver.quit()
    return None

def main():
    print(f"--- Bắt đầu xử lý: {config_path} ---")
    
    # 1. Đọc danh sách link
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    results = []
    # 2. Chạy đa luồng (5 luồng cùng lúc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(get_price_selenium, p) for p in products]
        for future in concurrent.futures.as_completed(futures):
            data = future.result()
            if data:
                results.append(data)
                print(f"Done: {data['Product']}")

    if not results:
        print("Không lấy được dữ liệu nào.")
        return

    # 3. Lưu ra CSV tạm thời
    csv_filename = f"Report_{os.path.basename(config_path).replace('.json', '.csv')}"
    keys = results[0].keys()
    with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(results)

    # 4. Upload lên Google Drive
    try:
        service = get_drive_service()
        daily_folder_id = create_daily_folder(service)
        
        file_metadata = {
            'name': csv_filename,
            'parents': [daily_folder_id]
        }
        media = MediaFileUpload(csv_filename, mimetype='text/csv')
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"✅ Đã upload thành công lên Drive! File ID: {file.get('id')}")
    except Exception as e:
        print(f"❌ Lỗi upload Drive: {e}")

if __name__ == "__main__":
    main()
