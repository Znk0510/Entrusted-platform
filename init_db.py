# init_db.py
import psycopg
# 從 db.py 匯入連線參數
from db import DATABASE_URL

# 定義初始化 SQL 指令
# 使用 IF NOT EXISTS 避免重複建立錯誤
INIT_SQL = """
-- 1. 建立列舉類型 (Enum Types) - 統一管理狀態與角色
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('client', 'contractor');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_status') THEN
        CREATE TYPE project_status AS ENUM ('open', 'in_progress', 'pending_approval', 'completed', 'rejected');
    END IF;
END $$;

-- 2. 建立使用者表 (users)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    avatar VARCHAR(500),      -- 頭像路徑
    introduction TEXT,        -- 自我介紹
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 建立專案表 (projects)
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contractor_id INT REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status project_status NOT NULL DEFAULT 'open',
    deadline TIMESTAMPTZ,
    budget VARCHAR(100),      -- 預算範圍文字
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 建立提案表 (proposals) - 接案人投標用
CREATE TABLE IF NOT EXISTS proposals (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    contractor_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quote DECIMAL(10, 2) NOT NULL, -- 報價金額
    message TEXT,
    proposal_file VARCHAR(500),    -- 提案 PDF 路徑
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. 建立專案檔案表 (project_files) - 成果交付用
CREATE TABLE IF NOT EXISTS project_files (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    uploader_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(1024) NOT NULL,
    version INT NOT NULL DEFAULT 1, -- 版本控管
    description TEXT,               -- 版本說明
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. 建立問題追蹤表 (project_issues)
CREATE TABLE IF NOT EXISTS project_issues (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    creator_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. 建立問題留言表 (issue_comments)
CREATE TABLE IF NOT EXISTS issue_comments (
    id SERIAL PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES project_issues(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. 建立評價表 (reviews)
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    reviewer_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewee_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_role user_role NOT NULL, 
    rating_1 INT NOT NULL CHECK (rating_1 BETWEEN 1 AND 5), -- 維度1評分
    rating_2 INT NOT NULL CHECK (rating_2 BETWEEN 1 AND 5), -- 維度2評分
    rating_3 INT NOT NULL CHECK (rating_3 BETWEEN 1 AND 5), -- 維度3評分
    average_score DECIMAL(3, 1) NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, reviewer_id) -- 防止重複評價
);

-- 建立索引以加速查詢
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee ON reviews(reviewee_id);
"""

def init_database():
    """
    執行資料庫初始化：
    1. 建立基礎表格。
    2. 自動檢查並修復舊表格的欄位缺失 (Migration)。
    """
    try:
        print("正在檢查並更新資料庫結構...")
        # 這裡使用同步連線 (psycopg.connect) 因為初始化通常在伺服器啟動前執行一次即可
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # 1. 執行基礎建表 SQL
                cur.execute(INIT_SQL)
                
                # --- 自動修復區域 (Auto-Migration) ---
                # 用於處理專案開發過程中新增的欄位，確保舊資料庫相容
                
                # [修復 users] 檢查 avatar
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='avatar'")
                if not cur.fetchone():
                    print("--> 檢測到舊版 users 表，正在新增 avatar 與 introduction 欄位...")
                    cur.execute("ALTER TABLE users ADD COLUMN avatar VARCHAR(500)")
                    cur.execute("ALTER TABLE users ADD COLUMN introduction TEXT")

                # [修復 proposals] 檢查 created_at
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='proposals' AND column_name='created_at'")
                if not cur.fetchone():
                    print("--> 檢測到 proposals 表缺少 created_at，正在修復...")
                    # 檢查是否有舊名的 submitted_at
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='proposals' AND column_name='submitted_at'")
                    if cur.fetchone():
                         cur.execute("ALTER TABLE proposals RENAME COLUMN submitted_at TO created_at")
                    else:
                         cur.execute("ALTER TABLE proposals ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()")

                # [修復 projects] 檢查 budget
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='projects' AND column_name='budget'")
                if not cur.fetchone():
                    print("--> 檢測到 projects 表缺少 budget，正在新增...")
                    cur.execute("ALTER TABLE projects ADD COLUMN budget VARCHAR(100)")
                
                # [修復 project_files] 檢查 version (新增)
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='project_files' AND column_name='version'")
                if not cur.fetchone():
                    print("--> 檢測到 project_files 表缺少 version，正在新增...")
                    cur.execute("ALTER TABLE project_files ADD COLUMN version INT NOT NULL DEFAULT 1")
                    cur.execute("ALTER TABLE project_files ADD COLUMN description TEXT")

            conn.commit()
            print("資料庫初始化/更新完成！")
    except Exception as e:
        print(f"資料庫初始化失敗: {e}")

if __name__ == "__main__":
    init_database()