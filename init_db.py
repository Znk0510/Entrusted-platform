import psycopg
# 從你的 db.py 匯入連線資訊
from db import dbHost, dbPort, defaultDB, dbUser, dbPassword

INIT_SQL = """
-- 1. 建立列舉類型 (Enum Types)
-- 使用 DO block 來檢查類型是否存在，避免錯誤
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('client', 'contractor');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_status') THEN
        CREATE TYPE project_status AS ENUM ('open', 'in_progress', 'pending_approval', 'completed', 'rejected');
    END IF;
END $$;

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

-- 6. 建立索引 (加速查詢)
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_contractor_id ON projects(contractor_id);
CREATE INDEX IF NOT EXISTS idx_proposals_project_id ON proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_proposals_contractor_id ON proposals(contractor_id);
"""

def init_database():
    """
    連線到資料庫並執行初始化 SQL。
    使用同步連線 (psycopg.connect) 以確保在 FastAPI 啟動前完成。
    """
    # 組合連線字串
    conn_info = f"host={dbHost} port={dbPort} dbname={defaultDB} user={dbUser} password={dbPassword}"
    
    try:
        print("正在檢查資料庫結構...")
        with psycopg.connect(conn_info) as conn:
            with conn.cursor() as cur:
                cur.execute(INIT_SQL)
            conn.commit() # 確認執行
            print("資料庫初始化檢查完成！(表格已就緒)")
    except Exception as e:
        print(f"資料庫初始化失敗: {e}")
        # 在這裡印出錯誤但不中斷程式，以免因暫時連線問題導致伺服器崩潰
        # 如果是第一次執行且連線資訊錯誤，這裡會顯示錯誤訊息

if __name__ == "__main__":
    # 這讓你可以單獨執行 `python init_db.py` 來測試
    init_database()