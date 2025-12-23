from psycopg_pool import AsyncConnectionPool #使用connection pool
from psycopg.rows import dict_row
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, create_engine
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import HTTPException, status # 引入 FastAPI 錯誤處理
import psycopg

# db.py
defaultDB = "work_platform"
dbUser = "postgres"
dbPassword = "03020910"
dbHost = "localhost"
dbPort = 5432

#DATABASE_URL = f"dbname={defaultDB} user={dbUser} password={dbPassword} host={dbHost} port={dbPort}"
DATABASE_CONNINFO = (
    f"dbname={defaultDB} "
    f"user={dbUser} "
    f"password={dbPassword} "
    f"host={dbHost} "
    f"port={dbPort}"
)

#宣告變數，預設為None
_pool: AsyncConnectionPool | None = None


# =================================================================
# 1. 在 db.py 內部定義 Base
# =================================================================
# 宣告所有的模型類別都將繼承自 Base
#Base = declarative_base()

# 定義評價方向的常數
#RATING_DIRECTION = {
  #  'CLIENT_TO_CONTRACTOR': 'CL2C',  # 甲方評乙方
   # 'CONTRACTOR_TO_CLIENT': 'C2CL'  # 乙方評甲方
#}

# =================================================================
# 2. 定義 Rating 模型 (直接繼承 Base)
# =================================================================
# 評價模型定義 (保持不變)
#class Rating(Base):
 #   __tablename__ = 'ratings'
    
    #rating_id = Column(Integer, primary_key=True)
    ## ⚠️ 注意：如果您的 users/projects 表使用 'id' 作為主鍵，這裡的外鍵就應該是 'users.id' 和 'projects.id'
   # project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
   # rater_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
   # rated_user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    #    
   # rating_direction = Column(String(10), nullable=False)
    #overall_comment = Column(Text, nullable=True)
    #rating_date = Column(DateTime, default=datetime.utcnow)
#
    #output_quality_score = Column(Integer)
   # execution_efficiency_score = Column(Integer)
   # contractor_attitude_score = Column(Integer)
#
   # requirement_rationality_score = Column(Integer)
   # acceptance_difficulty_score = Column(Integer)
    #client_attitude_score = Column(Integer)
    
    # -----------------------------------------------------------------
# 3. 連線池管理與依賴函式 (FastAPI 使用)
# -----------------------------------------------------------------

async def init_pool():
    """
    給 main.py lifespan 使用
    """
    global _pool
    if _pool is not None:
        return

    print("🔌 初始化資料庫連線池...")
    try:
        _pool = AsyncConnectionPool(
            conninfo=DATABASE_CONNINFO,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        await _pool.open()
        print("✅ Database pool ready")
    except Exception as e:
        _pool = None
        print("❌ Database pool init failed:", e)
        raise

#async def init_pool():
   # """
   # 應用程式啟動時呼叫，用於初始化連線池。
   # """
   # global _pool
   # if _pool is None:
    #    print("Initializing Connection Pool...")
       # try:
            # 使用修正後的 DATABASE_URL
          #  _pool = AsyncConnectionPool(
          #      conninfo=DATABASE_CONNINFO,
         #       kwargs={"row_factory": dict_row}, # 設定查詢結果以dictionary方式回傳
          #      open=False # 不直接開啟
         #   )
         #   await _pool.open() # 等待開啟完成
         #   print("Connection Pool Opened.")
       # except Exception as e:
       #     _pool = None 
       #     print("Failed to init DB pool: ", e)          
       #     raise # 拋出異常


#async def close_pool():
  #  """
   # 應用程式關閉時呼叫，用於關閉連線池。
   # """
    #global _pool
    #if _pool is not None:
     #   await _pool.close()
     #   print("Connection Pool Closed.")
      #  _pool = None

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("🛑 Database pool closed")


#@asynccontextmanager
#async def get_conn_context() -> AsyncGenerator[AsyncConnectionPool, None]:
   # """
  #  內部使用的連線池上下文管理器，用於在 Rating 邏輯中執行 SQL。
  #  """
   # if _pool is None:
   #     raise Exception("Database connection pool has not been initialized.")
   # yield _pool

    
# -----------------------------------------------------------------
# 4. 數據庫連接和 Session（可選，但常用於 db.py）
# -----------------------------------------------------------------
# 創建 Engine
#engine = create_engine(DATABASE_URL, echo = True)

# 創建 Session
#Session = sessionmaker(bind=engine)
#session = Session()

#AsyncSessionLocal = sessionmaker(
  #  bind=engine,
   # expire_on_commit=False,
   ## class_=AsyncSession
#)

# ⚠️ 備註：您需要確保 'projects' 和 'users' 表也繼承自此處定義的 `Base`。

# ===============================
# FastAPI Dependency
# ===============================

#取得DB連線物件
#async def getDB():
	#global _pool
	#if _pool is None:
	#	#lazy create, 等到main.py來呼叫時再啟用 _pool
	#	print("Initializing Connection Pool...")
	#	_pool = AsyncConnectionPool(
	#		conninfo=DATABASE_CONNINFO,
	#		kwargs={"row_factory": dict_row}, #設定查詢結果以dictionary方式回傳
	#		open=False #不直接開啟
	#	)
	#	try:
	#		await _pool.open() #等待開啟完成
	#		print("Connection Pool Opened.")
	#	except Exception as e:
	#		print(f"Failed to open connection pool: {e}")
	#		_pool = None # 如果開啟失敗，重設為 None
	#		raise # 拋出異常
			
	#if _pool is None:
	#	raise HTTPException(status_code=500, detail="Database connection pool is not available.")

	#使用with context manager，當結束時自動關閉連線
	#async with _pool.connection() as conn:
		#使用yeild generator傳回連線物件
	#	yield conn
    

# ===============================
# FastAPI Dependency
# ===============================
async def getDB() -> AsyncGenerator:
    """
    FastAPI 使用：
    async def api(db = Depends(getDB)):
        await db.execute(...)
    """
    if _pool is None:
        raise HTTPException(
            status_code=500,
            detail="Database pool not initialized"
        )

    async with _pool.connection() as conn:
        yield conn