from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from psycopg_pool import AsyncConnectionPool
from db import getDB # 匯入資料庫連線依賴函式
import os

# --- 1. 資料庫初始化 ---
from init_db import init_database

# 每次伺服器啟動時，自動執行此函式來檢查並建立資料表
# 這樣就不用手動去資料庫下 SQL 指令
init_database()

# --- 2. 建立應用程式 ---
app = FastAPI()

# --- 3. 掛載靜態檔案 ---
# 讓瀏覽器可以讀取 CSS, JS, 圖片等靜態資源
# 例如：HTML 裡的 <link href="/static/style.css"> 會對應到專案的 static 資料夾
app.mount("/static", StaticFiles(directory="static"), name="static")

# 掛載上傳檔案目錄
# 讓使用者上傳的頭像或檔案可以透過 URL 被讀取
# 例如：<img src="/uploads/avatars/..."> 會對應到 uploads 資料夾
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- 4. 設定樣板引擎 ---
# 指定 HTML 檔案都放在 "templates" 資料夾內
# Jinja2 讓我們可以在 HTML 裡面寫變數，例如 {{ user.username }}
templates = Jinja2Templates(directory="templates")

# --- 5. 設定 Session (登入狀態管理) ---
# Session 用來像餅乾(Cookie)一樣記住使用者的登入狀態
app.add_middleware(
    SessionMiddleware,
    # SECRET_KEY 是加密用的鑰匙，正式上線時建議改用環境變數讀取
    secret_key=os.getenv("SECRET_KEY", "a_very_secret_key_please_change_me"), 
    max_age=86400,  # 登入狀態維持 1 天 (86400秒)
    same_site="lax", # 防止 CSRF 攻擊的設定
    https_only=False, # 本地開發設為 False，正式上線有 HTTPS 時應設為 True
)

# --- 6. 匯入各個功能的路由 (Router) ---
# 我們把不同功能拆到不同檔案，避免 main.py 太長
from routes.auth import router as auth_router, get_current_user
from routes.client import router as client_router
from routes.contractor import router as contractor_router
from routes.users import router as users_router # 使用者個人檔案與評價功能
from routes.support import router as support_router # 客服頁面
from routes.ai import router as ai_router # AI 小助手功能

# --- 7. 註冊路由到主程式 ---
# prefix 表示網址的前綴
# 例如 client_router 的功能都會在 http://網站/client/... 底下
app.include_router(auth_router) # 登入註冊 (無前綴)
app.include_router(client_router, prefix="/client")
app.include_router(contractor_router, prefix="/contractor")
app.include_router(users_router, prefix="/users")
app.include_router(support_router) # 客服 (無前綴)
app.include_router(ai_router, prefix="/api/ai") # AI API

# --- 8. 首頁路由邏輯 ---
@app.get("/")
async def root(request: Request, user: dict | None = Depends(get_current_user)):
    """
    首頁處理函式：
    這個函式是網站的「門面」，它會判斷你是誰，然後帶你去該去的地方。
    
    參數:
    - request: 用來傳給樣板，讓 HTML 知道當前的網址資訊
    - user: 透過 get_current_user 依賴函式，自動檢查是否已登入
    """
    
    # 如果使用者已經登入 (user 不是 None)
    if user:
        # 判斷角色：如果是委託人 (client)
        if user["role"] == "client":
            # 強制導向到「委託人儀表板」
            return RedirectResponse(url="/client/dashboard", status_code=302)
        # 判斷角色：如果是接案人 (contractor)
        elif user["role"] == "contractor":
            # 強制導向到「接案人儀表板」
            return RedirectResponse(url="/contractor/dashboard", status_code=302)
    
    # 如果沒登入，就顯示一般的歡迎首頁 (index.html)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user # 把 user 資訊傳給 HTML，這樣導覽列才能顯示「登入/註冊」按鈕
    })