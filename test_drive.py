import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- ĐIỀN THÔNG TIN CỦA BẠN VÀO ĐÂY ---
PARENT_FOLDER_ID = '1udCflvt7ujbLCDS2cU1YtNZ9K58i84q5' 
SERVICE_ACCOUNT_FILE = 'service_account.json'

def test_upload():
    print("1. Đang kết nối Google Drive...")
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Lỗi file key json: {e}")
        return

    print("2. Đang tạo file test...")
    file_name = "test_ket_noi.txt"
    with open(file_name, "w") as f:
        f.write("Xin chao! Robot da ket noi thanh cong.")

    print("3. Đang upload lên Drive...")
    try:
        file_metadata = {
            'name': file_name,
            'parents': [PARENT_FOLDER_ID]
        }
        media = MediaFileUpload(file_name, mimetype='text/plain')
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        print(f"✅ THÀNH CÔNG! File ID: {file.get('id')}")
        print("👉 Hãy mở Google Drive kiểm tra xem có file 'test_ket_noi.txt' chưa.")
        
    except Exception as e:
        print(f"❌ LỖI UPLOAD: {e}")
        print("👉 Gợi ý: Kiểm tra xem bạn đã Share quyền Editor cho email trong service_account.json chưa?")

if __name__ == "__main__":
    test_upload()
