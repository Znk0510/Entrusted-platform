from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式
from routes.auth import get_current_client_user # 導入建立的保護函式

 
templates = Jinja2Templates(directory="templates")
# 設定
router = APIRouter()

# 委託人儀表板
@router.get("/dashboard", response_class=HTMLResponse)
async def get_client_dashboard(
    request: Request, 
    user: dict = Depends(get_current_client_user), # 保護路由
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    顯示委託人的主儀表板
    顯示 歷史專案列表
    """
    projects = []
    async with conn.cursor() as cur:
        # 查詢這個委託人建立的所有專案，並按狀態和日期排序
        await cur.execute(
            """
            SELECT id, title, description, status, created_at
            FROM projects
            WHERE client_id = %s
            ORDER BY 
                CASE status
                    WHEN 'pending_approval' THEN 1
                    WHEN 'open' THEN 2
                    WHEN 'in_progress' THEN 3
                    WHEN 'rejected' THEN 4
                    WHEN 'completed' THEN 5
                END,
                created_at DESC
            """,
            (user["id"],)
        )
        projects = await cur.fetchall()

    return templates.TemplateResponse("dashboard_client.html", {
        "request": request,
        "user": user,
        "projects": projects # 將查詢到的專案傳給 HTML
    })

# 建立新專案
@router.get("/create_project", response_class=HTMLResponse)
async def get_create_project_page(
    request: Request, 
    user: dict = Depends(get_current_client_user) # 保護
):
    """
    顯示「建立新專案」的表單頁面
    """
    return templates.TemplateResponse("create_project.html", {
        "request": request,
        "user": user
    })

@router.post("/create_project")
async def handle_create_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    處理「建立新專案」的表單提交
    """
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO projects (title, description, client_id, status)
                VALUES (%s, %s, %s, 'open')
                """,
                (title, description, user["id"])
            )
        # 建立成功後，導向儀表板
        return RedirectResponse(url="/client/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return templates.TemplateResponse("create_project.html", {
            "request": request,
            "user": user,
            "error": f"建立專案失敗: {e}"
        })

# 顯示「編輯專案」頁面
@router.get("/project/{project_id}/edit", response_class=HTMLResponse)
async def get_edit_project_page(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    顯示「編輯專案」的表單頁面
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT * FROM projects WHERE id = %s AND client_id = %s",
            (project_id, user["id"])
        )
        project = await cur.fetchone()
        
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 只有 'open' 狀態的專案可以被編輯
    if project["status"] != 'open':
        redirect_url = f"/client/project/{project_id}?error=Only+'open'+projects+can+be+edited."
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
        
    return templates.TemplateResponse("edit_project.html", {
        "request": request,
        "user": user,
        "project": project
    })

# 處理「編輯專案」提交 
@router.post("/project/{project_id}/edit")
async def handle_edit_project(
    request: Request,
    project_id: int,
    title: str = Form(...),
    description: str = Form(...),
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    處理「編輯專案」的表單提交
    """
    try:
        async with conn.cursor() as cur:
            # 更新專案，但要再次確認是本人且狀態為 'open'
            await cur.execute(
                """
                UPDATE projects
                SET title = %s, description = %s
                WHERE id = %s AND client_id = %s AND status = 'open'
                """,
                (title, description, project_id, user["id"])
            )
            
            if cur.rowcount == 0:
                # 如果 rowcount 為 0，代表專案不存在、不是 'open' 狀態或非本人
                raise HTTPException(status_code=403, detail="Cannot update project.")
                
    except Exception as e:
        # 如果更新失敗，重新顯示編輯頁面並帶上錯誤
        temp_project_data = {"id": project_id, "title": title, "description": description}
        return templates.TemplateResponse("edit_project.html", {
            "request": request,
            "user": user,
            "project": temp_project_data,
            "error": f"Failed to update project: {e}"
        })
    
    # 成功後，導向回專案詳情頁，並帶上成功訊息
    redirect_url = f"/client/project/{project_id}?message=Project+updated+successfully."
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)


