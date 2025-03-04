import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from get_vector_db import get_vector_db
from db_utils import save_document_metadata, check_knowledge_base_exists

# 定义常量
TEMP_FOLDER = os.getenv('TEMP_FOLDER', './_temp')
DOCS_STORAGE = os.getenv('DOCS_STORAGE', './documents')
DB_PATH = os.getenv('DB_PATH', './documents.db')

# 确保目录存在
os.makedirs(DOCS_STORAGE, exist_ok=True)

def allowed_file(filename):
    """检查文件是否为允许的类型（仅PDF）"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

def save_file(file):
    """保存上传的文件到临时文件夹并返回文件路径"""
    ct = datetime.now()
    ts = ct.timestamp()
    filename = str(ts) + "_" + secure_filename(file.filename)
    file_path = os.path.join(TEMP_FOLDER, filename)
    file.save(file_path)
    return file_path, filename

def load_and_split_data(file_path):
    """加载PDF文件并分割数据"""
    loader = UnstructuredPDFLoader(file_path=file_path)
    data = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=7500, chunk_overlap=100)
    chunks = text_splitter.split_documents(data)
    return chunks

def embed_document(file, kb_id=1):
    """处理文档嵌入主函数"""
    # 验证知识库是否存在
    if not check_knowledge_base_exists(DB_PATH, kb_id):
        print(f"知识库 {kb_id} 不存在")
        return False, None
    
    if not file.filename or not allowed_file(file.filename):
        print(f"文件类型不支持或文件名无效: {file.filename}")
        return False, None
    
    try:
        print(f"开始处理文件: {file.filename} 到知识库 {kb_id}")
        # 保存到临时目录
        temp_file_path, stored_filename = save_file(file)
        print(f"文件已保存到临时路径: {temp_file_path}")
        
        # 处理文档并创建向量嵌入
        try:
            chunks = load_and_split_data(temp_file_path)
            print(f"文档已分割为 {len(chunks)} 个块")
            
            # 获取向量数据库实例
            db = get_vector_db(kb_id)
            
            # 添加文档到向量数据库
            db.add_documents(chunks)
            db.persist()
            print(f"文档已成功添加到向量数据库")
        except Exception as process_error:
            print(f"处理文档内容时出错: {str(process_error)}")
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise process_error
        
        # 将文件复制到永久存储目录
        permanent_path = os.path.join(DOCS_STORAGE, stored_filename)
        shutil.copy2(temp_file_path, permanent_path)
        print(f"文件已保存到永久路径: {permanent_path}")
        
        # 保存文档元数据到数据库
        file_size = os.path.getsize(temp_file_path)
        doc_id = save_document_metadata(
            DB_PATH,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=permanent_path,
            file_size=file_size,
            kb_id=kb_id
        )
        print(f"文档元数据已保存，ID: {doc_id}")
        
        # 删除临时文件
        os.remove(temp_file_path)
        
        return True, doc_id
    except Exception as e:
        print(f"嵌入文档时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        # 确保清理临时文件
        try:
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except:
            pass
        return False, None