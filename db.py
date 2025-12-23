# db.py
import os
from fastapi import HTTPException
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

# --- 資料庫設定 ---
# 在正式環境中，建議使用 os.getenv 從環境變數讀取，安全性較高
DEFAULT_DB = "work_platform"
DB_USER = "postgres"
DB_PASSWORD = "ux7e4ywp"
DB_HOST = "localhost"
DB_PORT = 5432

# 組合連線字串 (Connection String)
DATABASE_URL = f"dbname={DEFAULT_DB} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

# 宣告全域連線池變數，預設為 None
_pool: AsyncConnectionPool | None = None

async def getDB():
    """
    FastAPI 的 Dependency (依賴項) 函式。
    
    用途：
    1. 管理資料庫連線池的生命週期。
    2. 確保每次請求都有可用的連線。
    3. 使用 yield 讓 FastAPI 在請求結束後自動關閉該次連線。
    """
    global _pool

    # Lazy Loading: 第一次被呼叫時才建立連線池
    if _pool is None:
        print("正在初始化資料庫連線池 (Initializing Connection Pool)...")
        _pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            kwargs={"row_factory": dict_row},  # 設定：讓查詢結果變成 Dictionary (例如 record['id']) 而不是 Tuple
            open=False  # 先設定好參數，暫不開啟，由下方 open() 觸發
        )
        try:
            await _pool.open()  # 正式開啟連線池
            print("資料庫連線池已開啟 (Connection Pool Opened).")
        except Exception as e:
            print(f"無法開啟連線池: {e}")
            _pool = None
            raise

    if _pool is None:
        raise HTTPException(status_code=500, detail="Database connection pool is not available.")

    # 使用 context manager (async with) 取得連線
    # 這會自動處理連線的借出與歸還
    async with _pool.connection() as conn:
        yield conn