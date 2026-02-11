from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    openai_api_key: str
    mongodb_url: str = "mongodb://localhost:27017"
    database_name: str = "legal_indexer"
    chroma_persist_dir: str = "./chroma_db"
    log_level: str = "INFO"
    embedding_model: str = "text-embedding-3-small"
    analysis_model: str = "gpt-4o-mini"  # Changed from gpt-4o
    chunk_size: int = 1000  # Increased from 800
    chunk_overlap: int = 300  # Reduced from 200
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()