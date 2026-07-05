from sqlalchemy import Column, String, DateTime, ForeignKey, Text, func, JSON
from sqlalchemy.orm import relationship
from .base import Base, generate_uuid


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String(200))
    status = Column(String(20), default="active")
    workflow_state = Column(JSON, nullable=True)  # 保存 LangGraph 工作流状态
    uploaded_files = Column(JSON, nullable=True)  # 保存已上传文件信息
    current_node = Column(String(50), nullable=True)  # 当前工作流节点
    last_activity = Column(DateTime, server_default=func.now(), onupdate=func.now())  # 最后活动时间
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    messages = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text)
    message_type = Column(String(20), default="text")
    metadata_json = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")