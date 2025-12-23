from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from psycopg_pool import AsyncConnectionPool
from db import getDB 
# 匯入我們在 auth.py 寫好的權限檢查函式
# 這非常重要！確保只有「委託人」身分才能呼叫這裡的 API
from routes.auth import get_current_client_user 
from datetime import datetime
from main import templates 
from utils import save_upload_file, FOLDER_PROPOSALS, FOLDER_DELIVERABLES
import os
import urllib.parse

# 設定 Router
router = APIRouter()

# =========================================================
# 第一部分：儀表板與專案建立
# =========================================================

# 1. 委託人儀表板
@router.get("/dashboard", response_class=HTMLResponse)
async def get_client_dashboard(
    request: Request, 
    # 使用 Dependency Injection (依賴注入)
    # FastAPI 會自動執行 get_current_client_user，如果沒登入或身分不對，會直接被擋下來
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    顯示委託人的主控台，列出所有專案狀態。
    """
    # 取得網址上的參數 ?status=... (預設為 open)
    status_param = request.query_params.get("status", "open")

    projects = []
    all_projects = []

    async with conn.cursor() as cur:
        # 步驟 A: 查詢該使用者 (client_id = user["id"]) 的所有專案
        # 這裡撈出所有欄位，包含預算 (budget) 和截止日
        await cur.execute(
            """
            SELECT id, title, description, status, created_at, deadline, budget
            FROM projects
            WHERE client_id = %s
            ORDER BY created_at DESC
            """,
            (user["id"],)
        )
        all_projects = await cur.fetchall()

        # 步驟 B: 幫每個專案補上「目前收到幾個提案」的統計數字
        # 這會顯示在列表卡片上，讓委託人知道哪個案子很熱門
        for p in all_projects:
            await cur.execute("SELECT COUNT(*) as count FROM proposals WHERE project_id = %s", (p["id"],))
            res = await cur.fetchone()
            p["proposal_count"] = res["count"]

    # 步驟 C: 根據前端傳來的 status 參數進行篩選 (Python 端過濾)
    # 如果選 'all' 就顯示全部，否則只顯示對應狀態
    if status_param == 'all':
        projects = all_projects
    else:
        projects = [p for p in all_projects if p["status"] == status_param]

    return templates.TemplateResponse("dashboard_client.html", {
        "request": request,
        "user": user,
        "all_projects": all_projects, # 傳全部專案給前端做統計數字 (左上角的數字)
        "projects": projects,         # 傳篩選後的專案給列表顯示
        "current_filter": status_param
    })

# 2. 顯示「建立新專案」頁面 (GET)
@router.get("/create_project", response_class=HTMLResponse)
async def get_create_project_page(
    request: Request, 
    user: dict = Depends(get_current_client_user)
):
    return templates.TemplateResponse("create_project.html", {
        "request": request,
        "user": user
    })

# 3. 處理「建立新專案」表單提交 (POST)
@router.post("/create_project")
async def handle_create_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...), 
    budget: str = Form(...), 
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    # 資料驗證：將前端傳來的日期字串轉為 Python datetime 物件
    try:
        deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
    except ValueError:
        return templates.TemplateResponse("create_project.html", {
            "request": request, "user": user, "error": "日期格式錯誤"
        })

    # 寫入資料庫
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO projects (client_id, title, description, deadline, status, budget)
            VALUES (%s, %s, %s, %s, 'open', %s)
            RETURNING id
            """,
            (user["id"], title, description, deadline_dt, budget)
        )
    
    # 建立成功後，導回儀表板
    return RedirectResponse(url="/client/dashboard", status_code=303)


# =========================================================
# 第二部分：專案詳情與編輯
# =========================================================

