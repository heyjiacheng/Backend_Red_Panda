import fitz  # PyMuPDF
from typing import List

class DocumentParser:
    def __init__(self, chunk_size=512):
        self.chunk_size = chunk_size
        
    def parse_pdf(self, file_path: str) -> List[str]:
        """解析PDF文档并分块"""
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        
        # 简单分块逻辑
        chunks = [
            text[i:i+self.chunk_size] 
            for i in range(0, len(text), self.chunk_size)
        ]
        return chunks