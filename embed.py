import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from get_vector_db import get_vector_db
from db_utils import save_document_metadata, check_knowledge_base_exists
import pdf2image

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
    try:
        # Try with PyPDF2 which can sometimes handle corrupted files better
        from langchain_community.document_loaders import PyPDFLoader
        print("Attempting to load with PyPDFLoader...")
        try:
            loader = PyPDFLoader(file_path=file_path)
            data = loader.load()
            
            # Verify content was extracted
            if not data or all(not doc.page_content.strip() for doc in data):
                raise ValueError("No content extracted with PyPDFLoader")
        except Exception as e:
            print(f"PyPDFLoader failed: {str(e)}")
            data = []
        
        # If no content, try UnstructuredPDFLoader with OCR
        if not data or all(not doc.page_content.strip() for doc in data):
            print("No content found with PyPDFLoader, trying UnstructuredPDFLoader...")
            try:
                from langchain_community.document_loaders import UnstructuredPDFLoader
                loader = UnstructuredPDFLoader(
                    file_path=file_path,
                    mode="elements",
                    strategy="fast",
                    languages=["eng", "chi_sim"]
                )
                data = loader.load()
                if not data or all(not doc.page_content.strip() for doc in data):
                    raise ValueError("No content extracted with UnstructuredPDFLoader")
            except Exception as e:
                print(f"UnstructuredPDFLoader failed: {str(e)}")
                data = []
        
        # If still no content, try with PDFMiner
        if not data or all(not doc.page_content.strip() for doc in data):
            print("No content found with UnstructuredPDFLoader, trying PDFMinerLoader...")
            try:
                from langchain_community.document_loaders import PDFMinerLoader
                loader = PDFMinerLoader(file_path=file_path)
                data = loader.load()
                if not data or all(not doc.page_content.strip() for doc in data):
                    raise ValueError("No content extracted with PDFMinerLoader")
            except Exception as e:
                print(f"PDFMinerLoader failed: {str(e)}")
                data = []
            
        # If still no content, try pdfplumber as a last resort
        if not data or all(not doc.page_content.strip() for doc in data):
            print("No content found with PDFMinerLoader, trying PDF Plumber...")
            import pdfplumber
            from langchain_core.documents import Document
            
            data = []
            try:
                with pdfplumber.open(file_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        if text.strip():
                            data.append(Document(
                                page_content=text,
                                metadata={"source": file_path, "page": i+1}
                            ))
                if not data:
                    raise ValueError("No content extracted with pdfplumber")
            except Exception as plumber_error:
                print(f"PDF Plumber also failed: {str(plumber_error)}")
        
        # If still no content, try a direct approach with PyPDF2
        if not data or all(not doc.page_content.strip() for doc in data):
            print("All PDF loaders failed, trying direct PyPDF2 approach...")
            import io
            import PyPDF2
            from langchain_core.documents import Document
            
            data = []
            try:
                # Create a PyPDF2 reader with error handling
                reader = PyPDF2.PdfReader(file_path, strict=False)
                
                # Extract text from each page
                for i in range(len(reader.pages)):
                    try:
                        page = reader.pages[i]
                        text = page.extract_text() or ""
                        if text.strip():
                            data.append(Document(
                                page_content=text,
                                metadata={"source": file_path, "page": i+1}
                            ))
                    except Exception as page_error:
                        print(f"Error extracting page {i}: {str(page_error)}")
                
                if not data:
                    raise ValueError("No content extracted with direct PyPDF2")
            except Exception as pdf2_error:
                print(f"Direct PyPDF2 approach failed: {str(pdf2_error)}")
        
        # If still no content, try raw PDF parsing
        if not data or all(not doc.page_content.strip() for doc in data):
            print("Attempting raw PDF text extraction as last resort...")
            try:
                # Try to extract text from potentially corrupted PDF
                with open(file_path, 'rb') as file:
                    content = file.read()
                    
                # Look for text content in raw binary
                import re
                text_chunks = re.findall(b'[\x20-\x7E\n]{4,}', content)
                
                # Convert bytes to string and create documents
                extracted_text = '\n'.join([chunk.decode('utf-8', errors='ignore') for chunk in text_chunks])
                
                if extracted_text.strip():
                    data = [Document(
                        page_content=extracted_text,
                        metadata={"source": file_path, "page": 1}
                    )]
                    print("Successfully extracted some text using raw binary parsing")
                else:
                    raise ValueError("No text content found in raw binary")
            except Exception as raw_error:
                print(f"Raw text extraction failed: {str(raw_error)}")
        
        # If still no content, raise error
        if not data or all(not doc.page_content.strip() for doc in data):
            raise ValueError("No content could be extracted from the PDF after multiple attempts. The file is likely severely corrupted or password-protected.")
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=7500, chunk_overlap=100)
        chunks = text_splitter.split_documents(data)
        return chunks
    except Exception as e:
        print(f"Error extracting content from PDF: {str(e)}")
        raise ValueError(f"Failed to process PDF: {str(e)}")

def embed_document(file, kb_id=1):
    """处理文档嵌入主函数"""
    # 验证知识库是否存在
    if not check_knowledge_base_exists(DB_PATH, kb_id):
        print(f"知识库 {kb_id} 不存在")
        return False, None, "Knowledge base doesn't exist"
    
    if not file.filename or not allowed_file(file.filename):
        print(f"文件类型不支持或文件名无效: {file.filename}")
        return False, None, "Unsupported file type or invalid filename"
    
    try:
        print(f"开始处理文件: {file.filename} 到知识库 {kb_id}")
        # 保存到临时目录
        temp_file_path, stored_filename = save_file(file)
        print(f"文件已保存到临时路径: {temp_file_path}")
        
        # 处理文档并创建向量嵌入
        extraction_failed = False
        error_message = ""
        try:
            chunks = load_and_split_data(temp_file_path)
            print(f"文档已分割为 {len(chunks)} 个块")
            
            # 获取向量数据库实例
            db = get_vector_db(kb_id)
            
            # 添加文档到向量数据库
            db.add_documents(chunks)
            db.persist()
            print(f"文档已成功添加到向量数据库")
        except ValueError as process_error:
            error_msg = str(process_error)
            print(f"处理文档内容时出错: {error_msg}")
            extraction_failed = True
            error_message = error_msg
            # Don't remove temp file yet, we'll still save metadata
        except Exception as process_error:
            print(f"处理文档内容时出错: {str(process_error)}")
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            return False, None, f"Error processing document: {str(process_error)}"
        
        # 将文件复制到永久存储目录
        permanent_path = os.path.join(DOCS_STORAGE, stored_filename)
        shutil.copy2(temp_file_path, permanent_path)
        print(f"文件已保存到永久路径: {permanent_path}")
        
        # 保存文档元数据到数据库
        file_size = os.path.getsize(temp_file_path)
        
        # Even if extraction failed, we still save metadata but mark it as extraction_failed
        doc_id = save_document_metadata(
            DB_PATH,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=permanent_path,
            file_size=file_size,
            kb_id=kb_id,
            extraction_failed=extraction_failed
        )
        print(f"文档元数据已保存，ID: {doc_id}")
        
        # 删除临时文件
        os.remove(temp_file_path)
        
        # If extraction failed but we saved the file, return partial success
        if extraction_failed:
            return True, doc_id, f"File saved but content extraction failed: {error_message}"
        
        return True, doc_id, "Successfully embedded document"
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
        return False, None, f"Error embedding document: {str(e)}"