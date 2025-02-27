import sqlite3

def get_db_connection(db_path):
    """创建数据库连接并设置row_factory为sqlite3.Row"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_database(db_path):
    """初始化数据库，创建必要的表和添加默认知识库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建知识库表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS knowledge_bases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 检查文档表中是否存在knowledge_base_id列
    cursor.execute("PRAGMA table_info(documents)")
    columns = [info[1] for info in cursor.fetchall()]
    
    # 检查documents表是否存在
    table_exists = False
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
    if cursor.fetchone():
        table_exists = True
    
    if not table_exists:
        # 创建文档表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            metadata TEXT,
            knowledge_base_id INTEGER,
            FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
        )
        ''')
    elif 'knowledge_base_id' not in columns:
        # 添加knowledge_base_id列
        cursor.execute("ALTER TABLE documents ADD COLUMN knowledge_base_id INTEGER")
        # 为现有文档设置默认知识库ID
        cursor.execute("UPDATE documents SET knowledge_base_id = 1 WHERE knowledge_base_id IS NULL")
    
    # 如果没有知识库，添加默认知识库
    cursor.execute("SELECT COUNT(*) FROM knowledge_bases")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO knowledge_bases (name, description) VALUES (?, ?)",
                     ("默认知识库", "系统默认知识库"))
    
    conn.commit()
    conn.close()

def save_document_metadata(db_path, original_filename, stored_filename, file_path, file_size, kb_id=1):
    """保存文档元数据到数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (original_filename, stored_filename, file_path, file_size, knowledge_base_id) VALUES (?, ?, ?, ?, ?)",
        (original_filename, stored_filename, file_path, file_size, kb_id)
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id

def check_knowledge_base_exists(db_path, kb_id):
    """检查知识库是否存在"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists 