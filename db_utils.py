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
    
    # 检查文档表中是否存在knowledge_base_id列和extraction_failed列
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
            extraction_failed BOOLEAN DEFAULT 0,
            FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
        )
        ''')
    else:
        # 添加可能缺少的列
        if 'knowledge_base_id' not in columns:
            # 添加knowledge_base_id列
            cursor.execute("ALTER TABLE documents ADD COLUMN knowledge_base_id INTEGER")
            # 为现有文档设置默认知识库ID
            cursor.execute("UPDATE documents SET knowledge_base_id = 1 WHERE knowledge_base_id IS NULL")
        
        if 'extraction_failed' not in columns:
            # 添加extraction_failed列
            cursor.execute("ALTER TABLE documents ADD COLUMN extraction_failed BOOLEAN DEFAULT 0")
    
    # 如果没有知识库，添加默认知识库
    cursor.execute("SELECT COUNT(*) FROM knowledge_bases")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO knowledge_bases (name, description) VALUES (?, ?)",
                     ("默认知识库", "系统默认知识库"))
    
    conn.commit()
    conn.close()

def save_document_metadata(db_path, original_filename, stored_filename, file_path, file_size, kb_id=1, extraction_failed=False):
    """保存文档元数据到数据库"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (original_filename, stored_filename, file_path, file_size, knowledge_base_id, extraction_failed) VALUES (?, ?, ?, ?, ?, ?)",
        (original_filename, stored_filename, file_path, file_size, kb_id, 1 if extraction_failed else 0)
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

def save_conversation_message(db_path, conversation_id, message_type, content, sources=None):
    """
    保存对话消息到数据库
    
    参数:
        db_path: 数据库路径
        conversation_id: 对话ID
        message_type: 消息类型 ('user' 或 'assistant')
        content: 消息内容
        sources: 引用的源信息 (JSON字符串)
        
    返回:
        int: 新消息的ID
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 保存消息
    cursor.execute(
        "INSERT INTO conversation_messages (conversation_id, message_type, content, sources) VALUES (?, ?, ?, ?)",
        (conversation_id, message_type, content, sources)
    )
    
    # 更新对话的更新时间
    cursor.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (conversation_id,)
    )
    
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id

def create_conversation(db_path, title, kb_id=None):
    """
    创建新的对话历史记录
    
    参数:
        db_path: 数据库路径
        title: 对话标题
        kb_id: 知识库ID (可选)
        
    返回:
        int: 新对话的ID
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO conversations (title, knowledge_base_id) VALUES (?, ?)",
        (title, kb_id)
    )
    
    conversation_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return conversation_id

def get_conversation(db_path, conversation_id):
    """
    获取单个对话的详细信息和所有消息
    
    参数:
        db_path: 数据库路径
        conversation_id: 对话ID
        
    返回:
        dict: 包含对话详情和消息列表的字典
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 获取对话详情
    cursor.execute(
        "SELECT * FROM conversations WHERE id = ?", 
        (conversation_id,)
    )
    conversation = cursor.fetchone()
    
    if not conversation:
        conn.close()
        return None
    
    # 获取该对话的所有消息
    cursor.execute(
        "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,)
    )
    messages = [dict(row) for row in cursor.fetchall()]
    
    # 转换为字典
    conversation_dict = dict(conversation)
    conversation_dict['messages'] = messages
    
    conn.close()
    return conversation_dict

def get_conversations(db_path, kb_id=None, limit=20, offset=0):
    """
    获取对话列表，可按知识库筛选
    
    参数:
        db_path: 数据库路径
        kb_id: 知识库ID (可选)
        limit: 返回的最大记录数
        offset: 分页起始位置
        
    返回:
        list: 对话列表
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 构建查询SQL
    query = "SELECT * FROM conversations"
    params = []
    
    if kb_id:
        query += " WHERE knowledge_base_id = ?"
        params.append(kb_id)
    
    query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    conversations = [dict(row) for row in cursor.fetchall()]
    
    # 获取每个对话的最后一条消息
    for conv in conversations:
        cursor.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
            (conv['id'],)
        )
        last_message = cursor.fetchone()
        if last_message:
            conv['last_message'] = dict(last_message)
    
    conn.close()
    return conversations

def delete_conversation(db_path, conversation_id):
    """
    删除对话及其所有消息
    
    参数:
        db_path: 数据库路径
        conversation_id: 对话ID
        
    返回:
        bool: 是否成功删除
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查对话是否存在
        cursor.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,))
        if not cursor.fetchone():
            conn.close()
            return False
        
        # 删除所有相关消息
        cursor.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conversation_id,))
        
        # 删除对话
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"删除对话时出错: {str(e)}")
        conn.close()
        return False 