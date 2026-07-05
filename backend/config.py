import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

class Settings(BaseSettings):
    openai_api_key: str
    openai_base_url: str
    llm_model: str
    embedding_model: str
    database_url: str
    database_sync_url: str
    secret_key: str
    upload_dir: str = "uploads"
    dashscope_api_key: str = ""
    ocr_space_api_key: str = ""

    class Config:
        # 显式指定 .env 的绝对路径
        env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()