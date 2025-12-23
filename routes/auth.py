from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式

# --- 1. 設定 Router 與樣板 ---
router = APIRouter()
templates = Jinja2Templates(directory="templates")

# --- 2. 核心依賴函式：取得當前登入者 ---
# 這是一個 "Dependency"，會在其他路由執行前先跑過一遍
async def get_current_user(request: Request, conn: AsyncConnectionPool = Depends(getDB)):
    """
    檢查 Session，如果使用者已登入，返回使用者的資料 (dict)。
    如果未登入，返回 None。
    
    運作原理：
    1. 瀏覽器發送請求時會帶上 Cookie (Session ID)。
    2. 伺服器解密 Cookie 取得 "user_id"。
    3. 用這個 ID 去資料庫查是不是真的有這個人。
    """
    # 嘗試從 Session 取得 user_id
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    
    try:
        user_id = int(user_id)
    except ValueError:
        request.session.clear() # 如果 Session 資料怪怪的 (不是數字)，為了安全就清掉
        return None
        
    async with conn.cursor() as cur:
        # 去資料庫撈使用者資料 (只撈需要的欄位)
        await cur.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
        user = await cur.fetchone()
        
    if not user:
        # 如果 Session 有紀錄 ID，但資料庫找不到人 (可能被刪除帳號了)
        # 那就清除 Session，強制登出
        request.session.clear()
        return None
        
    return user # user 是一個 dict, e.g., {'id': 1, 'username': 'test', 'role': 'client'}

# --- 3. 註冊功能 ---

# 顯示註冊頁面 (GET)
@router.get("/register", response_class=HTMLResponse)
async def get_register_page(request: Request, user: dict | None = Depends(get_current_user)):
    """
    顯示註冊表單。
    如果使用者已經登入 (user 有值)，就不用註冊了，直接踢回首頁。
    """
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    return templates.TemplateResponse("register.html", {"request": request})

# 處理註冊表單提交 (POST)
@router.post("/register")
async def handle_registration(
    request: Request,
    username: str = Form(...), # Form(...) 表示這些資料來自 HTML 表單
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    接收使用者填寫的資料，檢查並寫入資料庫。
    """
    # 步驟 1: 檢查重複 (防止同名或同信箱註冊)
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id FROM users WHERE username = %s OR email = %s", 
            (username, email)
        )
        existing_user = await cur.fetchone()

    if existing_user:
        # 如果重複，回傳 HTML 並顯示錯誤訊息
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "使用者名稱或 Email 已經被註冊。"
        }, status_code=400)

    # 步驟 2: 檢查角色是否合法 (防止惡意修改 HTML 傳送奇怪的角色)
    if role not in ['client', 'contractor']:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "無效的角色。"
        }, status_code=400)

    # 步驟 3: 寫入資料庫
    # 注意：專案範例為了簡單，密碼是明碼儲存。
    # 在正式產品中，這裡必須使用 bcrypt 或 argon2 進行雜湊 (Hash) 加密！
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO users (username, email, hashed_password, role)
                VALUES (%s, %s, %s, %s)
                """,
                (username, email, password, role) 
            )
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": f"資料庫錯誤: {e}"
        }, status_code=500)

    # 註冊成功，導向登入頁面，並帶上參數讓登入頁顯示「註冊成功」訊息
    return RedirectResponse(url="/login?registered=true", status_code=status.HTTP_303_SEE_OTHER)


# --- 4. 登入功能 ---

# 顯示登入頁面 (GET)
@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request, registered: bool = False, user: dict | None = Depends(get_current_user)):
    # 如果已登入，踢回首頁
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    context = {"request": request}
    if registered:
        context["message"] = "註冊成功！請登入。"
        
    return templates.TemplateResponse("login.html", context)

# 處理登入表單 (POST)
@router.post("/login")
async def handle_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    驗證帳號密碼，成功則建立 Session。
    """
    # 步驟 1: 去資料庫找這個使用者
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id, username, hashed_password, role FROM users WHERE username = %s", 
            (username,)
        )
        user = await cur.fetchone()

    # 步驟 2: 驗證密碼
    # 如果 user 不存在 OR 密碼不對
    if not user or user["hashed_password"] != password:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "無效的使用者名稱或密碼。"
        }, status_code=401)
    
    # 步驟 3: 登入成功，設定 Session
    # 這行程式碼執行後，FastAPI 會自動幫我們把加密後的 Cookie 塞給瀏覽器
    request.session["user_id"] = user["id"]
    
    # 導向首頁 (main.py 的 root 函式會負責再把你導向對應的儀表板)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# --- 5. 登出功能 ---
@router.get("/logout")
async def handle_logout(request: Request):
    """
    清除 session 並導向首頁
    """
    request.session.clear() # 把 Server 端認得這個人的 Session 清掉
    return RedirectResponse(url="/")


# --- 6. 權限控管依賴函式 (重要！) ---
# 這些函式用來保護特定路由，例如只有 "委託人" 才能建立專案

# [委託人 Client] 專用權限檢查
async def get_current_client_user(
    request: Request, 
    user: dict | None = Depends(get_current_user)
) -> dict:
    """
    檢查：
    1. 是否已登入 (user is not None)
    2. 角色是否為 'client'
    """
    if user is None:
        # 沒登入 -> 踢去登入頁
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    if user["role"] != "client":
        # 有登入但角色不對 -> 403 禁止訪問 (例如接案人想偷看發案頁面)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not a client",
        )
    return user # 通過檢查，回傳 user

# [接案人 Contractor] 專用權限檢查
async def get_current_contractor_user(
    request: Request, 
    user: dict | None = Depends(get_current_user)
) -> dict:
    """
    檢查：
    1. 是否已登入
    2. 角色是否為 'contractor'
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    if user["role"] != "contractor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not a contractor",
        )
    return user