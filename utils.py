import os
import shutil
from datetime import datetime
from fastapi import UploadFile, HTTPException
import aiofiles

# 定義基礎上傳路徑
UPLOAD_ROOT = "uploads"
FOLDER_PROPOSALS = "proposals"       # 報價/提案資料夾
FOLDER_DELIVERABLES = "deliverables" # 結案/更新版本資料夾

def setup_upload_directories():
    os.makedirs(UPLOAD_ROOT, exist_ok=True)

async def save_upload_file(file: UploadFile, project_id: int, sub_folder: str) -> str:
    """
    通用檔案儲存函式
    結構: uploads/{project_id}/{sub_folder}/
    檔名處理: {timestamp}_{original_filename} (防止覆蓋)
    """
    # 1. 建立專案專屬資料夾結構
    project_dir = os.path.join(UPLOAD_ROOT, str(project_id))
    target_dir = os.path.join(project_dir, sub_folder)
    
    os.makedirs(target_dir, exist_ok=True)
    
    # 2. 處理檔名 (加上時間戳記防止覆蓋)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 移除檔名中的危險字元 (簡單處理)
    safe_filename = file.filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
    new_filename = f"{timestamp}_{safe_filename}"
    
    file_path = os.path.join(target_dir, new_filename)
    
    # 3. 寫入檔案
    async with aiofiles.open(file_path, 'wb') as out_file:
        while content := await file.read(1024):  # async read chunk
            await out_file.write(content)
            
    # 4. 回傳相對路徑 (存入資料庫用)
    # 使用 / 作為分隔符，確保在不同作業系統路徑一致
    return f"{UPLOAD_ROOT}/{project_id}/{sub_folder}/{new_filename}"