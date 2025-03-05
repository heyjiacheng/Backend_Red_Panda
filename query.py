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
    if not response:
        return "抱歉，无法生成回答。"
    
    # 移除<think>...</think>块
    import re
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    
    # 移除其他可能的思考标记
    response = re.sub(r'\*\*思考：.*?\*\*', '', response, flags=re.DOTALL)
    response = re.sub(r'\*\*thinking:.*?\*\*', '', response, flags=re.DOTALL)
    response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
    
    # 移除常见的思考引导词
    response = re.sub(r'(^|\n)让我思考一下[.：:][^\n]*\n', '\n', response)
    response = re.sub(r'(^|\n)Let me think[.：:][^\n]*\n', '\n', response)
    
    # 移除XML和Markdown中常见的特殊标记
    response = re.sub(r'</?[a-zA-Z][^>]*>', '', response)  # XML标签
    
    # 处理可能的引用格式保持一致
    response = re.sub(r'```[a-zA-Z]*\n', '', response)  # 代码块开始标记
    response = re.sub(r'```\n?', '', response)  # 代码块结束标记
    
    # 处理换行，保证段落之间有适当的空白
    response = re.sub(r'\n{3,}', '\n\n', response)  # 多个换行替换为两个
    
    # 确保文本有适当的首尾格式
    response = response.strip()
    
    return response

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
        Dict[str, Any]: 包含回答和源信息的响应对象，失败时返回带有错误信息的字典
    """
    if not input_query:
        return {"error": "查询内容不能为空", "detail": "请提供一个有效的查询"}
    
    try:
        # 从环境变量获取模型名称，并尝试匹配已安装的模型
        import subprocess
        model_name = os.getenv('LLM_MODEL', 'deepseek-r1:14b')
        embedding_model_name = os.getenv('TEXT_EMBEDDING_MODEL', 'nomic-embed-text')
        
        print(f"使用语言模型: {model_name}")
        print(f"使用嵌入模型: {embedding_model_name}")
        
        # 验证知识库ID (如果提供)
        if kb_id is not None:
            from db_utils import check_knowledge_base_exists
            if not check_knowledge_base_exists(DB_PATH, kb_id):
                return {
                    "error": "知识库不存在",
                    "detail": f"ID为{kb_id}的知识库不存在"
                }
        
        # 初始化语言模型
        try:
            llm = ChatOllama(model=model_name)
        except Exception as model_error:
            print(f"初始化语言模型时出错: {str(model_error)}")
            # 尝试使用已安装的任意可用模型
            try:
                process = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
                models = process.stdout.strip().split('\n')[1:]  # 跳过标题行
                if models:
                    # 提取第一个可用模型的名称
                    available_model = models[0].split()[0]
                    print(f"尝试使用可用模型: {available_model}")
                    llm = ChatOllama(model=available_model)
                else:
                    return {
                        "error": "无法初始化语言模型",
                        "detail": f"指定的模型 {model_name} 不可用，且没有其他可用模型"
                    }
            except Exception as fallback_error:
                return {
                    "error": "无法初始化语言模型",
                    "detail": f"原始错误: {str(model_error)}, 回退错误: {str(fallback_error)}"
                }
        
        # 获取向量数据库实例
        try:
            db = get_vector_db(kb_id)
            # 检查向量数据库是否为空
            if hasattr(db, '_collection') and db._collection.count() == 0:
                return {
                    "error": "知识库为空",
                    "detail": f"知识库 {kb_id if kb_id else '默认'} 中没有文档，请先上传文档"
                }
        except Exception as db_error:
            print(f"获取向量数据库时出错: {str(db_error)}")
            return {
                "error": "无法访问向量数据库",
                "detail": str(db_error)
            }
        
        # 获取提示模板
        query_prompt, answer_prompt = get_prompt()

        # 设置多重查询检索器
        try:
            retriever = MultiQueryRetriever.from_llm(
                retriever=db.as_retriever(search_kwargs={"k": 8}),
                llm=llm,
                prompt=query_prompt
            )
        except Exception as retriever_error:
            print(f"创建检索器时出错: {str(retriever_error)}")
            return {
                "error": "无法创建文档检索器",
                "detail": str(retriever_error)
            }
        
        # 执行检索以获取相关文档
        try:
            retrieved_docs = retriever.get_relevant_documents(input_query)
        except Exception as retrieve_error:
            print(f"检索文档时出错: {str(retrieve_error)}")
            return {
                "error": "文档检索失败",
                "detail": str(retrieve_error)
            }
        
        if not retrieved_docs:
            return {
                "answer": "抱歉，没有找到相关的信息来回答您的问题。",
                "sources": [],
                "query": {
                    "original": input_query,
                    "kb_id": kb_id
                }
            }
        
        # 重新排序文档以提高相关性
        reranked_docs = rerank_documents(input_query, retrieved_docs)
        
        # 只使用前4个最相关的文档
        top_docs = reranked_docs[:4]
        
        # 格式化文档内容作为上下文
        context = "\n\n".join([doc.page_content for doc in top_docs])
        
        # 生成回答
        try:
            formatted_prompt = answer_prompt.format(context=context, question=input_query)
            raw_answer = llm.invoke(formatted_prompt).content
        except Exception as llm_error:
            print(f"生成回答时出错: {str(llm_error)}")
            return {
                "error": "无法生成回答",
                "detail": str(llm_error)
            }
        
        # 清理响应
        clean_answer = clean_llm_response(raw_answer)
        
        # 获取并格式化源信息 (包含相关度分数)
        try:
            # 尝试获取嵌入向量以计算相关度
            from langchain_community.embeddings import OllamaEmbeddings
            embedding_model = OllamaEmbeddings(model=embedding_model_name)
            query_embedding = embedding_model.embed_query(input_query)
            doc_embeddings = [embedding_model.embed_query(doc.page_content) for doc in top_docs]
            sources = format_sources(top_docs, query_embedding, doc_embeddings)
        except Exception as embed_error:
            print(f"计算相关度分数时出错: {str(embed_error)}")
            # 继续而不计算相关度分数
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
        return {
            "error": "查询执行失败",
            "detail": str(e)
        }