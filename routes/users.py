from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg_pool import AsyncConnectionPool
from db import getDB
# 匯入通用的權限檢查 (不分角色，只要有登入即可)
from routes.auth import get_current_user
# 匯入儲存頭像的工具函式
from utils import save_avatar_file
from main import templates

# 設定 Router
router = APIRouter()

# =========================================================
# 1. 查看個人檔案 (公開/私人)
# =========================================================
@router.get("/profile/{user_id}", response_class=HTMLResponse)
async def view_user_profile(
    request: Request,
    user_id: int,
    # 這裡使用 get_current_user，因為不管有沒有登入，或許都能看別人的檔案 (視需求而定)
    # 但這裡的設計是：current_user 用來判斷「我是不是正在看我自己的檔案」以便顯示編輯按鈕
    current_user: dict | None = Depends(get_current_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    target_user = None
    reviews = []
    # 初始化統計數據結構
    stats = {
        "avg_rating": 0.0, # 總平均分
        "count": 0,        # 評價總數
        "dim1": 0.0,       # 維度1 (如：品質/需求合理性)
        "dim2": 0.0,       # 維度2 (如：效率/驗收難度)
        "dim3": 0.0        # 維度3 (如：態度)
    }

    async with conn.cursor() as cur:
        # A. 撈取目標使用者的基本資料
        await cur.execute(
            "SELECT id, username, email, role, avatar, introduction, created_at FROM users WHERE id = %s",
            (user_id,)
        )
        target_user = await cur.fetchone()
        
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # B. 撈取該使用者「收到」的評價 (reviewee_id = 目標用戶)
        # 同時 JOIN projects 取得專案標題，JOIN users 取得評價者(reviewer)的資訊
        await cur.execute(
            """
            SELECT r.*, u.username AS reviewer_name, u.avatar AS reviewer_avatar, p.title AS project_title
            FROM reviews r
            JOIN users u ON r.reviewer_id = u.id
            JOIN projects p ON r.project_id = p.id
            WHERE r.reviewee_id = %s
            ORDER BY r.created_at DESC
            """,
            (user_id,)
        )
        reviews = await cur.fetchall()

        # C. 計算統計數據 (算術平均數)
        if reviews:
            total_avg = sum(r["average_score"] for r in reviews)
            stats["count"] = len(reviews)
            # round(數值, 1) 表示取到小數點後第 1 位
            stats["avg_rating"] = round(total_avg / stats["count"], 1)
            
            # 分別計算三個維度的平均分
            stats["dim1"] = round(sum(r["rating_1"] for r in reviews) / stats["count"], 1)
            stats["dim2"] = round(sum(r["rating_2"] for r in reviews) / stats["count"], 1)
            stats["dim3"] = round(sum(r["rating_3"] for r in reviews) / stats["count"], 1)

    return templates.TemplateResponse("profile_view.html", {
        "request": request,
        "user": current_user,       # 當前登入者 (用來決定 Layout 右上角顯示什麼)
        "target_user": target_user, # 被查看的人 (頁面主角)
        "reviews": reviews,
        "stats": stats
    })

# =========================================================
# 2. 編輯個人檔案 (頁面)
# =========================================================
@router.get("/profile/edit/me", response_class=HTMLResponse)
async def edit_my_profile_page(
    request: Request,
    user: dict = Depends(get_current_user)
):
    # 權限檢查：必須先登入
    if not user:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse("profile_edit.html", {
        "request": request, "user": user
    })

# =========================================================
# 3. 處理編輯儲存 (POST)
# =========================================================
@router.post("/profile/edit/me")
async def handle_edit_profile(
    request: Request,
    introduction: str = Form(""),
    avatar: UploadFile = File(None), # 頭像是非必填 (None)
    user: dict = Depends(get_current_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    if not user:
         raise HTTPException(status_code=401)

    async with conn.cursor() as cur:
        # 情況 A: 使用者有上傳新圖片
        if avatar and avatar.filename:
            # 呼叫 utils.py 的函式存檔案
            avatar_path = await save_avatar_file(avatar, user["id"])
            
            # 更新資料庫：同時更新文字介紹與頭像路徑
            await cur.execute(
                "UPDATE users SET introduction = %s, avatar = %s WHERE id = %s",
                (introduction, avatar_path, user["id"])
            )
        else:
            # 情況 B: 只更新文字介紹，保留原頭像
            await cur.execute(
                "UPDATE users SET introduction = %s WHERE id = %s",
                (introduction, user["id"])
            )
            
    # 更新完成，導回個人檔案頁面
    return RedirectResponse(url=f"/users/profile/{user['id']}", status_code=303)

# =========================================================
# 4. 送出評價 (Review) - 關鍵修正版
# =========================================================
# [重要] 這裡將函式名稱從 submit_review 改為 submit_general_review
# 這是為了避免與 client.py 裡的同名函式衝突，導致權限錯誤
@router.post("/review/{project_id}")
async def submit_general_review(
    request: Request,
    project_id: int,
    rating_1: int = Form(...),
    rating_2: int = Form(...),
    rating_3: int = Form(...),
    comment: str = Form(...),
    user: dict = Depends(get_current_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    if not user:
        raise HTTPException(status_code=401)

    # A. 資料驗證：防止有人用 Postman 繞過前端檢查傳送無效分數
    if not (1 <= rating_1 <= 5) or not (1 <= rating_2 <= 5) or not (1 <= rating_3 <= 5):
        base_url = "/client" if user["role"] == "client" else "/contractor"
        return RedirectResponse(
            url=f"{base_url}/project/{project_id}?error=Invalid+Rating+Data", 
            status_code=303
        )
        
    # B. XSS 防護：清洗留言內容
    import html
    clean_comment = html.escape(comment.strip())

    # 計算本次評價的平均分
    avg_score = round((rating_1 + rating_2 + rating_3) / 3, 1)

    async with conn.cursor() as cur:
        # 查詢專案資訊
        await cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        project = await cur.fetchone()
        
        # 狀態檢查：必須是已結案 (completed) 才能評價
        if not project or project["status"] != 'completed':
            raise HTTPException(status_code=400, detail="只能評論已結案的專案")

        # C. 自動判斷角色：到底是「誰評誰」？
        # 如果我是發案人 -> 評接案人
        if user["id"] == project["client_id"]:
            reviewee_id = project["contractor_id"]
            target_role = 'contractor'
        # 如果我是接案人 -> 評發案人
        elif user["id"] == project["contractor_id"]:
            reviewee_id = project["client_id"]
            target_role = 'client'
        else:
            # 如果我根本不是這個專案的成員 -> 滾出去
            raise HTTPException(status_code=403, detail="您不是此專案的成員")

        # D. 寫入評價
        try:
            await cur.execute(
                """
                INSERT INTO reviews 
                (project_id, reviewer_id, reviewee_id, target_role, rating_1, rating_2, rating_3, average_score, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (project_id, user["id"], reviewee_id, target_role, rating_1, rating_2, rating_3, avg_score, clean_comment)
            )
        except Exception:
            # 如果資料庫回報錯誤 (通常是違反唯一性限制，代表評過了)
             return RedirectResponse(
                url=f"/{'client' if user['role']=='client' else 'contractor'}/project/{project_id}?error=Already+Reviewed", 
                status_code=303
            )

    # 評價成功，根據角色導回對應的專案詳情頁
    base_url = "/client" if user["role"] == "client" else "/contractor"
    return RedirectResponse(url=f"{base_url}/project/{project_id}?message=Review+Submitted", status_code=303)

# =========================================================
# 5. API: 取得使用者預覽資訊 (Hover Card)
# =========================================================
@router.get("/api/preview/{target_id}")
async def get_user_preview_data(
    target_id: int,
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    這是一個回傳 JSON 的 API，給前端 JavaScript (layout.html) 使用。
    當滑鼠移到使用者連結上時，顯示小框框預覽。
    """
    async with conn.cursor() as cur:
        # 1. 查基本資料
        await cur.execute(
            "SELECT id, username, avatar, role, created_at FROM users WHERE id = %s",
            (target_id,)
        )
        user = await cur.fetchone()
        
        if not user:
            return {"error": "User not found"}
            
        # 2. 查該用戶的歷史平均評分
        await cur.execute(
            "SELECT average_score FROM reviews WHERE reviewee_id = %s",
            (target_id,)
        )
        reviews = await cur.fetchall()
        
        stats = {
            "rating": "尚無評價",
            "count": 0
        }
        
        if reviews:
            count = len(reviews)
            avg = sum(r["average_score"] for r in reviews) / count
            stats["rating"] = f"{round(avg, 1)} ⭐"
            stats["count"] = count

    # 回傳 JSON 格式
    return {
        "id": user["id"],
        "username": user["username"],
        "avatar": f"/{user['avatar']}" if user["avatar"] else None, # 補上斜線確保路徑正確
        "role": user["role"],
        "stats": stats
    }