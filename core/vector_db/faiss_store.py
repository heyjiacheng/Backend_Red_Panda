import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List

class VectorStore:
    def __init__(self):
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.index = None
        self.documents = []
        
    def create_index(self, dimension=384):
        self.index = faiss.IndexFlatL2(dimension)
        
    def add_documents(self, chunks: List[str]):
        embeddings = self.model.encode(chunks)
        if not self.index:
            self.create_index(embeddings.shape[1])
        self.index.add(embeddings.astype(np.float32))
        self.documents.extend(chunks)
        
    def search(self, query: str, k=5) -> List[str]:
        query_embed = self.model.encode([query])
        distances, indices = self.index.search(query_embed, k)
        return [self.documents[i] for i in indices[0]]
    
    def get_vector_stats(self):
        """获取向量存储统计信息"""
        if not self.index:
            return "索引未初始化"
            
        return {
            "vector_number": self.index.ntotal,
            "vector_dimension": self.index.d,
        }