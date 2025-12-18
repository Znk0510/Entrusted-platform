from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, UploadFile, File
from fastapi import Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from psycopg_pool import AsyncConnectionPool
from db import getDB # 資料庫連線函式
from routes.auth import get_current_contractor_user, get_current_user 
import os
import aiofiles

# 從 main 匯入共用的 templates 物件 
#from main import templates

from fastapi.templating import Jinja2Templates
# 重新定義 templates 物件
templates = Jinja2Templates(directory="templates")

# 設定
router = APIRouter()

# 建立一個儲存上傳檔案的資料夾 (如果它不存在的話)
UPLOAD_DIRECTORY = "uploads"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)


# 接案人儀表板
@router.get("/dashboard", response_class=HTMLResponse)
async def get_contractor_dashboard(
    request: Request, 
    user: dict = Depends(get_current_contractor_user), # 保護路由
    conn: AsyncConnectionPool = Depends(getDB),
    # --- 2. (新) 接收 URL 傳來的 search_query 參數 ---
    search_query: str | None = Query(None, alias="search") 
):
    """
    顯示接案人的主儀表板。
    - 區塊 1: 顯示 所有 'open' (開放中)的專案 (查詢/觀看委託專案)
    - 區塊 2: 顯示 贏得的專案
    - 區塊 3: 顯示 投標的(審核中)專案
    - 區塊 4: 顯示 未得標的專案
    """
    open_projects = []
    won_projects = []
    bid_projects = []
    lost_projects = [] 
    
    async with conn.cursor() as cur:
        
        # 區塊 1: 查詢 'open' 的專案/搜尋
        
        # 基礎查詢
        sql_open_projects = """
            SELECT p.id, p.title, p.description, p.status, u.username AS client_name
            FROM projects p
            JOIN users u ON p.client_id = u.id
            WHERE p.status = 'open' AND p.client_id != %s
            AND NOT EXISTS (
                SELECT 1 FROM proposals pr 
                WHERE pr.project_id = p.id AND pr.contractor_id = %s
            )
        """
        
        # 準備參數
        params = [user["id"], user["id"]]
        
        # 如果有搜尋字詞，就加入 SQL 條件
        if search_query:
            sql_open_projects += " AND (p.title ILIKE %s OR p.description ILIKE %s)"
            # ILIKE 是 PostgreSQL 中 "不分大小寫" 的 LIKE
            params.append(f"%{search_query}%")
            params.append(f"%{search_query}%")

        sql_open_projects += " ORDER BY p.created_at DESC"
        
        await cur.execute(sql_open_projects, tuple(params))
        open_projects = await cur.fetchall()

        # 區塊 2: 查詢 "贏得的案子"
        await cur.execute(
            """
            SELECT p.id, p.title, p.status, u.username AS client_name
            FROM projects p
            JOIN users u ON p.client_id = u.id
            WHERE p.contractor_id = %s
            ORDER BY 
                CASE status
                    WHEN 'in_progress' THEN 1
                    WHEN 'rejected' THEN 2
                    WHEN 'pending_approval' THEN 3
                    WHEN 'completed' THEN 4
                END,
                p.created_at DESC
            """,
            (user["id"],)
        )
        won_projects = await cur.fetchall()
        
        # 區塊 3: 查詢 "投標的案子"
        await cur.execute(
            """
            SELECT p.id, p.title, u.username AS client_name
            FROM projects p
            JOIN users u ON p.client_id = u.id
            JOIN proposals pr ON p.id = pr.project_id
            WHERE pr.contractor_id = %s AND p.status = 'open'
            ORDER BY p.created_at DESC
            """,
            (user["id"],)
        )
        bid_projects = await cur.fetchall()

        # 區塊 4: 查詢 "未得標的案子"
        await cur.execute(
            """
            SELECT p.id, p.title, p.status, u.username AS client_name
            FROM projects p
            JOIN users u ON p.client_id = u.id
            JOIN proposals pr ON p.id = pr.project_id
            WHERE 
                pr.contractor_id = %s
                AND p.status != 'open'
                AND (p.contractor_id IS NULL OR p.contractor_id != %s)
            ORDER BY p.created_at DESC
            """,
            (user["id"], user["id"])
        )
        lost_projects = await cur.fetchall()


    return templates.TemplateResponse("dashboard_contractor.html", {
        "request": request,
        "user": user,
        "open_projects": open_projects,
        "won_projects": won_projects,
        "bid_projects": bid_projects,
        "lost_projects": lost_projects,
        "search_query": search_query
    })

