from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式
from routes.auth import get_current_client_user # 導入建立的保護函式
from datetime import datetime
from main import templates 
from utils import save_upload_file, FOLDER_PROPOSALS, FOLDER_DELIVERABLES
import os

# 設定
router = APIRouter()

# ---------------------------------------------------------
# 1. 儀表板與專案建立
# ---------------------------------------------------------

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
        "projects": projects
    })

# 顯示建立新專案頁面
@router.get("/create_project", response_class=HTMLResponse)
async def get_create_project_page(
    request: Request, 
    user: dict = Depends(get_current_client_user)
):
    return templates.TemplateResponse("create_project.html", {
        "request": request,
        "user": user
    })

# 處理建立新專案
@router.post("/create_project")
async def handle_create_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    deadline: str = Form(...), # 接收 HTML datetime-local 字串
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    # 轉換時間格式
    try:
        # HTML datetime-local 格式通常是 "YYYY-MM-DDTHH:MM"
        deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
    except ValueError:
        return templates.TemplateResponse("create_project.html", {
            "request": request, "user": user, "error": "日期格式錯誤"
        })

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO projects (client_id, title, description, deadline, status)
            VALUES (%s, %s, %s, %s, 'open')
            RETURNING id
            """,
            (user["id"], title, description, deadline_dt)
        )
    return RedirectResponse(url="/client/dashboard", status_code=303)


# ---------------------------------------------------------
# 2. 專案詳情與編輯
# ---------------------------------------------------------

# 顯示專案詳情 (整合了提案、檔案、Issue)
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_project_details(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    顯示單一專案的詳細資訊
    """
    project = None
    proposals = []
    files = []
    
    async with conn.cursor() as cur:
        # 1. 查詢專案基本資料
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

        # 2. 取得提案 (JOIN user)
        await cur.execute(
            """
            SELECT p.id, p.quote, p.message, p.submitted_at, p.proposal_file, u.username AS contractor_name
            FROM proposals p
            JOIN users u ON p.contractor_id = u.id
            WHERE p.project_id = %s
            ORDER BY p.quote ASC
            """,
            (project_id,)
        )
        proposals = await cur.fetchall()

        # 3. 取得結案檔案
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

        # 4. 取得 Issue Tracker 資料
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

        # 補上 Issue 的 comments
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

    return templates.TemplateResponse("project_detail_client.html", {
        "request": request,
        "user": user,
        "project": project,
        "proposals": proposals,
        "files": files,
        "issues": issues,
        "message": request.query_params.get("message", None),
        "error": request.query_params.get("error", None)
    })

# 顯示編輯頁面 (補上這個路由，不然按編輯會 404)
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
        
    if project["status"] != 'open':
         return RedirectResponse(url=f"/client/project/{project_id}?error=Cannot+edit+project", status_code=303)

    return templates.TemplateResponse("edit_project.html", {
        "request": request, "user": user, "project": project
    })

# 處理編輯提交
@router.post("/project/{project_id}/edit")
async def handle_edit_project(
    request: Request,
    project_id: int,
    title: str = Form(...),
    description: str = Form(...),
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE projects
                SET title = %s, description = %s
                WHERE id = %s AND client_id = %s AND status = 'open'
                """,
                (title, description, project_id, user["id"])
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=403, detail="Cannot update project.")
    except Exception as e:
        # 簡單錯誤處理
        return RedirectResponse(url=f"/client/project/{project_id}?error=Update+failed", status_code=303)
    
    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+updated", status_code=303)


# ---------------------------------------------------------
# 3. 業務邏輯 (選人、Issue、下載、結案)
# ---------------------------------------------------------

# 選擇委託對象
@router.post("/select_proposal/{project_id}/{proposal_id}")
async def select_proposal(
    request: Request,
    project_id: int,
    proposal_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 1. 找出接案人ID
        await cur.execute("SELECT contractor_id FROM proposals WHERE id = %s", (proposal_id,))
        proposal = await cur.fetchone()
        
        if not proposal:
            raise HTTPException(status_code=404, detail="Proposal not found")
        
        contractor_id = proposal["contractor_id"]

        # 2. 更新專案
        await cur.execute(
            """
            UPDATE projects
            SET contractor_id = %s, status = 'in_progress'
            WHERE id = %s AND client_id = %s AND status = 'open'
            """,
            (contractor_id, project_id, user["id"])
        )
    
    return RedirectResponse(url=f"/client/project/{project_id}?message=Contractor+selected", status_code=303)

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

# 回覆 Issue
@router.post("/issue/{issue_id}/comment")
async def client_comment_issue(
    request: Request,
    issue_id: int,
    message: str = Form(...),
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 找出專案ID並驗證
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


# ---------------------------------------------------------
# 4. 下載與驗收 (New Features)
# ---------------------------------------------------------

@router.get("/download")
async def download_file(
    path: str, 
    user: dict = Depends(get_current_client_user)
):
    """
    下載檔案
    """
    if ".." in path or not path.startswith("uploads/"):
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path)


@router.post("/project/{project_id}/approve")
async def approve_project(
    project_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    驗收通過 (結案)
    """
    async with conn.cursor() as cur:
        # 檢查是否還有未解決的 Issue，如果有則不能結案
        await cur.execute(
            "SELECT COUNT(*) as count FROM project_issues WHERE project_id = %s AND status = 'open'",
            (project_id,)
        )
        issue_count = await cur.fetchone()
        if issue_count["count"] > 0:
             return RedirectResponse(url=f"/client/project/{project_id}?error=Resolve+all+issues+first", status_code=303)

        # 執行結案
        await cur.execute(
            """
            UPDATE projects 
            SET status = 'completed' 
            WHERE id = %s AND client_id = %s AND status = 'pending_approval'
            RETURNING id
            """,
            (project_id, user["id"])
        )
        result = await cur.fetchone()
        
    if not result:
        raise HTTPException(status_code=400, detail="Cannot complete project")

    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+Completed!", status_code=303)


@router.post("/project/{project_id}/reject")
async def reject_project(
    project_id: int,
    user: dict = Depends(get_current_client_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    """
    退件 (要求修改)
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE projects 
            SET status = 'rejected' 
            WHERE id = %s AND client_id = %s AND status = 'pending_approval'
            RETURNING id
            """,
            (project_id, user["id"])
        )
        result = await cur.fetchone()

    if not result:
        raise HTTPException(status_code=400, detail="Cannot reject project")

    return RedirectResponse(url=f"/client/project/{project_id}?message=Project+Rejected", status_code=303)