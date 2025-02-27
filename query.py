import os
from langchain_community.chat_models import ChatOllama
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain.retrievers.multi_query import MultiQueryRetriever
from get_vector_db import get_vector_db

# 使用环境变量配置
LLM_MODEL = os.getenv('LLM_MODEL', 'mistral')

def get_prompt():
    """获取提示模板"""
    # 多重查询提示模板
    query_prompt = PromptTemplate(
        input_variables=["question"],
        template="""你是一个AI语言模型助手。你的任务是为给定的用户问题生成五个
        不同版本的问题，以便从向量数据库中检索相关文档。通过生成多种视角的用户问题，
        你的目标是帮助用户克服基于距离的相似度搜索的一些局限性。请提供这些替代问题，
        每个问题用换行符分隔。
        原始问题: {question}""",
    )

    # 回答提示模板
    answer_prompt = ChatPromptTemplate.from_template("""请仅根据以下提供的上下文回答问题:
    {context}
    问题: {question}
    """)

    return query_prompt, answer_prompt

def perform_query(input_query, kb_id=None):
    """执行查询并返回回答"""
    if not input_query:
        return None
    
    try:
        # 初始化语言模型
        llm = ChatOllama(model=LLM_MODEL)
        
        # 获取向量数据库实例
        db = get_vector_db(kb_id)
        
        # 获取提示模板
        query_prompt, answer_prompt = get_prompt()

        # 设置多重查询检索器
        retriever = MultiQueryRetriever.from_llm(
            db.as_retriever(), 
            llm,
            prompt=query_prompt
        )

        # 定义处理链
        chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | answer_prompt
            | llm
            | StrOutputParser()
        )

        # 执行查询
        response = chain.invoke(input_query)
        return response
    except Exception as e:
        print(f"执行查询时发生错误: {str(e)}")
        return None