# 專案詳情（接案人）
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def get_contractor_project_details(
    request: Request,
    project_id: int,
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    has_proposed = False
    issues = []

    # ⭐ 評價相關
    client_rating_summary = None
    client_comments = []
    can_rate = False
    already_rated = False
    client = None

    async with conn.cursor() as cur:

        # 1️⃣ 先取得專案（一定要最先）
        await cur.execute(
            """
            SELECT p.*, u.username AS client_name
            FROM projects p
            JOIN users u ON p.client_id = u.id
            WHERE p.id = %s
            """,
            (project_id,)
        )
        project = await cur.fetchone()

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # 2️⃣ 是否已投標
        if project["status"] == "open":
            await cur.execute(
                "SELECT 1 FROM proposals WHERE project_id = %s AND contractor_id = %s",
                (project_id, user["id"])
            )
            has_proposed = await cur.fetchone() is not None

        # 3️⃣ Issue Tracker（非 open）
        if project["status"] != "open":
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

        # ==================================================
        # ⭐ 委託人「被評價摘要」（給接案人看）
        # ==================================================
        await cur.execute(
            """
            SELECT
                AVG(requirement_rationality_score) AS requirement_rationality_avg,
                AVG(acceptance_difficulty_score)   AS acceptance_difficulty_avg,
                AVG(client_attitude_score)         AS client_attitude_avg,
                COUNT(*)                           AS rating_count
            FROM ratings
            WHERE ratee_id = %s
              AND rating_direction = 'contractor_to_client'
            """,
            (project["client_id"],)
        )
        client_rating_summary = await cur.fetchone()

        await cur.execute(
            """
            SELECT overall_comment, rating_date
            FROM ratings
            WHERE ratee_id = %s
              AND rating_direction = 'contractor_to_client'
              AND overall_comment IS NOT NULL
            ORDER BY rating_date DESC
            LIMIT 5
            """,
            (project["client_id"],)
        )
        client_comments = await cur.fetchall()

        # ==================================================
        # ⭐ 接案人 → 委託人 是否可評價
        # ==================================================
        if (
            project["status"] == "completed"
            and project["contractor_id"] == user["id"]
        ):
            # 委託人資料
            await cur.execute(
                "SELECT id, username FROM users WHERE id = %s",
                (project["client_id"],)
            )
            client = await cur.fetchone()

            # 是否已評價
            await cur.execute(
                """
                SELECT 1 FROM ratings
                WHERE project_id = %s
                  AND rater_id = %s
                  AND rating_direction = 'contractor_to_client'
                """,
                (project_id, user["id"])
            )
            already_rated = await cur.fetchone() is not None
            can_rate = not already_rated

    return templates.TemplateResponse(
        "project_detail_contractor.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "has_proposed": has_proposed,
            "issues": issues,
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),

            # ⭐ 評價顯示
            "client_rating": client_rating_summary,
            "client_comments": client_comments,

            # ⭐ 評價行為
            "can_rate": can_rate,
            "already_rated": already_rated,
            "client": client,
        }
    )
    

# 專案詳情
#@router.get("/project/{project_id}", response_class=HTMLResponse)
#async def get_contractor_project_details(
  #  request: Request,
  #  project_id: int,
   # user: dict = Depends(get_current_contractor_user), # 保護
   # conn: AsyncConnectionPool = Depends(getDB)
