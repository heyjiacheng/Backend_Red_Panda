import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from get_vector_db import get_vector_db
import sqlite3

TEMP_FOLDER = os.getenv('TEMP_FOLDER', './_temp')
DOCS_STORAGE = os.getenv('DOCS_STORAGE', './documents')
DB_PATH = os.getenv('DB_PATH', './documents.db')

# 确保目录存在
os.makedirs(DOCS_STORAGE, exist_ok=True)

# 初始化SQLite数据库
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        file_path TEXT NOT NULL,
        file_size INTEGER,
        metadata TEXT
    )
    ''')
    conn.commit()
    conn.close()

# 保存文档元数据到数据库
def save_document_metadata(original_filename, stored_filename, file_path, file_size):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (original_filename, stored_filename, file_path, file_size) VALUES (?, ?, ?, ?)",
        (original_filename, stored_filename, file_path, file_size)
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id

# Function to check if the uploaded file is allowed (only PDF files)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

# Function to save the uploaded file to the temporary folder
def save_file(file):
    # Save the uploaded file with a secure filename and return the file path
    ct = datetime.now()
    ts = ct.timestamp()
    filename = str(ts) + "_" + secure_filename(file.filename)
    file_path = os.path.join(TEMP_FOLDER, filename)
    file.save(file_path)

    return file_path, filename

# Function to load and split the data from the PDF file
def load_and_split_data(file_path):
    # Load the PDF file and split the data into chunks
    loader = UnstructuredPDFLoader(file_path=file_path)
    data = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=7500, chunk_overlap=100)
    chunks = text_splitter.split_documents(data)

    return chunks

# Main function to handle the embedding process
def embed(file):
    # 确保数据库已初始化
    init_db()
    
    if file.filename != '' and file and allowed_file(file.filename):
        # 保存到临时目录
        temp_file_path, stored_filename = save_file(file)
        
        # 处理文档并创建向量嵌入
        chunks = load_and_split_data(temp_file_path)
        db = get_vector_db()
        db.add_documents(chunks)
        db.persist()
        
        # 将文件复制到永久存储目录
        permanent_path = os.path.join(DOCS_STORAGE, stored_filename)
        shutil.copy2(temp_file_path, permanent_path)
        
        # 保存文档元数据到数据库
        file_size = os.path.getsize(temp_file_path)
        doc_id = save_document_metadata(
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=permanent_path,
            file_size=file_size
        )
        
        # 删除临时文件
        os.remove(temp_file_path)
        
        return True, doc_id

    return False, None