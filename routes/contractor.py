from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, UploadFile, File
from fastapi import Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from psycopg_pool import AsyncConnectionPool
from db import getDB 
# 匯入我們在 auth.py 寫好的權限檢查函式
# 確保只有「接案人」身分才能呼叫這裡的 API
from routes.auth import get_current_contractor_user
import os
import aiofiles
from utils import save_upload_file, FOLDER_PROPOSALS, FOLDER_DELIVERABLES
from datetime import datetime
from main import templates
import urllib.parse
import re

# 設定 Router
router = APIRouter()

# 建立儲存資料夾 (雖然 utils.py 有做，但這裡再確保一次)
UPLOAD_DIRECTORY = "uploads"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

# ---------------------------------------------------------
# 工具函式區：處理預算字串的轉換
# 因為資料庫存的是 "5,000 以下" 這種文字，但篩選時需要轉成數字
# ---------------------------------------------------------

def get_budget_limit(budget_str: str):
    """
    將預算下拉選單的文字 (e.g., "5,000 以下") 轉換為 (最小值, 最大值) 的數字 Tuple。
    用途：接案人報價時，檢查報價是否超出預算範圍。
    """
    if not budget_str:
        return 0, float('inf') # 沒設定就無限大
        
    clean_str = budget_str.strip()

    # 定義預算對照表 (Key 必須跟 create_project.html 的 value 一模一樣)
    mapping = {
        "5,000 以下": (0, 5000),
        "5,001 - 10,000": (5001, 10000),
        "10,001 - 50,000": (10001, 50000),
        "50,001 - 100,000": (50001, 100000),
        "100,001 - 300,000": (100001, 300000),
        "300,001 - 1,000,000": (300001, 1000000),
        "1,000,001 - 3,000,000": (1000001, 3000000),
        "3,000,000 以上": (3000001, float('inf'))
    }
    
    return mapping.get(clean_str, (0, float('inf')))

def parse_budget_max_value(budget_str: str) -> int:
    """
    將預算文字轉為單一數字，用於「預算由高到低」的排序功能。
    邏輯：取區間的最大值來代表這個專案的預算規模。
    """
    if not budget_str: 
        return 0
    
    # 移除逗號與空白，方便處理
    clean_str = budget_str.replace(',', '').replace(' ', '')
    
    # 手動對照表 (處理常見格式)
    mapping = {
        "5000以下": 5000,
        "5001-10000": 10000,
        "10001-50000": 50000,
        "50001-100000": 100000,
        "100001-300000": 300000,
        "300001-1000000": 1000000,
        "1000001-3000000": 3000000,
        "3000000以上": 99999999
    }
    
    if clean_str in mapping:
        return mapping[clean_str]
        
    # 如果對照不到，嘗試用正規表達式抓出字串裡所有的數字，取最大的一個
    # 例如 "1萬 - 5萬" -> 抓出 [1, 5] -> 回傳 5
    numbers = re.findall(r'\d+', clean_str)
    if numbers:
        return int(max(map(int, numbers)))
        
    return 0

