import os
import json
from typing import List, Dict, Any, Optional
import numpy as np

from langchain_community.chat_models import ChatOllama
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain.retrievers.multi_query import MultiQueryRetriever
from get_vector_db import get_vector_db
from db_utils import get_db_connection

# 使用环境变量配置
LLM_MODEL = os.getenv('LLM_MODEL', 'mistral')
DB_PATH = os.getenv('DB_PATH', './documents.db')

def get_prompt() -> tuple:
    """
    创建查询和回答的提示模板
    
    返回:
        tuple: 包含查询提示模板和回答提示模板的元组
    """
    # 多重查询提示模板 - 使用英文提示以提高性能
    query_prompt = PromptTemplate(
        input_variables=["question"],
        template="""You are an AI assistant. Your task is to generate five different versions 
        of the user's question to help retrieve relevant information from a vector database.
        By generating multiple perspectives of the question, you can help overcome some limitations
        of distance-based similarity search. Provide these alternative questions separated by line breaks.
        
        Original question: {question}""",
    )

    # 回答提示模板 - 使用英文提示并确保不输出内部思考过程
    answer_prompt = ChatPromptTemplate.from_template("""Answer the question based on the context below.
    Do NOT include any thinking process tags like <think> or similar. Provide a direct, concise answer.
    
    Context:
    {context}
    
    Question: {question}
    
    Please provide a clear, professional answer in the user's original language:
    """)

    return query_prompt, answer_prompt

def get_document_metadata(doc_source: str) -> Optional[str]:
    """
    从数据库中获取文档的原始文件名
    
    参数:
        doc_source: 文档源路径
        
    返回:
        str: 原始文件名或None
    """
    if not doc_source:
        return None
        
    source_file = os.path.basename(doc_source)
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT original_filename FROM documents WHERE stored_filename = ?", 
            (source_file,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
        return source_file
    except Exception as e:
        print(f"获取文档元数据时出错: {str(e)}")
        return source_file
    finally:
        conn.close()

def calculate_relevance_score(query_embedding, doc_embedding):
    """
    计算查询和文档嵌入之间的相似度分数
    
    参数:
        query_embedding: 查询的嵌入向量
        doc_embedding: 文档的嵌入向量
        
    返回:
        float: 相似度分数 (0-100)
    """
    # 使用余弦相似度计算相关性
    dot_product = np.dot(query_embedding, doc_embedding)
    query_norm = np.linalg.norm(query_embedding)
    doc_norm = np.linalg.norm(doc_embedding)
    
    if query_norm == 0 or doc_norm == 0:
        return 0
    
    cosine_similarity = dot_product / (query_norm * doc_norm)
    # 将相似度转换为百分比分数
    return float(max(0, min(100, (cosine_similarity + 1) * 50)))

def format_sources(retrieved_docs: List[Document], query_embedding=None, doc_embeddings=None) -> List[Dict[str, Any]]:
    """
    格式化检索到的文档源信息，并包含相关度分数
    
    参数:
        retrieved_docs: 检索到的文档列表
        query_embedding: 查询的嵌入向量 (可选)
        doc_embeddings: 文档的嵌入向量 (可选)
        
    返回:
        List[Dict[str, Any]]: 格式化后的源信息列表
    """
    sources = []
    
    for i, doc in enumerate(retrieved_docs):
        # 提取文档内容
        content = doc.page_content
        
        # 获取文档元数据
        metadata = doc.metadata
        source_path = metadata.get('source') if metadata else None
        document_name = get_document_metadata(source_path) or "未知文档"
        
        # 计算相关度分数 (如果提供了嵌入向量)
        relevance_score = None
        if query_embedding is not None and doc_embeddings is not None and i < len(doc_embeddings):
            relevance_score = calculate_relevance_score(query_embedding, doc_embeddings[i])
        
        # 创建源信息对象
        source_info = {
            "document_name": document_name,
            "content": content,
            "content_preview": content[:100] + "..." if len(content) > 100 else content,
            "relevance_score": relevance_score
        }
        
        # 如果有其他元数据，也可以添加
        if metadata:
            # 过滤掉不需要的大型元数据 (如嵌入向量)
            filtered_metadata = {k: v for k, v in metadata.items() 
                                if k not in ['source'] and not isinstance(v, (list, np.ndarray)) 
                                or (isinstance(v, list) and len(v) < 20)}
            source_info["metadata"] = filtered_metadata
        
        sources.append(source_info)
    
    # 按相关度分数排序 (如果有)
    if sources and sources[0].get("relevance_score") is not None:
        sources.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    return sources

def clean_llm_response(response: str) -> str:
    """
    清理LLM响应中的内部思考和特殊标记
    
    参数:
        response: LLM原始响应
        
    返回:
        str: 清理后的响应
    """
    # 移除<think>...</think>块
    import re
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    
    # 移除其他可能的思考标记
    response = re.sub(r'\*\*思考：.*?\*\*', '', response, flags=re.DOTALL)
    response = re.sub(r'\*\*thinking:.*?\*\*', '', response, flags=re.DOTALL)
    response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
    
    # 移除多余的空行
    response = re.sub(r'\n{3,}', '\n\n', response)
    
    return response.strip()

def rerank_documents(query: str, docs: List[Document]) -> List[Document]:
    """
    对文档进行重新排序，找出与查询最相关的文档
    
    参数:
        query: 用户查询
        docs: 检索到的文档列表
        
    返回:
        List[Document]: 重新排序的文档列表
    """
    try:
        # 这里可以使用第三方重排模型，如sentence-transformers中的CrossEncoder
        # 简单实现：根据关键词匹配度排序
        from collections import Counter
        
        # 将查询拆分为关键词
        import re
        # 移除标点符号并转为小写
        query_clean = re.sub(r'[^\w\s]', '', query.lower())
        query_terms = set(query_clean.split())
        
        # 计算每个文档包含多少查询关键词
        doc_scores = []
        for doc in docs:
            content_clean = re.sub(r'[^\w\s]', '', doc.page_content.lower())
            content_terms = Counter(content_clean.split())
            
            # 计算关键词匹配得分
            score = sum(content_terms[term] for term in query_terms if term in content_terms)
            doc_scores.append((doc, score))
        
        # 按得分降序排序
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in doc_scores]
    except Exception as e:
        print(f"重新排序文档时出错: {str(e)}")
        return docs  # 出错时返回原始文档顺序

