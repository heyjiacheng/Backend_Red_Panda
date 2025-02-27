import os
from dotenv import load_dotenv
import sqlite3
from flask import Flask, request, jsonify, send_file
from embed import embed
from query import query
from get_vector_db import get_vector_db

load_dotenv()

TEMP_FOLDER = os.getenv('TEMP_FOLDER', './_temp')
os.makedirs(TEMP_FOLDER, exist_ok=True)

DOCS_STORAGE = os.getenv('DOCS_STORAGE', './documents')
os.makedirs(DOCS_STORAGE, exist_ok=True)

DB_PATH = os.getenv('DB_PATH', './documents.db')

app = Flask(__name__)

@app.route('/embed', methods=['POST'])
def route_embed():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    success, doc_id = embed(file)

    if success:
        return jsonify({
            "message": "File embedded successfully",
            "document_id": doc_id
        }), 200

    return jsonify({"error": "File embedded unsuccessfully"}), 400

@app.route('/query', methods=['POST'])
def route_query():
    data = request.get_json()
    response = query(data.get('query'))

    if response:
        return jsonify({"message": response}), 200

    return jsonify({"error": "Something went wrong"}), 400

@app.route('/documents', methods=['GET'])
def list_documents():
    """列出所有存储的文档"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, original_filename, upload_date, file_size FROM documents ORDER BY upload_date DESC")
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"documents": documents})

@app.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    """获取单个文档的详细信息"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    document = cursor.fetchone()
    conn.close()
    
    if document:
        return jsonify(dict(document))
    else:
        return jsonify({"error": "Document not found"}), 404

@app.route('/documents/<int:doc_id>/download', methods=['GET'])
def download_document(doc_id):
    """下载文档"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_path, original_filename FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        file_path, original_filename = result
        return send_file(file_path, as_attachment=True, download_name=original_filename)
    else:
        return jsonify({"error": "Document not found"}), 404

@app.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """删除文档"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取文件路径
    cursor.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    
    file_path = result[0]
    
    # 删除数据库记录
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    
    # 如果文件存在，删除文件
    if os.path.exists(file_path):
        os.remove(file_path)
    
    return jsonify({"message": "Document deleted successfully"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)