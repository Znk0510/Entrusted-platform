from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式

# 設定
router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 依賴函式
async def get_current_user( request: Request, conn = Depends(getDB)):
    """
    檢查 session，如果使用者已登入，返回使用者的資料。
    如果未登入，返回 None。
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    
    try:
        user_id = int(user_id)
    except ValueError:
        request.session.clear() # Session 資料損毀
        return None
        
    async with conn.cursor() as cur:
        await cur.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
        user = await cur.fetchone()
        
    if not user:
        # 找不到使用者，但 session 還在，清除它
        request.session.clear()
        return None
        
    return user # user 是一個 dict, e.g., {'id': 1, 'username': 'test', ...}

# 註冊
@router.get("/register", response_class=HTMLResponse)
async def get_register_page(request: Request, user: dict | None = Depends(get_current_user)):
    """
    顯示註冊頁面。
    如果使用者已經登入，就導向首頁。
    """
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def handle_registration(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    處理註冊表單提交
    """
    # 檢查使用者或Email是否已被註冊
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id FROM users WHERE username = %s OR email = %s", 
            (username, email)
        )
        existing_user = await cur.fetchone()

    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "使用者名稱或 Email 已經被註冊。"
        }, status_code=400)

    if role not in ['client', 'contractor']:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "無效的角色。"
        }, status_code=400)

    # 將新使用者存入資料庫
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

    # 註冊成功，導向登入頁面
    return RedirectResponse(url="/login?registered=true", status_code=status.HTTP_303_SEE_OTHER)


# 登入
@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request, registered: bool = False, user: dict | None = Depends(get_current_user)):
    """
    顯示登入頁面。
    """
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        
    context = {"request": request}
    if registered:
        context["message"] = "註冊成功！請登入。"
        
    return templates.TemplateResponse("login.html", context)


@router.post("/login")
async def handle_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    處理登入表單提交
    """
    # 從資料庫中找出使用者
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id, username, hashed_password, role FROM users WHERE username = %s", 
            (username,)
        )
        user = await cur.fetchone()

    # 驗證
    # 直接比對表單送來的 'password' 和資料庫中的 'hashed_password'
    if not user or user["hashed_password"] != password:
        # 驗證失敗
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "無效的使用者名稱或密碼。"
        }, status_code=401)
    
    # 驗證成功，將使用者 ID 存入 Session
    request.session["user_id"] = user["id"]
    
    # 導向首頁
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# 登出
@router.get("/logout")
async def handle_logout(request: Request):
    """
    清除 session 並導向首頁
    """
    request.session.clear()
    return RedirectResponse(url="/")

# 角色驗證依賴函式
# 委託人
async def get_current_client_user(
    request: Request, 
    user: dict | None = Depends(get_current_user)
) -> dict:
    """
    這是一個新的依賴函式。
    它會檢查使用者是否已登入 "且" 角色是否為 'client'。
    如果不是，它會自動將使用者踢到登入頁面。
    我們將在 client.py 的所有路由中使用它。
    """
    if user is None:
        # 如果未登入，導向登入頁面
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    if user["role"] != "client":
        # 如果不是委託人 (例如是接案人)，拋出 403 Forbidden 錯誤
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not a client",
        )
    return user # 如果一切正常，返回使用者資料

# 接案人
async def get_current_contractor_user(
    request: Request, 
    user: dict | None = Depends(get_current_user)
) -> dict:
    """
    這是一個新的依賴函式。
    它會檢查使用者是否已登入 "且" 角色是否為 'contractor'。
    如果不是，它會自動將使用者踢到登入頁面。
    """
    if user is None:
        # 如果未登入，導向登入頁面
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    if user["role"] != "contractor":
        # 如果不是接案人 (例如是委託人)，拋出 403 Forbidden 錯誤
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not a contractor",
        )
    return user # 如果一切正常，返回使用者資料