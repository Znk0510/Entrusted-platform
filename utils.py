import os
import shutil
from datetime import datetime
from fastapi import UploadFile, HTTPException
import aiofiles # 這是非同步檔案處理套件，避免上傳大檔案時卡住整個伺服器

# --- 1. 設定檔案儲存路徑常數 ---
# 統一管理資料夾名稱，以後如果要改路徑，只要改這裡就好
UPLOAD_ROOT = "uploads"             # 所有上傳檔案的根目錄
FOLDER_PROPOSALS = "proposals"      # 子資料夾：存放提案計畫書
FOLDER_DELIVERABLES = "deliverables" # 子資料夾：存放接案人的交付檔案
FOLDER_AVATARS = "avatars"          # 子資料夾：存放使用者頭像

def setup_upload_directories():
    """
    初始化資料夾結構：
    在伺服器啟動時可以呼叫此函式，確保資料夾都已經存在。
    exist_ok=True 表示如果資料夾已經存在，就跳過，不會報錯。
    """
    os.makedirs(UPLOAD_ROOT, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_ROOT, FOLDER_AVATARS), exist_ok=True) 

async def save_upload_file(file: UploadFile, project_id: int, sub_folder: str) -> str:
    """
    通用檔案儲存函式 (用於專案相關檔案)
    
    參數:
    - file: 使用者上傳的檔案物件
    - project_id: 專案 ID (用來分類資料夾，例如 uploads/101/...)
    - sub_folder: 子資料夾名稱 (例如 'proposals' 或 'deliverables')
    
    回傳:
    - 檔案在伺服器上的相對路徑 (字串)，準備存入資料庫
    """
    
    # 1. 建立目標資料夾路徑: uploads/{project_id}/{sub_folder}
    # 這樣每個專案的檔案都會分開，不會混在一起
    project_dir = os.path.join(UPLOAD_ROOT, str(project_id))
    target_dir = os.path.join(project_dir, sub_folder)
    
    # 確保資料夾存在
    os.makedirs(target_dir, exist_ok=True)
    
    # 2. 處理檔名 (安全性與防重覆)
    # 加上時間戳記 (Timestamp)，避免不同人上傳同名檔案 (如 resume.pdf) 互相覆蓋
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 清洗檔名：把空白、斜線等可能造成路徑錯誤的符號換成底線
    safe_filename = file.filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
    
    # 組合新檔名：例如 20231225_103000_proposal.pdf
    new_filename = f"{timestamp}_{safe_filename}"
    
    # 完整儲存路徑
    file_path = os.path.join(target_dir, new_filename)
    
    # 3. 寫入檔案 (非同步串流寫入)
    # 使用 aiofiles 與 chunks (分塊) 讀取，這對於大檔案非常重要，
    # 可以避免記憶體爆掉，也不會因為硬碟寫入慢而卡住其他使用者的請求。
    async with aiofiles.open(file_path, 'wb') as out_file:
        while content := await file.read(1024):  # 每次讀取 1024 bytes
            await out_file.write(content)
            
    # 回傳給資料庫的路徑格式 (使用 / 分隔，確保跨平台相容性)
    return f"{UPLOAD_ROOT}/{project_id}/{sub_folder}/{new_filename}"

# --- 新增：專門存頭像的函式 ---
async def save_avatar_file(file: UploadFile, user_id: int) -> str:
    """
    儲存使用者頭像
    
    特點:
    - 不根據專案分資料夾，而是統一放在 uploads/avatars/
    - 檔名包含 user_id，方便管理
    
    回傳:
    - 相對路徑: uploads/avatars/user_1_20231225.jpg
    """
    target_dir = os.path.join(UPLOAD_ROOT, FOLDER_AVATARS)
    os.makedirs(target_dir, exist_ok=True)
    
    # 產生檔名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # 取得原始副檔名 (例如 .jpg, .png)
    ext = os.path.splitext(file.filename)[1] 
    
    # 組合檔名: user_{user_id}_{時間}.{副檔名}
    new_filename = f"user_{user_id}_{timestamp}{ext}"
    
    file_path = os.path.join(target_dir, new_filename)
    
    # 寫入檔案
    async with aiofiles.open(file_path, 'wb') as out_file:
        while content := await file.read(1024): 
            await out_file.write(content)
            
    return f"{UPLOAD_ROOT}/{FOLDER_AVATARS}/{new_filename}"