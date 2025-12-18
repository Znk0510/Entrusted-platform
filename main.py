from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager # 導入 asynccontextmanager
from db import getDB, DATABASE_CONNINFO, init_pool, close_pool # 資料庫連線函式
import os
import asyncio
from datetime import datetime, timedelta
from init_db import ensure_database_exists, initialize_database
import uvicorn

# 匯入初始化函式
#from init_db import init_database
# 每次啟動時，都會自動確保資料表存在
#init_database()

# 應用程式設定
#app = FastAPI()

# 掛載靜態檔案目錄
#app.mount("/static", StaticFiles(directory="static"), name="static")

# 設定 Jinja2 模板
#templates = Jinja2Templates(directory="templates")

# 設定 Session 中間件
#app.add_middleware(
  ## secret_key=os.getenv("SECRET_KEY", "a_very_secret_key_please_change_me"), # 強烈建議使用環境變數
  #  max_age=86400,  # 1 day
   # same_site="lax",
   # https_only=False, # 在生產環境中應設為 True
#)


# ---------------------------------------------
# A. 應用程式生命週期管理 (使用 lifespan)
# ---------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 App starting...")
        
    await ensure_database_exists()
    # 3️⃣ 再建資料表
    await initialize_database()
    # 2️⃣ 再初始化 pool（連到新 database）
    await init_pool()

    print("✅ Database ready")
    yield

    print("🛑 Shutting down...")
    await close_pool()

# 應用程式設定，並連結 lifespan
# ---------------------------------------------------------
# B. 建立 FastAPI 實例
# ---------------------------------------------------------
app = FastAPI(lifespan=lifespan)

# ---------------------------------------------
# C. 靜態/模板/Session 設定 (保持不變)
# ---------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "a_very_secret_key_please_change_me"),
    max_age=86400,
    same_site="lax",
    https_only=False,
)


# D.路由
from init_db import initialize_database
from routes.auth import router as auth_router, get_current_user
from routes.client import router as client_router
from routes.contractor import router as contractor_router
from routes.rating import router as rating_router
app.include_router(auth_router)
app.include_router(client_router, prefix="/client")
app.include_router(contractor_router, prefix="/contractor")
app.include_router(rating_router) # 💡 新增：註冊評價路由
# app.include_router(upload_router, prefix="/api") # 你的 upload router


# E.首頁
@app.get("/")
async def root(request: Request, user: dict | None = Depends(get_current_user)):
    """
    首頁
    - 已登入，根據角色導向不同的儀表板
    - 未登入，顯示歡迎頁面 或 導向登入頁
    """
    if user:
        if user["role"] == "client":
            # 導向委託人
            return RedirectResponse(url="/client/dashboard", status_code=302)
        elif user["role"] == "contractor":
            # 導向接案人
            return RedirectResponse(url="/contractor/dashboard", status_code=302)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user # 將 user 物件傳給模板 (可以是 None)
    })



# --- F. 應用程式主啟動流程 ---
# 這是你應用程式的入口點，確保在其他函式使用資料庫之前運行 initialize_database。
#async def main():
    # 1. 執行初始化：如果成功，才繼續下一步
 #   success = await initialize_database(DATABASE_CONNINFO)
  #  if not success:
   #     return 
    
    # 2. 建立連線池供整個應用程式使用
   # global db_pool # 如果你需要在其他地方使用這個 pool
   # db_pool = AsyncConnectionPool(DATABASE_CONNINFO)
   # await db_pool.open()
   # print("系統連線池已開啟，應用程式開始運行...")

    # ... 其他啟動程式碼 (例如：啟動 Web Server) ...

    # 結束時記得關閉連線池
   # await db_pool.close()
#if __name__ == "__main__":
#    asyncio.run(main())
    
# ---------------------------------------------
# F. 應用程式主啟動流程 (修改 async def main)
# ---------------------------------------------
# 💡 修正：移除手動的連線池創建和關閉，因為 lifespan 已經處理了這些。
async def main():
    """
    應用程式主入口點。現在只負責啟動 Uvicorn Web Server。
    資料庫初始化和連線池管理已委託給 app.lifespan。
    """

    print("正在啟動 Web 服務...")
    # Uvicorn 將會使用 app.lifespan 來處理資料庫的啟動和關閉
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # 這裡直接運行 main 函數
    print(f"PostgreSQL 連線目標: {DATABASE_CONNINFO}") 
    asyncio.run(main())