# 專案詳情 & 選擇委託對象
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_project_details(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    顯示單一專案的詳細資訊
    - 專案基本資料
    - 收到的所有提案 (用於「選擇委託對象」)
    - 專案提交的檔案 (用於「結案管理」)
    """
    project = None
    proposals = []
    files = []
    
    async with conn.cursor() as cur:
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
            # 如果專案不存在，或使用者不是擁有者，拋出 404
            raise HTTPException(status_code=404, detail="Project not found")

        # 取得所有針對此專案的提案，並 JOIN user 資料表取得接案人名稱
        await cur.execute(
            """
            SELECT p.id, p.quote, p.message, p.submitted_at, u.username AS contractor_name
            FROM proposals p
            JOIN users u ON p.contractor_id = u.id
            WHERE p.project_id = %s
            ORDER BY p.quote ASC
            """,
            (project_id,)
        )
        proposals = await cur.fetchall()

        # 取得所有提交的結案檔案
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

        # 取得 Issue Tracker 資料
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

        # 為了顯示方便，把每個 Issue 的 comments 也抓出來
        for issue in issues_data:
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
        
        # ⭐ 評價相關（委託人 → 接案人）
        can_rate = False
        already_rated = False
        contractor = None

        if project["status"] == "completed":
            # 專案的接案人
            await cur.execute(
                "SELECT id, username FROM users WHERE id = %s",
                (project["contractor_id"],)
            )
            contractor = await cur.fetchone()

            # 是否已評價
            await cur.execute(
                """
                SELECT 1 FROM ratings
                WHERE project_id = %s
                AND rater_id = %s
                AND ratee_id = %s
                """,
                (project_id, user["id"], project["contractor_id"])
            )
            already_rated = await cur.fetchone() is not None

            can_rate = contractor is not None and not already_rated


    return templates.TemplateResponse("project_detail_client.html", {
        "request": request,
        "user": user,
        "project": project,
        "proposals": proposals,
        "files": files,
        "issues": issues,
        "message": request.query_params.get("message", None), # 用於顯示成功/失敗訊息
        "error": request.query_params.get("error", None), # 用於顯示 "無法編輯" 訊息
        "request": request,
        "user": user,
        "project": project,

        # ⭐ 評價
        "can_rate": can_rate,
        "already_rated": already_rated,
        "contractor": contractor,
    })

# 選擇委託對象
@router.post("/select_proposal/{project_id}/{proposal_id}")
async def select_proposal(
    request: Request,
    project_id: int,
    proposal_id: int,
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    執行「選擇委託對象」
    """
    async with conn.cursor() as cur:
        # 先從提案中找出接案人的 ID
        await cur.execute("SELECT contractor_id FROM proposals WHERE id = %s", (proposal_id,))
        proposal = await cur.fetchone()
        
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")
        
        contractor_id = proposal["contractor_id"]

        # 更新專案狀態，並綁定接案人 ID
        # 同時要確保這個專案是屬於這個委託人的
        await cur.execute(
            """
            UPDATE projects
            SET contractor_id = %s, status = 'in_progress'
            WHERE id = %s AND client_id = %s AND status = 'open'
            """,
            (contractor_id, project_id, user["id"])
        )
    
    # 重新導向回專案詳情頁，並帶上成功訊息
    redirect_url = f"/client/project/{project_id}?message=Contractor+selected+successfully"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# 結案管理
@router.post("/manage_case/{project_id}")
async def manage_case(
    request: Request,
    project_id: int,
    action: str = Form(...), # 表單會傳來 'accept' 或 'reject'
    user: dict = Depends(get_current_client_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    執行「結案管理」(接受結案 / 退件)
    """
    new_status = ""
    if action == "accept":
        new_status = "completed"
    elif action == "reject":
        new_status = "rejected" # 退件
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    async with conn.cursor() as cur:
        # 如果是要結案，必須檢查是否還有 open 的 issues
        if new_status == "completed":
            await cur.execute(
                "SELECT COUNT(*) as count FROM project_issues WHERE project_id = %s AND status = 'open'",
                (project_id,)
            )
            issue_count = await cur.fetchone()
            if issue_count["count"] > 0:
                # 如果還有未解決的問題，禁止結案
                redirect_url = f"/client/project/{project_id}?error=Cannot+complete+project.+Please+resolve+all+issues+first."
                return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
        
        # 確保只有在 'pending_approval' (等待驗收) 狀態下才能執行
        await cur.execute(
            """
            UPDATE projects
            SET status = %s
            WHERE id = %s AND client_id = %s AND status = 'pending_approval'
            """,
            (new_status, project_id, user["id"])
        )
    
    message = "Case+accepted+and+project+completed." if new_status == "completed" else "Case+rejected.+Waiting+for+resubmission."
    redirect_url = f"/client/project/{project_id}?message={message}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

# 建立新 Issue
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
        # 驗證專案權限
        await cur.execute("SELECT id FROM projects WHERE id = %s AND client_id = %s", (project_id, user["id"]))
        if not await cur.fetchone():
            raise HTTPException(status_code=403, detail="Access denied")

        await cur.execute(
            "INSERT INTO project_issues (project_id, creator_id, title, description, status) VALUES (%s, %s, %s, %s, 'open')",
            (project_id, user["id"], title, description)
        )
    return RedirectResponse(url=f"/client/project/{project_id}?message=Issue+created", status_code=status.HTTP_303_SEE_OTHER)

# 回覆/留言 Issue
@router.post("/issue/{issue_id}/comment")
async def client_comment_issue(
    request: Request,
    issue_id: int,
    message: str = Form(...),
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 找出這個 issue 屬於哪個專案，並確認該專案屬於這個 client
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
            
        await cur.execute(
            "INSERT INTO issue_comments (issue_id, user_id, message) VALUES (%s, %s, %s)",
            (issue_id, user["id"], message)
        )
        
    return RedirectResponse(url=f"/client/project/{project['id']}?message=Comment+added", status_code=status.HTTP_303_SEE_OTHER)

# 解決 Issue
@router.post("/issue/{issue_id}/resolve")
async def resolve_issue(
    request: Request,
    issue_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 驗證權限並更新
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

    return RedirectResponse(url=f"/client/project/{project_id}?message=Issue+marked+as+resolved", status_code=status.HTTP_303_SEE_OTHER)