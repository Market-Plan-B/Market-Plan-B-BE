from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, Date, 
    DateTime, Numeric, JSON, ForeignKey, CheckConstraint, func
)
from sqlalchemy.orm import declarative_base, relationship

DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5433/market-plan-b"

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    session_token = Column(String(255), unique=True)
    session_expires_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    code = Column(String(10), unique=True, nullable=False)
    coordinates = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    contents = relationship("Content", back_populates="region", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="region", cascade="all, delete-orphan")


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    type = Column(String(30), nullable=False)
    source_url = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("type IN ('news_api','rss_feed','web_scraping','file_upload','social_api')", name="chk_data_source_type"),
    )

    contents = relationship("Content", back_populates="source", cascade="all, delete-orphan")
    analytics = relationship("Analytics", back_populates="source", cascade="all, delete-orphan")


class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"))
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="SET NULL"))
    content_type = Column(String(30), nullable=False)
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    content_text = Column(Text)
    s3_url = Column(String(1000))
    file_name = Column(String(255))
    file_size = Column(Integer)
    original_url = Column(String(500))
    published_at = Column(DateTime)
    sentiment_score = Column(Numeric(3, 2))
    impact_score = Column(Numeric(3, 2))
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("content_type IN ('news','research_pdf','briefing_doc','daily_report','weekly_report','social_post')", name="chk_content_type"),
    )

    source = relationship("DataSource", back_populates="contents")
    region = relationship("Region", back_populates="contents")
    notifications = relationship("Notification", back_populates="content")


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"))
    date = Column(Date, nullable=False)
    overall_score = Column(Numeric(3, 2))
    features = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    region = relationship("Region", back_populates="analytics")
    source = relationship("DataSource", back_populates="analytics")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content_id = Column(Integer, ForeignKey("contents.id", ondelete="SET NULL"))
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="notifications")
    content = relationship("Content", back_populates="notifications")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime)
    context = Column(JSON)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("sender IN ('user','bot','system')", name="chk_sender_type"),
    )

    session = relationship("ChatSession", back_populates="messages")


def init_db():
    print("🔄 Connecting to PostgreSQL on localhost:5433 ...")
    engine = create_engine(DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)
    print("✅ Tables created successfully in 'market-plan-b' database!")


if __name__ == "__main__":
    init_db()