#):
   # project = None
   # has_proposed = False 
    
   # async with conn.cursor() as cur:
   #     await cur.execute(
   #         "SELECT p.*, u.username AS client_name FROM projects p "
   #         "JOIN users u ON p.client_id = u.id "
   #         "WHERE p.id = %s", 
    #        (project_id,)
    #    )
    #    project = await cur.fetchone()
    
    #    if not project:
   #         raise HTTPException(status_code=404, detail="Project not found")

   #     if project["status"] == 'open':
 #           await cur.execute(
 #               "SELECT id FROM proposals WHERE project_id = %s AND contractor_id = %s",
  #              (project_id, user["id"])
  #          )
  #          has_proposed = await cur.fetchone() is not None

        # 取得 Issue Tracker 資料
   #     issues = []
        # 只有當專案狀態不是 open (已經開始合作後) 才顯示 issue
     #   if project["status"] != 'open':
     #       await cur.execute(
     #           """
      #          SELECT i.*, u.username AS creator_name
     #           FROM project_issues i
    #            JOIN users u ON i.creator_id = u.id
    #            WHERE i.project_id = %s
   #             ORDER BY i.created_at DESC
       #         """,
   #             (project_id,)
   #         )
   #         issues_data = await cur.fetchall()
            
     #       for issue in issues_data:
        #        await cur.execute(
      #              """
      #              SELECT c.*, u.username, u.role
      #              FROM issue_comments c
      #              JOIN users u ON c.user_id = u.id
      #              WHERE c.issue_id = %s
      #              ORDER BY c.created_at ASC
      #              """,
       #             (issue["id"],)
       #         )
       #         issue["comments"] = await cur.fetchall()
        #        issues.append(issue)    
       #         
    # =========================
    # ⭐ 評價相關（接案人 → 委託人）
    # =========================
   #     can_rate = False
    #    already_rated = False
    #    client = None
#
    #    if project["status"] == "completed" and project["contractor_id"] == user["id"]:
            # 取得委託人資料
      #      await cur.execute(
        #       "SELECT id, username FROM users WHERE id = %s",
        #        (project["client_id"],)
        #    )
        #    client = await cur.fetchone()

            # 檢查是否已經評價過
       #     await cur.execute(
        #        """
        #        SELECT 1 FROM ratings
       #         WHERE project_id = %s
       #           AND rater_id = %s
       #           AND rating_direction = 'contractor_to_client'
        #        """,
      #          (project_id, user["id"])
        #    )
      #      already_rated = await cur.fetchone() is not None

       #     can_rate = not already_rated
            

   # return templates.TemplateResponse("project_detail_contractor.html", {
     #   "request": request,
     #   "user": user,
    #    "project": project,
    #    "has_proposed": has_proposed,
    #    "issues": issues,
     #   "message": request.query_params.get("message", None),
     #   "error": request.query_params.get("error", None),
        
         # ⭐ 評價相關（新增）
     #   "can_rate": can_rate,
    #    "already_rated": already_rated,
    #    "client": client,
    
    
  #  return templates.TemplateResponse("project_detail_contractor.html", {
  #      "request": request,
  #      "user": user,
  #      "project": project,
  #      "has_proposed": has_proposed,
   #     "issues": issues,
  #      "message": request.query_params.get("message", None),
   #     "error": request.query_params.get("error", None),

        # ⭐ 評價
   #     "can_rate": can_rate,
   #     "already_rated": already_rated,
  #      "client": client,
 #   })

    
#})

