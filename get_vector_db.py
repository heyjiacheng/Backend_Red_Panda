import os
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores.chroma import Chroma

# 使用环境变量配置
CHROMA_PATH = os.getenv('CHROMA_PATH', 'chroma')
BASE_COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'kb')
TEXT_EMBEDDING_MODEL = os.getenv('TEXT_EMBEDDING_MODEL', 'nomic-embed-text')

def get_vector_db(kb_id=None):
    """
    获取向量数据库实例
    
    参数:
        kb_id: 知识库ID，用于区分不同知识库的向量存储
        
    返回:
        Chroma向量数据库实例
    """
    # 创建嵌入模型
    embedding = OllamaEmbeddings(model=TEXT_EMBEDDING_MODEL, show_progress=True)
    
    # 如果提供了kb_id，将其作为集合名称的一部分
    collection_name = f"{BASE_COLLECTION_NAME}-{kb_id}" if kb_id else BASE_COLLECTION_NAME
    
    # 创建并返回Chroma向量数据库
    db = Chroma(
        collection_name=collection_name,
        persist_directory=CHROMA_PATH,
        embedding_function=embedding
    )

    return db