# 4. 顯示專案詳情頁 (這頁最複雜，要撈很多資料)
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_project_details(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    project = None
    proposals = []
    files = []
    my_review = None
    
    async with conn.cursor() as cur:
        # A. 撈專案本體 (並 Join 查出接案人的名字 contractor_name)
        # 注意 WHERE 條件：必需是這個 client 自己的專案，防止偷看別人的
        await cur.execute(
            """
            SELECT p.*, u.username AS contractor_name
            FROM projects p
            LEFT JOIN users u ON p.contractor_id = u.id
            WHERE p.id = %s AND p.client_id = %s
            """, 
            (project_id, user["id"])
        )
        project = await cur.fetchone()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # B. 撈提案列表 (Proposals) - 只有在 status='open' 時最重要
        # 按報價由低到高排序
        await cur.execute(
            """
            SELECT p.id, p.contractor_id, p.quote, p.message, p.created_at AS submitted_at, p.proposal_file, u.username AS contractor_name
            FROM proposals p
            JOIN users u ON p.contractor_id = u.id
            WHERE p.project_id = %s
            ORDER BY p.quote ASC
            """,
            (project_id,)
        )
        proposals = await cur.fetchall()

        # C. 撈檔案列表 (Files) - 接案人上傳的交付檔案
        await cur.execute(
            """
            SELECT f.id, f.filename, f.filepath, f.uploaded_at, u.username AS uploader_name
            FROM project_files f
            JOIN users u ON f.uploader_id = u.id
            WHERE f.project_id = %s
            ORDER BY f.uploaded_at DESC
            """,
            (project_id,)
        )
        files = await cur.fetchall()

        # D. 撈 Issue (問題追蹤) 與 留言 (Comments)
        # 這是巢狀結構：先撈 Issue -> 再撈每個 Issue 底下的 Comments
        issues = []
        await cur.execute(
            """
            SELECT i.*, u.username AS creator_name
            FROM project_issues i
            JOIN users u ON i.creator_id = u.id
            WHERE i.project_id = %s
            ORDER BY i.created_at DESC
            """,
            (project_id,)
        )
        issues_data = await cur.fetchall()

        for issue in issues_data:
            # 撈該 Issue 的所有留言
            await cur.execute(
                """
                SELECT c.*, u.username, u.role
                FROM issue_comments c
                JOIN users u ON c.user_id = u.id
                WHERE c.issue_id = %s
                ORDER BY c.created_at ASC
                """,
                (issue["id"],)
            )
            issue["comments"] = await cur.fetchall()
            issues.append(issue)

        # E. 檢查評價狀態
        # 如果已經結案，檢查我(client)是否已經給過評價
        if project["status"] == 'completed':
            await cur.execute(
                "SELECT * FROM reviews WHERE project_id = %s AND reviewer_id = %s",
                (project_id, user["id"])
            )
            my_review = await cur.fetchone()

    return templates.TemplateResponse("project_detail_client.html", {
        "request": request,
        "user": user,
        "project": project,
        "proposals": proposals,
        "files": files,
        "issues": issues,
        "my_review": my_review,
        # 接收 URL 上的 ?message=... 或 ?error=... 顯示提示訊息
        "message": request.query_params.get("message", None),
        "error": request.query_params.get("error", None)
    })

# 5. 編輯專案 (顯示頁面)
@router.get("/project/{project_id}/edit", response_class=HTMLResponse)
async def get_edit_project_page(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT * FROM projects WHERE id = %s AND client_id = %s",
            (project_id, user["id"])
        )
        project = await cur.fetchone()
        
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # 防呆：只有在 'open' 狀態下才能編輯，一旦有人接案就不准改了
    if project["status"] != 'open':
         return RedirectResponse(url=f"/client/project/{project_id}?error=Cannot+edit+project", status_code=303)

    return templates.TemplateResponse("edit_project.html", {
        "request": request, "user": user, "project": project
    })

# 6. 編輯專案 (處理更新)
@router.post("/project/{project_id}/edit")
async def handle_edit_project(
    request: Request,
    project_id: int,
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...),
    budget: str = Form(...), 
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    try:
        deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
    except ValueError:
        return RedirectResponse(
            url=f"/client/project/{project_id}/edit?error=Invalid+date+format", 
            status_code=303
        )

    try:
        async with conn.cursor() as cur:
            # 執行 SQL Update
            # 再次加上 status='open' 條件，防止有人用 Postman 繞過前端限制
            await cur.execute(
                """
                UPDATE projects
                SET title = %s, description = %s, deadline = %s, budget = %s
                WHERE id = %s AND client_id = %s AND status = 'open'
                """,
                (title, description, deadline_dt, budget, project_id, user["id"])
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=403, detail="無法更新，專案可能已非開放狀態。")
    except Exception as e:
        print(f"Update error: {e}") 
        return RedirectResponse(url=f"/client/project/{project_id}?error=Update+failed", status_code=303)
    
    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+updated", status_code=303)


# =========================================================
# 第三部分：業務邏輯 (選人、Issue、下載、結案)
# =========================================================

# 7. 下載檔案 (安全檢查)
@router.get("/download")
async def download_file(path: str, user: dict = Depends(get_current_client_user)):
    # 防止路徑遍歷攻擊 (Path Traversal)，不允許路徑包含 ".."
    if ".." in path or not path.startswith("uploads/"):
        raise HTTPException(status_code=403, detail="Invalid file path")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)