# ---------------------------------------------------------
# 1. 接案人儀表板 (Dashboard) & 搜尋引擎
# ---------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def get_contractor_dashboard(
    request: Request, 
    user: dict = Depends(get_current_contractor_user), # 權限檢查
    conn: AsyncConnectionPool = Depends(getDB),
    status_filter: str = Query("open", alias="status"), # 從網址 ?status=... 取得，預設 'open'
    search_query: str | None = Query(None, alias="search"), # 舊版搜尋參數 (保留相容性)
    # --- 新版進階篩選參數 ---
    q: str | None = Query(None),                 # 關鍵字搜尋
    min_budget: str | None = Query(None),        # 最低預算 (使用者輸入的數字)
    max_budget: str | None = Query(None),        # 最高預算
    deadline_days: str | None = Query(None),     # 截止天數 (例如 "3", "7", "custom")
    custom_deadline: str | None = Query(None),   # 自訂截止日期 (YYYY-MM-DD)
    sort: str | None = Query('newest')           # 排序方式
):
    # 資料清理：把預算轉成整數，如果使用者亂填文字就變 None
    min_b_val = int(min_budget) if min_budget and min_budget.strip().isdigit() else None
    max_b_val = int(max_budget) if max_budget and max_budget.strip().isdigit() else None

    projects = []
    
    # 統計數據 (顯示在儀表板頂端的數字卡片)
    stats = {
        "open": 0, "in_progress": 0, "pending": 0, "completed": 0
    }

    async with conn.cursor() as cur:
        
        # 1. 計算各狀態的案件數量
        await cur.execute("""
            SELECT COUNT(*) as count FROM projects 
            WHERE status = 'open' AND (deadline IS NULL OR deadline > NOW())
        """)
        stats["open"] = (await cur.fetchone())["count"]

        # 計算接案人「自己」相關的案件數量 (執行中、待驗收、已結案)
        for s, key in [
            ("('in_progress', 'rejected')", "in_progress"), 
            ("('pending_approval')", "pending"), 
            ("('completed')", "completed")
        ]:
            # 注意：這裡的 WHERE 條件多了 contractor_id = user["id"]
            # 因為「執行中」只需要看「我接的案子」，而不是全平台的案子
            await cur.execute(
                f"SELECT COUNT(*) as count FROM projects WHERE contractor_id = %s AND status IN {s}",
                (user["id"],)
            )
            stats[key] = (await cur.fetchone())["count"]

        # 2. 根據目前選的 Tab (status_filter) 撈取專案列表
        
        if status_filter == 'open':
            # --- 模式 A: 「尋找新案件」 (全平台的 Open 專案) ---
            
            base_sql = """
                SELECT p.*, u.username AS client_name,
                -- 檢查我是否已經投過標 (回傳 True/False)
                EXISTS (
                    SELECT 1 FROM proposals pr 
                    WHERE pr.project_id = p.id AND pr.contractor_id = %s
                ) as has_proposed
                FROM projects p
                JOIN users u ON p.client_id = u.id
                WHERE p.status = 'open'
                AND (p.deadline IS NULL OR p.deadline > NOW()) 
            """
            params = [user["id"]]

            # A-1. 關鍵字搜尋 (標題 或 描述)
            if q:
                base_sql += " AND (p.title ILIKE %s OR p.description ILIKE %s)"
                # ILIKE 是 PostgreSQL 專用的「不分大小寫」搜尋
                params.extend([f"%{q}%", f"%{q}%"])

            # A-2. 截止日期篩選
            if deadline_days:
                if deadline_days.isdigit(): # 3, 7, 14 天內
                    days = int(deadline_days)
                    base_sql += f" AND p.deadline <= NOW() + INTERVAL '{days} days'"
                elif deadline_days == 'custom' and custom_deadline: # 自訂日期
                    base_sql += " AND p.deadline <= %s"
                    params.append(custom_deadline)

            # A-3. 排序 SQL 部分 (僅處理非預算排序)
            if sort == 'deadline':
                base_sql += " ORDER BY p.deadline ASC NULLS LAST" # 快截止的排前面
            elif sort == 'newest':
                base_sql += " ORDER BY p.created_at DESC" # 最新的排前面
            
            await cur.execute(base_sql, tuple(params))
            raw_projects = await cur.fetchall()

            # A-4. Python 端處理：預算過濾與排序
            # (因為 DB 裡的預算是文字，無法直接用 SQL > < 比較，所以撈出來用 Python 算)
            projects = []
            for p in raw_projects:
                # 解析該專案的預算數值
                budget_val = parse_budget_max_value(p.get('budget', ''))
                
                # 篩選邏輯
                if min_b_val is not None and budget_val < min_b_val:
                    continue # 太便宜，跳過
                if max_b_val is not None and budget_val > max_b_val:
                    continue # 太貴(超出範圍)，跳過
                
                # 將數值暫存進物件，方便等下排序
                p['budget_val'] = budget_val
                projects.append(p)

            # 如果選了「預算由高到低」，在這裡進行 List 排序
            if sort == 'budget_high':
                projects.sort(key=lambda x: x.get('budget_val', 0), reverse=True)

        else:
            # --- 模式 B: 「我的專案」 (執行中、已結案...) ---
            # 這裡只需要撈出 contractor_id 是我本人的專案
            
            status_condition = ""
            if status_filter == 'in_progress':
                status_condition = "AND p.status IN ('in_progress', 'rejected')"
            elif status_filter == 'pending_approval':
                status_condition = "AND p.status = 'pending_approval'"
            elif status_filter == 'completed':
                status_condition = "AND p.status = 'completed'"
            else:
                status_condition = "AND 1=0" # 防呆：無效狀態不回傳任何資料

            sql = f"""
                SELECT p.*, u.username AS client_name
                FROM projects p
                JOIN users u ON p.client_id = u.id
                WHERE p.contractor_id = %s {status_condition}
                ORDER BY p.created_at DESC
            """
            await cur.execute(sql, (user["id"],))
            projects = await cur.fetchall()

    return templates.TemplateResponse("dashboard_contractor.html", {
        "request": request,
        "user": user,
        "projects": projects,
        "current_filter": status_filter,
        "search_query": q,
        "stats": stats
    })


