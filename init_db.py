import psycopg
import asyncio
from psycopg_pool import AsyncConnectionPool
from psycopg.errors import DuplicateDatabase
# 從你的 db.py 匯入連線資訊
from db import dbHost, dbPort, defaultDB, dbUser, dbPassword, DATABASE_CONNINFO
from datetime import datetime

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



#-- 建立 review_role ENUM（若不存在）


INIT_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('client', 'contractor');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_status') THEN
        CREATE TYPE project_status AS ENUM ('open', 'in_progress', 'pending_approval', 'completed', 'rejected');
    END IF;
END $$;
;

-- 2. 建立 users 表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 建立 projects 表
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    client_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contractor_id INT REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status project_status NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. 建立 proposals 表 (提案)
CREATE TABLE IF NOT EXISTS proposals (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    contractor_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    quote NUMERIC(10, 2) NOT NULL,
    message TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, contractor_id) -- 確保同一人對同一案子只能投標一次
);

-- 5. 建立 project_files 表 (結案檔案)
CREATE TABLE IF NOT EXISTS project_files (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    uploader_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(1024) NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. 建立 ratings 表（甲乙雙向評價）
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rater_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ratee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    rating_direction VARCHAR(20) NOT NULL, -- 'client_to_contractor' 或 'contractor_to_client'
    overall_comment TEXT,
    rating_date TIMESTAMPTZ DEFAULT NOW(),

    -- 乙方受評維度 (甲方評乙方)
    output_quality_score INTEGER CHECK (output_quality_score BETWEEN 1 AND 5),
    execution_efficiency_score INTEGER CHECK (execution_efficiency_score BETWEEN 1 AND 5),
    contractor_attitude_score INTEGER CHECK (contractor_attitude_score BETWEEN 1 AND 5),

    -- 甲方受評維度 (乙方評甲方)
    requirement_rationality_score INTEGER CHECK (requirement_rationality_score BETWEEN 1 AND 5),
    acceptance_difficulty_score INTEGER CHECK (acceptance_difficulty_score BETWEEN 1 AND 5),
    client_attitude_score INTEGER CHECK (client_attitude_score BETWEEN 1 AND 5),

    UNIQUE (project_id, rater_id, ratee_id)
);


-- 7. 建立索引 (加速查詢)
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_contractor_id ON projects(contractor_id);
CREATE INDEX IF NOT EXISTS idx_proposals_project_id ON proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_proposals_contractor_id ON proposals(contractor_id);

-- 8. 建立 project_issues 表 (待解決事項)
CREATE TABLE IF NOT EXISTS project_issues (
    id SERIAL PRIMARY KEY,
    project_id INT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    creator_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'open', -- 'open' (未解決) or 'resolved' (已解決)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. 建立 issue_comments 表 (事項討論/回覆)
CREATE TABLE IF NOT EXISTS issue_comments (
    id SERIAL PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES project_issues(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issues_projects_id ON project_issues(project_id);
CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON issue_comments(issue_id);
"""

# -------------------------------------------------
# 1️⃣ 確保 database 存在（不能在 transaction）
# -------------------------------------------------
async def ensure_database_exists():
    conninfo = (
        f"dbname=postgres "
        f"user={dbUser} "
        f"password={dbPassword} "
        f"host={dbHost} "
        f"port={dbPort}"
    )

    conn = await psycopg.AsyncConnection.connect(
        conninfo,
        autocommit=True
    )

    try:
        await conn.execute(f'CREATE DATABASE "{defaultDB}"')
        print(f"✅ Database '{defaultDB}' created")
    except DuplicateDatabase:
        print(f"ℹ️ Database '{defaultDB}' already exists")
    finally:
        await conn.close()



async def initialize_database():
    print("🔧 初始化資料庫結構...")
    async with await psycopg.AsyncConnection.connect(DATABASE_CONNINFO) as conn:
        await conn.execute(INIT_SQL)
    print("✅ Database schema ready")


#async def initialize_database():
   # print("正在檢查資料庫與資料表狀態...")
    
    # 建立一個臨時的連線池或單次連線來執行建表
    #async with AsyncConnectionPool(DATABASE_CONNINFO) as pool:
      #  async with pool.connection() as conn:
       #     async with conn.cursor() as cur:
        #        # 執行建表 SQL
        #        await cur.execute(INIT_SQL)
                # 確保變更被儲存
       #         await conn.commit()
                
   # print("✅ 資料庫初始化完成！資料表已準備好。")


#if __name__ == "__main__":
    # 這讓你可以單獨執行 `python init_db.py` 來測試
    #init_database()
    
# 這一塊是用來測試單獨執行這個檔案時用的
# -------------------------------------------------
# CLI 測試用
# -------------------------------------------------
if __name__ == "__main__":
    async def main():
        await ensure_database_exists()
        await initialize_database()

    asyncio.run(main())