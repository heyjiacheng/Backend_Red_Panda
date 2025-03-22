import os
import sqlite3
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # Import the CORS extension
from embed import embed_document
from query import perform_query
from db_utils import init_database, get_db_connection, create_conversation, get_conversation, get_conversations, delete_conversation, save_conversation_message
import json


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
CORS(app, origins="*")
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
    
    success, doc_id, message = embed_document(file, kb_id)

    if success:
        # Check if the file was saved but content extraction failed
        if "content extraction failed" in message:
            return jsonify({
                "warning": "File saved but content cannot be searched",
                "message": "The file was saved to the knowledge base but could not be processed for search. It may be corrupted or password-protected.",
                "document_id": doc_id,
                "technical_details": message
            }), 201  # 201 Created - since we did create a record, just with limitations
        else:
            return jsonify({
                "message": "success with embedding",
                "document_id": doc_id
            }), 200
    else:
        return jsonify({
            "error": message
        }), 400

@app.route('/query', methods=['POST'])
def route_query():
    """查询文档内容并返回带有源信息的回答"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "please provide a request body"}), 400
            
        user_query = data.get('query')
        kb_id = data.get('knowledge_base_id')
        conversation_id = data.get('conversation_id')
        
        if not user_query:
            return jsonify({"error": "please provide a query"}), 400
        
        # 验证知识库ID (如果提供)
        if kb_id is not None:
            try:
                kb_id = int(kb_id)
                conn = get_db_connection(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
                kb_exists = cursor.fetchone() is not None
                
                # 检查知识库是否包含文档
                cursor.execute("SELECT COUNT(*) FROM documents WHERE knowledge_base_id = ?", (kb_id,))
                doc_count = cursor.fetchone()[0]
                conn.close()
                
                if not kb_exists:
                    return jsonify({"error": "knowledge base not found", "detail": f"Knowledge base ID {kb_id} does not exist"}), 404
                
                if doc_count == 0:
                    return jsonify({
                        "error": "knowledge base is empty", 
                        "detail": f"Knowledge base ID {kb_id} has no documents. Please upload documents first."
                    }), 400
            except ValueError:
                return jsonify({"error": "invalid knowledge base id"}), 400
        
        # 验证对话ID (如果提供)
        if conversation_id is not None:
            try:
                conversation_id = int(conversation_id)
                conversation = get_conversation(DB_PATH, conversation_id)
                if not conversation:
                    return jsonify({"error": "conversation not found", "detail": f"Conversation ID {conversation_id} does not exist"}), 404
            except ValueError:
                return jsonify({"error": "invalid conversation id"}), 400
        
        # 执行查询获取回答
        response = perform_query(user_query, kb_id)
        
        # 检查是否查询失败
        if response and "error" in response:
            # 如果perform_query返回了错误信息，返回给客户端
            return jsonify(response), 400
            
        # 处理对话历史
        if conversation_id:
            try:
                # 保存用户问题到对话历史
                save_conversation_message(DB_PATH, conversation_id, 'user', user_query)
                
                # 保存AI回答到对话历史
                sources_json = json.dumps(response.get('sources', [])) if response.get('sources') else None
                save_conversation_message(DB_PATH, conversation_id, 'assistant', response.get('answer', ''), sources_json)
                
                # 添加会话ID到响应
                response['conversation_id'] = conversation_id
                
            except Exception as e:
                print(f"保存对话历史出错: {str(e)}")
                # 添加警告但继续返回查询结果
                response['warning'] = "Failed to save conversation history"
        
        # 确保响应可以正确序列化为JSON
        return jsonify(response), 200
    except Exception as e:
        print(f"查询处理错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"error with query", "detail": str(e)}), 500

# 添加一个新的路由，简化文档上传
@app.route('/upload/<int:kb_id>', methods=['POST'])
def upload_document_simple(kb_id):
    """简化的文档上传接口，通过URL路径接收知识库ID"""
    try:
        print(f"接收到上传请求，知识库ID: {kb_id}")
        print(f"请求内容类型: {request.content_type}")
        print(f"请求大小: {request.content_length} 字节")
        print(f"请求头: {dict(request.headers)}")
        
        # 检查是否为常规表单上传
        if request.files and 'file' in request.files:
            print("从表单数据中获取文件")
            file = request.files['file']
        # 检查是否为直接二进制数据(Tauri的upload API)
        elif request.data:
            print("从请求体中获取直接二进制数据")
            
            # 尝试从各种头信息获取文件名
            filename = None
            
            # 尝试从URL参数中获取文件路径
            if request.args.get('path'):
                filename = os.path.basename(request.args.get('path'))
                print(f"从URL参数path中提取文件名: {filename}")
            # 从Content-Disposition头中提取文件名
            elif 'Content-Disposition' in request.headers:
                content_disp = request.headers.get('Content-Disposition', '')
                if 'filename=' in content_disp:
                    filename = content_disp.split('filename=')[1].strip('"\'')
                    print(f"从Content-Disposition提取文件名: {filename}")
            # 检查自定义头
            elif 'X-File-Path' in request.headers:
                path = request.headers.get('X-File-Path')
                filename = os.path.basename(path)
                print(f"从X-File-Path头提取文件名: {filename}")
            
            # 无法获取文件名时使用默认文件名
            if not filename:
                filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                print(f"使用默认文件名: {filename}")
            
            # 创建临时文件 - 直接使用系统的临时目录
            temp_file_path = os.path.join(TEMP_FOLDER, f"{datetime.now().timestamp()}_{filename}")
            print(f"创建临时文件: {temp_file_path}")
            
            # 确保请求数据未被损坏
            print(f"接收到的数据大小: {len(request.data)} 字节")
            
            # 保存二进制数据到临时文件
            with open(temp_file_path, 'wb') as f:
                f.write(request.data)
            
            # 验证文件完整性
            actual_size = os.path.getsize(temp_file_path)
            expected_size = request.content_length
            print(f"写入文件大小: {actual_size} 字节, 预期大小: {expected_size} 字节")
            
            if expected_size and abs(actual_size - expected_size) > 100:  # 允许100字节的误差
                print(f"警告: 文件大小不匹配! 实际: {actual_size}, 预期: {expected_size}")
            
            # 打开临时文件作为FileStorage对象
            from werkzeug.datastructures import FileStorage
            file = FileStorage(
                stream=open(temp_file_path, 'rb'),
                filename=filename,
                content_type=request.content_type or 'application/octet-stream'
            )
        else:
            return jsonify({"error": "未找到上传的文件"}), 400

        if not file or file.filename == '':
            return jsonify({"error": "未选择文件"}), 400
        
        # 验证知识库是否存在
        conn = get_db_connection(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
        kb = cursor.fetchone()
        conn.close()
        
        if not kb:
            return jsonify({
                "error": "knowledge base not found",
                "detail": f"知识库ID {kb_id} 不存在"
            }), 404
        
        print(f"正在处理文件上传: {file.filename} 到知识库 {kb_id}")
        success, doc_id, message = embed_document(file, kb_id)

        # 清理临时文件（如果存在）
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                # 关闭文件流
                if hasattr(file, 'stream') and hasattr(file.stream, 'close'):
                    file.stream.close()
                os.remove(temp_file_path)
                print(f"临时文件已删除: {temp_file_path}")
            except Exception as e:
                print(f"删除临时文件失败: {str(e)}")

        if success:
            # 检查是否保存了文件但内容提取失败
            if "content extraction failed" in message:
                return jsonify({
                    "warning": "文件已保存但内容无法搜索",
                    "message": "文件已保存到知识库，但无法处理用于搜索。它可能已损坏或受密码保护。",
                    "document_id": doc_id,
                    "technical_details": message
                }), 201
            else:
                return jsonify({
                    "message": "文档嵌入成功",
                    "document_id": doc_id
                }), 200
        else:
            return jsonify({
                "error": message
            }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "文件上传处理失败",
            "detail": str(e)
        }), 500

# ================ 对话历史API ================

@app.route('/conversations', methods=['GET'])
def list_conversations():
    """获取对话历史列表，可按知识库筛选"""
    kb_id = request.args.get('knowledge_base_id')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        if kb_id:
            kb_id = int(kb_id)
    except ValueError:
        return jsonify({"error": "invalid knowledge base id"}), 400
    
    conversations = get_conversations(DB_PATH, kb_id, limit, offset)
    return jsonify({"conversations": conversations})

@app.route('/conversations', methods=['POST'])
def create_new_conversation():
    """创建新的对话"""
    data = request.get_json()
    
    if not data or 'title' not in data:
        return jsonify({"error": "title is required"}), 400
    
    title = data.get('title')
    kb_id = data.get('knowledge_base_id')
    
    try:
        # 如果提供了知识库ID，验证其存在性
        if kb_id:
            kb_id = int(kb_id)
            conn = get_db_connection(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM knowledge_bases WHERE id = ?", (kb_id,))
            kb = cursor.fetchone()
            conn.close()
            
            if not kb:
                return jsonify({"error": "knowledge base not found"}), 404
    except ValueError:
        return jsonify({"error": "invalid knowledge base id"}), 400
    
    conversation_id = create_conversation(DB_PATH, title, kb_id)
    
    return jsonify({
        "message": "conversation created",
        "conversation_id": conversation_id
    }), 201

@app.route('/conversations/<int:conversation_id>', methods=['GET'])
def get_conversation_detail(conversation_id):
    """获取单个对话的详细信息及其消息历史"""
    conversation = get_conversation(DB_PATH, conversation_id)
    
    if not conversation:
        return jsonify({"error": "conversation not found"}), 404
    
    return jsonify(conversation)

@app.route('/conversations/<int:conversation_id>', methods=['DELETE'])
def delete_conversation_by_id(conversation_id):
    """删除对话历史"""
    success = delete_conversation(DB_PATH, conversation_id)
    
    if not success:
        return jsonify({"error": "conversation not found or could not be deleted"}), 404
    
    return jsonify({"message": "conversation deleted"})

@app.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
def add_conversation_message(conversation_id):
    """向对话中添加新消息"""
    data = request.get_json()
    
    if not data or 'content' not in data or 'message_type' not in data:
        return jsonify({"error": "content and message_type are required"}), 400
    
    content = data.get('content')
    message_type = data.get('message_type')
    sources = data.get('sources')
    
    # 验证消息类型
    if message_type not in ['user', 'assistant']:
        return jsonify({"error": "message_type must be 'user' or 'assistant'"}), 400
    
    # 验证会话是否存在
    conversation = get_conversation(DB_PATH, conversation_id)
    if not conversation:
        return jsonify({"error": "conversation not found"}), 404
    
    # 如果提供了sources且不是字符串，转换为JSON字符串
    if sources and not isinstance(sources, str):
        sources = json.dumps(sources)
    
    # 保存消息
    message_id = save_conversation_message(DB_PATH, conversation_id, message_type, content, sources)
    
    return jsonify({
        "message": "message added",
        "message_id": message_id
    }), 201

if __name__ == '__main__':
    app.run(port=8080, debug=True)