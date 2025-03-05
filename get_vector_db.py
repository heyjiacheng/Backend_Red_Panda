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
    try:
        # 确保向量数据库目录存在
        os.makedirs(CHROMA_PATH, exist_ok=True)
        
        # 创建嵌入模型
        print(f"正在使用嵌入模型: {TEXT_EMBEDDING_MODEL}")
        embedding = OllamaEmbeddings(model=TEXT_EMBEDDING_MODEL, show_progress=True)
        
        # 如果提供了kb_id，将其作为集合名称的一部分
        collection_name = f"{BASE_COLLECTION_NAME}-{kb_id}" if kb_id else BASE_COLLECTION_NAME
        print(f"正在访问向量数据库集合: {collection_name}")
        
        # 创建并返回Chroma向量数据库
        db = Chroma(
            collection_name=collection_name,
            persist_directory=CHROMA_PATH,
            embedding_function=embedding
        )
        
        # 检查数据库是否初始化成功
        try:
            # 尝试访问集合，确保它存在且可用
            collection_count = db._collection.count()
            print(f"向量数据库集合 {collection_name} 包含 {collection_count} 条记录")
        except Exception as collection_error:
            print(f"警告: 向量数据库访问异常: {str(collection_error)}")
        
        return db
    except Exception as e:
        print(f"创建向量数据库实例时出错: {str(e)}")
        raise