# 投標
@router.post("/project/{project_id}/propose")
async def handle_propose(
    request: Request,
    project_id: int,
    quote: float = Form(...),
    message: str = Form(...),
    user: dict = Depends(get_current_contractor_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    redirect_url = f"/contractor/project/{project_id}"
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO proposals (quote, message, contractor_id, project_id)
                VALUES (%s, %s, %s, %s)
                """,
                (quote, message, user["id"], project_id)
            )
        return RedirectResponse(
            url=f"{redirect_url}?message=Proposal+submitted+successfully.", 
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{redirect_url}?error=Failed+to+submit+proposal.+Have+you+already+proposed?", 
            status_code=status.HTTP_303_SEE_OTHER
        )

# 上傳檔案
@router.post("/project/{project_id}/upload_file")
async def handle_upload_file(
    request: Request,
    project_id: int,
    file: UploadFile = File(...), # 接收檔案
    user: dict = Depends(get_current_contractor_user), # 保護
    conn: AsyncConnectionPool = Depends(getDB)
):
    redirect_url = f"/contractor/project/{project_id}"

    async with conn.cursor() as cur:
        # 驗證是否為此專案的得標者
        await cur.execute(
            "SELECT id FROM projects WHERE id = %s AND contractor_id = %s",
            (project_id, user["id"])
        )
        project = await cur.fetchone()
        if not project:
            return RedirectResponse(
                url=f"{redirect_url}?error=You+are+not+the+assigned+contractor+for+this+project.", 
                status_code=status.HTTP_303_SEE_OTHER
            )
        
    # 儲存檔案到伺服器
    filepath = os.path.join(UPLOAD_DIRECTORY, f"{project_id}_{user['id']}_{file.filename}")
    
    try:
        async with aiofiles.open(filepath, "wb") as buffer:
            while chunk := await file.read(1024 * 1024): 
                await buffer.write(chunk)
    except Exception as e:
        return RedirectResponse(
            url=f"{redirect_url}?error=File+upload+failed: {e}", 
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 更新資料庫
    try:
        async with conn.cursor() as cur:
            # 記錄檔案
            await cur.execute(
                """
                INSERT INTO project_files (filename, filepath, project_id, uploader_id)
                VALUES (%s, %s, %s, %s)
                """,
                (file.filename, filepath, project_id, user["id"])
            )
            
            # 更新專案狀態
            await cur.execute(
                """
                UPDATE projects
                SET status = 'pending_approval'
                WHERE id = %s AND (status = 'in_progress' OR status = 'rejected')
                """,
                (project_id,)
            )
    except Exception as e:
        os.remove(filepath)
        return RedirectResponse(
            url=f"{redirect_url}?error=Database+error+after+upload: {e}", 
            status_code=status.HTTP_303_SEE_OTHER
        )

    return RedirectResponse(
        url=f"{redirect_url}?message=File+uploaded+successfully.+Project+is+pending+approval.", 
        status_code=status.HTTP_303_SEE_OTHER
    )

# 下載檔案(擺著...前端沒設計)
@router.get("/download_file/{file_id}")
async def download_file(
    request: Request,
    file_id: int,
    user: dict = Depends(get_current_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    if not user:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
         
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT pf.filepath, pf.filename
            FROM project_files pf
            JOIN projects p ON pf.project_id = p.id
            WHERE 
                pf.id = %s
                AND (p.client_id = %s OR p.contractor_id = %s)
            """,
            (file_id, user["id"], user["id"])
        )
        file_record = await cur.fetchone()
        
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found or access denied.")
    
    filepath = file_record["filepath"]
    filename = file_record["filename"]
    
    if not os.path.exists(filepath):
         raise HTTPException(status_code=44, detail="File not found on server.")

    return FileResponse(path=filepath, filename=filename)

@router.post("/issue/{issue_id}/comment")
async def contractor_comment_issue(
    request: Request,
    issue_id: int,
    message: str = Form(...),
    user: dict = Depends(get_current_contractor_user),
    conn: AsyncConnectionPool = Depends(getDB)
):
    async with conn.cursor() as cur:
        # 驗證接案人是否負責此專案
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