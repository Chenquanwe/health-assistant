from sqlalchemy import Column, String, DateTime, Text, func
from .base import Base, generate_uuid


class CheckReport(Base):
    __tablename__ = "check_reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False)
    conversation_id = Column(String, nullable=False)
    filename = Column(String(500))
    file_type = Column(String(20))
    file_path = Column(String(1000))
    analysis_result = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class HealthReport(Base):
    __tablename__ = "health_reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False)
    conversation_id = Column(String, nullable=False)
    content_markdown = Column(Text)
    file_path_pdf = Column(String(1000))
    risk_level = Column(String(10))
    created_at = Column(DateTime, server_default=func.now())


class ConsultationState(Base):
    __tablename__ = "consultation_state"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(String, unique=True, nullable=False)
    state_json = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())