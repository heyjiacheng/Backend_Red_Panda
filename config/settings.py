import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    UPLOAD_FOLDER = 'data/docs'
    ALLOWED_EXTENSIONS = {'pdf'}
    EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'