# 8. 選擇提案 (關鍵流程：Open -> In Progress)
@router.post("/select_proposal/{project_id}/{proposal_id}")
async def select_proposal(
    request: Request, 
    project_id: int, 
    proposal_id: int, 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 先查出這個提案是誰提的 (contractor_id)
        await cur.execute("SELECT contractor_id FROM proposals WHERE id = %s", (proposal_id,))
        proposal = await cur.fetchone()
        if not proposal: 
            raise HTTPException(status_code=404, detail="Proposal not found")
        
        # 更新專案：
        # 1. 填入 contractor_id
        # 2. 狀態改為 'in_progress'
        await cur.execute(
            """
            UPDATE projects 
            SET contractor_id = %s, status = 'in_progress' 
            WHERE id = %s AND client_id = %s AND status = 'open'
            """, 
            (proposal["contractor_id"], project_id, user["id"])
        )
    return RedirectResponse(url=f"/client/project/{project_id}?message=Contractor+selected", status_code=303)

# 9. 建立 Issue (發起問題)
@router.post("/project/{project_id}/create_issue")
async def create_issue(
    request: Request, 
    project_id: int, 
    title: str = Form(...), 
    description: str = Form(...), 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 確認是自己的專案
        await cur.execute("SELECT id FROM projects WHERE id = %s AND client_id = %s", (project_id, user["id"]))
        if not await cur.fetchone(): 
            raise HTTPException(status_code=403, detail="Access denied")
            
        await cur.execute(
            "INSERT INTO project_issues (project_id, creator_id, title, description, status) VALUES (%s, %s, %s, %s, 'open')", 
            (project_id, user["id"], title, description)
        )
    return RedirectResponse(url=f"/client/project/{project_id}?message=Issue+created", status_code=status.HTTP_303_SEE_OTHER)

# 10. 回覆 Issue (留言)
@router.post("/issue/{issue_id}/comment")
async def client_comment_issue(
    request: Request, 
    issue_id: int, 
    message: str = Form(...), 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 驗證權限：確認該 Issue 屬於這個 Client 的專案
        await cur.execute(
            """
            SELECT p.id FROM project_issues i 
            JOIN projects p ON i.project_id = p.id 
            WHERE i.id = %s AND p.client_id = %s
            """, 
            (issue_id, user["id"])
        )
        project = await cur.fetchone()
        if not project: 
            raise HTTPException(status_code=403, detail="Access denied")
            
        await cur.execute("INSERT INTO issue_comments (issue_id, user_id, message) VALUES (%s, %s, %s)", (issue_id, user["id"], message))
        
    return RedirectResponse(url=f"/client/project/{project['id']}?message=Comment+added", status_code=status.HTTP_303_SEE_OTHER)

# 11. 標記 Issue 為已解決 (Resolve)
@router.post("/issue/{issue_id}/resolve")
async def resolve_issue(
    request: Request, 
    issue_id: int, 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 更新狀態為 'resolved'
        await cur.execute(
            """
            UPDATE project_issues 
            SET status = 'resolved' 
            FROM projects 
            WHERE project_issues.project_id = projects.id 
            AND project_issues.id = %s AND projects.client_id = %s 
            RETURNING projects.id
            """, 
            (issue_id, user["id"])
        )
        result = await cur.fetchone()
        if not result: 
            raise HTTPException(status_code=403, detail="Access denied or issue not found")
        project_id = result["id"]
        
    return RedirectResponse(url=f"/client/project/{project_id}?message=Issue+resolved", status_code=status.HTTP_303_SEE_OTHER)

# 12. 驗收通過 (Approve -> Completed)
@router.post("/project/{project_id}/approve")
async def approve_project(
    project_id: int, 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 防呆：如果還有未解決的 Issue (status='open')，不能結案
        await cur.execute("SELECT COUNT(*) as count FROM project_issues WHERE project_id = %s AND status = 'open'", (project_id,))
        if (await cur.fetchone())["count"] > 0: 
            return RedirectResponse(url=f"/client/project/{project_id}?error=Resolve+all+issues+first", status_code=303)
        
        # 更新狀態為 'completed'
        await cur.execute(
            """
            UPDATE projects 
            SET status = 'completed' 
            WHERE id = %s AND client_id = %s AND status = 'pending_approval' 
            RETURNING id
            """, 
            (project_id, user["id"])
        )
        if not await cur.fetchone(): 
            raise HTTPException(status_code=400, detail="Cannot complete project")
            
    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+Completed!", status_code=303)

# 13. 退件 (Reject -> Rejected)
@router.post("/project/{project_id}/reject")
async def reject_project(
    project_id: int, 
    user: dict = Depends(get_current_client_user), 
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 狀態改為 'rejected'，讓接案人知道要修改
        await cur.execute(
            """
            UPDATE projects 
            SET status = 'rejected' 
            WHERE id = %s AND client_id = %s AND status = 'pending_approval' 
            RETURNING id
            """, 
            (project_id, user["id"])
        )
        if not await cur.fetchone(): 
            raise HTTPException(status_code=400, detail="Cannot reject project")
            
    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+Rejected", status_code=303)

# 14. 提交評價 (Review)
@router.post("/project/{project_id}/review")
async def submit_review(
    request: Request,
    project_id: int,
    rating_1: int = Form(...),
    rating_2: int = Form(...),
    rating_3: int = Form(...),
    comment: str = Form(...),
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    # 資料驗證：確保分數在 1~5 之間
    if not (1 <= rating_1 <= 5) or not (1 <= rating_2 <= 5) or not (1 <= rating_3 <= 5):
        return RedirectResponse(
            url=f"/client/project/{project_id}?error=Invalid+Rating+Score+(Must+be+1-5)", 
            status_code=303
        )

    # 簡單清洗留言，防止 XSS
    import html
    clean_comment = html.escape(comment.strip())
    
    # 限制長度
    if len(clean_comment) > 1000:
         return RedirectResponse(url=f"/client/project/{project_id}?error=Comment+too+long", status_code=303)

    async with conn.cursor() as cur:
        await cur.execute("SELECT status, contractor_id, client_id FROM projects WHERE id = %s", (project_id,))
        project = await cur.fetchone()
        
        # 檢查權限與狀態
        if not project or project["client_id"] != user["id"] or project["status"] != 'completed':
            raise HTTPException(status_code=400, detail="Invalid project status or permission")
            
        avg = (rating_1 + rating_2 + rating_3) / 3.0
        
        try:
            # 寫入評價表
            await cur.execute(
                """
                INSERT INTO reviews (project_id, reviewer_id, reviewee_id, target_role, rating_1, rating_2, rating_3, average_score, comment)
                VALUES (%s, %s, %s, 'contractor', %s, %s, %s, %s, %s)
                """,
                (project_id, user["id"], project["contractor_id"], rating_1, rating_2, rating_3, avg, clean_comment)
            )
        except Exception as e:
            # 如果重複評價 (違反 Unique Constraint)
            return RedirectResponse(url=f"/client/project/{project_id}?error=Already+Reviewed", status_code=303)

    return RedirectResponse(url=f"/client/project/{project_id}?message=Review+Submitted", status_code=303)