def perform_query(input_query: str, kb_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    执行查询并返回回答与来源
    
    参数:
        input_query: 用户输入的查询
        kb_id: 知识库ID (可选)
        
    返回:
        Dict[str, Any]: 包含回答和源信息的响应对象，失败时返回None
    """
    if not input_query:
        return None
    
    try:
        # 初始化语言模型
        llm = ChatOllama(model=LLM_MODEL)
        
        # 获取向量数据库实例
        db = get_vector_db(kb_id)
        
        # 获取提示模板
        query_prompt, answer_prompt = get_prompt()

        # 设置多重查询检索器 - 增加检索数量以便后续重排
        retriever = MultiQueryRetriever.from_llm(
            retriever=db.as_retriever(search_kwargs={"k": 8}),  # 增加检索数量
            llm=llm,
            prompt=query_prompt
        )
        
        # 执行检索以获取相关文档
        retrieved_docs = retriever.get_relevant_documents(input_query)
        
        if not retrieved_docs:
            return {
                "answer": "抱歉，没有找到相关的信息来回答您的问题。",
                "sources": []
            }
        
        # 重新排序文档以提高相关性
        reranked_docs = rerank_documents(input_query, retrieved_docs)
        
        # 只使用前4个最相关的文档
        top_docs = reranked_docs[:4]
        
        # 格式化文档内容作为上下文
        context = "\n\n".join([doc.page_content for doc in top_docs])
        
        # 生成回答
        formatted_prompt = answer_prompt.format(context=context, question=input_query)
        raw_answer = llm.invoke(formatted_prompt).content
        
        # 清理响应
        clean_answer = clean_llm_response(raw_answer)
        
        # 获取并格式化源信息 (包含相关度分数)
        try:
            # 尝试获取嵌入向量以计算相关度
            from langchain_community.embeddings import OllamaEmbeddings
            embedding_model = OllamaEmbeddings(model="nomic-embed-text")
            query_embedding = embedding_model.embed_query(input_query)
            doc_embeddings = [embedding_model.embed_query(doc.page_content) for doc in top_docs]
            sources = format_sources(top_docs, query_embedding, doc_embeddings)
        except Exception as e:
            print(f"计算相关度分数时出错: {str(e)}")
            sources = format_sources(top_docs)
        
        # 组装最终响应
        response = {
            "answer": clean_answer,
            "sources": sources,
            "query": {
                "original": input_query,
                "kb_id": kb_id
            }
        }
        
        return response
    except Exception as e:
        print(f"执行查询时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return None