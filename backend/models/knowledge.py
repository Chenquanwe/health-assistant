from sqlalchemy import Column, String, DateTime, Integer, Float, Text, func
from .base import Base, generate_uuid


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=True)
    title = Column(String(500), nullable=True)
    filename = Column(String(500), nullable=False)
    source = Column(String(50), nullable=True, default="user_upload")
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer)
    file_path = Column(String(1000))
    status = Column(String(20), default="processing")
    chunk_count = Column(Integer, default=0)
    quality_score = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class MedicalKnowledgeVector(Base):
    __tablename__ = "medical_knowledge_vectors"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String(255), nullable=True, index=True)
    chunk_index = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    # 以字符串形式存储 pgvector 向量，通过 CAST 转换
    embedding = Column(Text, nullable=False)
    source = Column(String(50), default="official")
    extra_metadata = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class UserKnowledgeConfig(Base):
    __tablename__ = "user_knowledge_config"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, unique=True, nullable=False)
    search_sources = Column(Text, default='["official"]')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
