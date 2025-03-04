import os
import sqlite3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # Import the CORS extension
from embed import embed_document
from query import perform_query
from db_utils import init_database, get_db_connection


# 定义常量
TEMP_FOLDER = os.getenv('TEMP_FOLDER', './_temp')
DOCS_STORAGE = os.getenv('DOCS_STORAGE', './documents')
DB_PATH = os.getenv('DB_PATH', './documents.db')

# 确保必要的目录存在
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(DOCS_STORAGE, exist_ok=True)

# 初始化Flask应用
app = Flask(__name__)
# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

# 初始化数据库
init_database(DB_PATH)

# ================ 知识库管理API ================

@app.route('/knowledge-bases', methods=['GET'])
def list_knowledge_bases():
    """获取所有知识库列表"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM knowledge_bases ORDER BY created_at DESC")
    knowledge_bases = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"knowledge_bases": knowledge_bases})

@app.route('/knowledge-bases', methods=['POST'])
def create_knowledge_base():
    """创建新的知识库"""
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({"error": "name is required"}), 400
    
    name = data.get('name')
    description = data.get('description', '')
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO knowledge_bases (name, description) VALUES (?, ?)",
        (name, description)
    )
    kb_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        "message": "success with knowledge",
        "knowledge_base_id": kb_id
    }), 201

@app.route('/knowledge-bases/<int:kb_id>', methods=['GET'])
def get_knowledge_base(kb_id):
    """获取指定知识库及其包含的文档"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # 获取知识库详情
    cursor.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,))
    kb = cursor.fetchone()
    
    if not kb:
        conn.close()
        return jsonify({"error": "knowledge base not found"}), 404
    
    # 获取该知识库下的所有文档
    cursor.execute(
        "SELECT id, original_filename, upload_date, file_size FROM documents WHERE knowledge_base_id = ? ORDER BY upload_date DESC", 
        (kb_id,)
    )
    documents = [dict(row) for row in cursor.fetchall()]
    
    kb_dict = dict(kb)
    kb_dict['documents'] = documents
    
    conn.close()
    return jsonify(kb_dict)

@app.route('/knowledge-bases/<int:kb_id>', methods=['PUT'])
def update_knowledge_base(kb_id):
    """更新知识库信息"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "no data provided"}), 400
    
    name = data.get('name')
    description = data.get('description')
    
    updates = []
    params = []
    
    if name:
        updates.append("name = ?")
        params.append(name)
    
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    
    if not updates:
        return jsonify({"error": "no valid update fields"}), 400
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # 检查知识库是否存在
    cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "knowledge base not found"}), 404
    
    # 更新知识库
    query = f"UPDATE knowledge_bases SET {', '.join(updates)} WHERE id = ?"
    params.append(kb_id)
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    
    return jsonify({"message": "knowledge base updated"})

@app.route('/knowledge-bases/<int:kb_id>', methods=['DELETE'])
def delete_knowledge_base(kb_id):
    """删除知识库及其所有文档"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # 检查知识库是否存在
    cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "knowledge base not found"}), 404
    
    # 获取该知识库下的所有文档
    cursor.execute("SELECT file_path FROM documents WHERE knowledge_base_id = ?", (kb_id,))
    documents = cursor.fetchall()
    
    # 删除文件系统中的文档文件
    for doc in documents:
        file_path = doc[0]
        if os.path.exists(file_path):
            os.remove(file_path)
    
    # 删除数据库中的文档记录
    cursor.execute("DELETE FROM documents WHERE knowledge_base_id = ?", (kb_id,))
    
    # 删除知识库
    cursor.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({"message": "knowledge base deleted"})

# ================ 文档管理API ================

@app.route('/documents', methods=['GET'])
def list_documents():
    """获取文档列表，可按知识库筛选"""
    kb_id = request.args.get('knowledge_base_id')
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    if kb_id:
        try:
            kb_id = int(kb_id)
            cursor.execute(
                "SELECT id, original_filename, upload_date, file_size, knowledge_base_id FROM documents WHERE knowledge_base_id = ? ORDER BY upload_date DESC", 
                (kb_id,)
            )
        except ValueError:
            conn.close()
            return jsonify({"error": "invalid knowledge base id"}), 400
    else:
        cursor.execute("SELECT id, original_filename, upload_date, file_size, knowledge_base_id FROM documents ORDER BY upload_date DESC")
    
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"documents": documents})

@app.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    """获取单个文档的详细信息"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    document = cursor.fetchone()
    conn.close()
    
    if document:
        return jsonify(dict(document))
    else:
        return jsonify({"error": "document not found"}), 404

@app.route('/documents/<int:doc_id>/download', methods=['GET'])
def download_document(doc_id):
    """下载文档文件"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, original_filename FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({"error": "document not found"}), 404
    
    file_path, original_filename = result
    
    if not os.path.exists(file_path):
        return jsonify({"error": "file not found"}), 404
    
    return send_file(file_path, download_name=original_filename, as_attachment=True)

@app.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """删除文档"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"error": "document not found"}), 404
    
    file_path = result[0]
    
    # 删除数据库记录
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    
    # 删除文件
    if os.path.exists(file_path):
        os.remove(file_path)
    
    return jsonify({"message": "document deleted"})

# ================ 嵌入和查询API ================

@app.route('/embed', methods=['POST'])
def route_embed():
    """上传并嵌入文档"""
    if 'file' not in request.files:
        return jsonify({"error": "please upload a file"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "no file selected"}), 400
    
    # 获取知识库ID，默认为1
    kb_id = request.form.get('knowledge_base_id', 1)
    try:
        kb_id = int(kb_id)
    except ValueError:
        return jsonify({"error": "invalid knowledge base id"}), 400
    
    success, doc_id = embed_document(file, kb_id)

    if success:
        return jsonify({
            "message": "success with embedding",
            "document_id": doc_id
        }), 200

    return jsonify({"error": "failed to embed document"}), 400

@app.route('/query', methods=['POST'])
def route_query():
    """查询文档内容并返回带有源信息的回答"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "please provide a request body"}), 400
            
        user_query = data.get('query')
        kb_id = data.get('knowledge_base_id')
        
        if not user_query:
            return jsonify({"error": "please provide a query"}), 400
        
        response = perform_query(user_query, kb_id)

        if response:
            # 确保响应可以正确序列化为JSON
            return jsonify(response), 200
        
        return jsonify({"error": "failed to query"}), 400
    except Exception as e:
        print(f"error with query: {str(e)}")
        return jsonify({"error": f"error with query:{str(e)}"}), 500

# 添加一个新的路由，简化文档上传
@app.route('/upload/<int:kb_id>', methods=['POST'])
def upload_document_simple(kb_id):
    """简化的文档上传接口，通过URL路径接收知识库ID"""
    if 'file' not in request.files:
        return jsonify({"error": "please upload a file"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "no file selected"}), 400
    
    # 验证知识库是否存在
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
    kb = cursor.fetchone()
    conn.close()
    
    if not kb:
        return jsonify({"error": "knowledge base not found"}), 404
    
    success, doc_id = embed_document(file, kb_id)

    if success:
        return jsonify({
            "message": "success with embedding",
            "document_id": doc_id,
            "knowledge_base_id": kb_id
        }), 200

    return jsonify({"error": "failed to embed document"}), 400

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)