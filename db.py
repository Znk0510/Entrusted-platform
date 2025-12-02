from psycopg_pool import AsyncConnectionPool #使用connection pool
from psycopg.rows import dict_row

# db.py
defaultDB = "work_platform"
dbUser = "postgres"
dbPassword = "ux7e4ywp"
dbHost = "localhost"
dbPort = 5432

DATABASE_URL = f"dbname={defaultDB} user={dbUser} password={dbPassword} host={dbHost} port={dbPort}"

#宣告變數，預設為None
_pool: AsyncConnectionPool | None = None

#取得DB連線物件
async def getDB():
	global _pool
	if _pool is None:
		#lazy create, 等到main.py來呼叫時再啟用 _pool
		print("Initializing Connection Pool...")
		_pool = AsyncConnectionPool(
			conninfo=DATABASE_URL,
			kwargs={"row_factory": dict_row}, #設定查詢結果以dictionary方式回傳
			open=False #不直接開啟
		)
		try:
			await _pool.open() #等待開啟完成
			print("Connection Pool Opened.")
		except Exception as e:
			print(f"Failed to open connection pool: {e}")
			_pool = None # 如果開啟失敗，重設為 None
			raise # 拋出異常
			
	if _pool is None:
		raise HTTPException(status_code=500, detail="Database connection pool is not available.")

	#使用with context manager，當結束時自動關閉連線
	async with _pool.connection() as conn:
		#使用yeild generator傳回連線物件
		yield conn