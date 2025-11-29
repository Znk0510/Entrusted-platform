from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式
import os

# 匯入初始化函式
from init_db import init_database
# 每次啟動時，都會自動確保資料表存在
init_database()

# 應用程式設定
app = FastAPI()

# 掛載靜態檔案目錄
app.mount("/static", StaticFiles(directory="static"), name="static")

# 設定 Jinja2 模板
templates = Jinja2Templates(directory="templates")

# 設定 Session 中間件
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "a_very_secret_key_please_change_me"), # 強烈建議使用環境變數
    max_age=86400,  # 1 day
    same_site="lax",
    https_only=False, # 在生產環境中應設為 True
)

# 路由
from routes.auth import router as auth_router, get_current_user
from routes.client import router as client_router
from routes.contractor import router as contractor_router
app.include_router(auth_router)
app.include_router(client_router, prefix="/client")
app.include_router(contractor_router, prefix="/contractor")
# app.include_router(upload_router, prefix="/api") # 你的 upload router

# 首頁
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