# ---------------------------------------------------------
# 2. 專案詳情 (Project Detail)
# ---------------------------------------------------------
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_contractor_project_details(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    project = None
    has_proposed = False 
    my_review = None 
    
    async with conn.cursor() as cur:
        # A. 撈專案資料
        await cur.execute(
            "SELECT p.*, u.username AS client_name FROM projects p "
            "JOIN users u ON p.client_id = u.id "
            "WHERE p.id = %s", 
            (project_id,)
        )
        project = await cur.fetchone()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # B. 檢查是否投過標 (用於顯示「已投標」狀態)
        if project["status"] == 'open':
            await cur.execute(
                "SELECT id FROM proposals WHERE project_id = %s AND contractor_id = %s",
                (project_id, user["id"])
            )
            has_proposed = await cur.fetchone() is not None

        # C. 檢查是否已評價 (用於結案後)
        if project["status"] == 'completed':
            await cur.execute(
                "SELECT * FROM reviews WHERE project_id = %s AND reviewer_id = %s",
                (project_id, user["id"])
            )
            my_review = await cur.fetchone()

        # D. 撈 Issue (溝通紀錄)
        issues = []
        if project["status"] != 'open':
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
            
            # 補上每個 Issue 的留言
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

    return templates.TemplateResponse("project_detail_contractor.html", {
        "request": request,
        "user": user,
        "project": project,
        "has_proposed": has_proposed,
        "issues": issues,
        "my_review": my_review,
        "message": request.query_params.get("message", None),
        "error": request.query_params.get("error", None)
    })


# ---------------------------------------------------------
# 3. 投標功能 (Propose)
# ---------------------------------------------------------
@router.post("/project/{project_id}/propose")
async def handle_propose(
    request: Request,
    project_id: int,
    quote: float = Form(...),
    message: str = Form(""),
    proposal_pdf: UploadFile = File(...),
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    # 格式檢查：只允許 PDF
    if not proposal_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="提案計畫書必須是 PDF 格式")

    async with conn.cursor() as cur:
        await cur.execute("SELECT deadline, status, budget FROM projects WHERE id = %s", (project_id,))
        project = await cur.fetchone()
        
        if not project:
            raise HTTPException(status_code=404, detail="專案不存在")
        
        # 1. 檢查是否過期
        if project['deadline']:
             if datetime.now().astimezone() > project['deadline'].astimezone():
                 return RedirectResponse(
                     url=f"/contractor/project/{project_id}?error=Time+Limit+Exceeded", 
                     status_code=303
                 )

        # 2. 檢查報價是否符合預算範圍
        # 使用工具函式解析預算文字
        min_budget, max_budget = get_budget_limit(project.get('budget'))
        
        if quote < min_budget or quote > max_budget:
            # 報價不合理，拒絕提交
            error_msg = f"報價金額 (${int(quote)}) 超出預算範圍 ({project['budget']})，無法提交。"
            encoded_error = urllib.parse.quote(error_msg)
            return RedirectResponse(
                url=f"/contractor/project/{project_id}?error={encoded_error}", 
                status_code=303
            )

        # 3. 儲存檔案
        file_path = await save_upload_file(proposal_pdf, project_id, FOLDER_PROPOSALS)
        
        # 4. 寫入資料庫
        await cur.execute(
            """
            INSERT INTO proposals (project_id, contractor_id, quote, message, proposal_file)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, user["id"], quote, message, file_path)
        )
        
    return RedirectResponse(url=f"/contractor/project/{project_id}?message=Proposed", status_code=303)


# ---------------------------------------------------------
# 4. 上傳交付檔案 (Upload Deliverables)
# ---------------------------------------------------------
@router.post("/project/{project_id}/upload")
async def upload_project_file(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        await cur.execute("SELECT status, contractor_id FROM projects WHERE id = %s", (project_id,))
        project = await cur.fetchone()
        
        # 權限檢查：必須是該專案的得標者
        if not project or project["contractor_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="無權限")
            
        # 狀態檢查：只有「進行中」或「被退件」時才能上傳
        allowed_statuses = ('in_progress', 'rejected', 'pending_approval')
        if project["status"] not in allowed_statuses:
             raise HTTPException(status_code=400, detail="目前狀態無法上傳檔案")

        # 儲存檔案
        file_path = await save_upload_file(file, project_id, FOLDER_DELIVERABLES)
        
        # 記錄到 project_files 表
        await cur.execute(
            "INSERT INTO project_files (project_id, uploader_id, filename, filepath) VALUES (%s, %s, %s, %s)",
            (project_id, user["id"], file.filename, file_path)
        )
        
        # 狀態自動更新為「等待驗收」(pending_approval)
        await cur.execute(
            "UPDATE projects SET status = 'pending_approval' WHERE id = %s",
            (project_id,)
        )
        
    return RedirectResponse(url=f"/contractor/project/{project_id}?message=File+Updated", status_code=303)


# ---------------------------------------------------------
# 5. Issue 留言功能
# ---------------------------------------------------------
@router.post("/issue/{issue_id}/comment")
async def contractor_comment_issue(
    request: Request,
    issue_id: int,
    message: str = Form(...),
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 權限檢查：確認該 Issue 屬於我接的案子
        await cur.execute(
            """
            SELECT p.id FROM project_issues i
            JOIN projects p ON i.project_id = p.id
            WHERE i.id = %s AND p.contractor_id = %s
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
        
    return RedirectResponse(url=f"/contractor/project/{project['id']}?message=Comment+added", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------
# 6. 下載檔案 (安全檢查)
# ---------------------------------------------------------
@router.get("/download")
async def download_file(
    path: str, 
    user: dict = Depends(get_current_contractor_user)
):
    # 防止 Path Traversal 攻擊 (禁止 .. 移動到上一層)
    if ".." in path or not path.startswith("uploads/"):
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path)