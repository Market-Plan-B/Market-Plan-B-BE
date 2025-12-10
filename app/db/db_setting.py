from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, Date,
    DateTime, Numeric, JSON, ForeignKey, func, Enum
)
from sqlalchemy.orm import declarative_base, relationship
import os
from dotenv import load_dotenv

load_dotenv()
# DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5433/market-plan-b"
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "market-plan-b")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

Base = declarative_base()

# ----------------------------
# USERS
# ----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(Enum('admin', 'user', 'ADMIN', 'USER', name='user_role'), nullable=False, default='user')
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    refresh_token = Column(String(500), nullable=True)
    refresh_token_expire = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


# ----------------------------
# REGIONS
# ----------------------------
class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    code = Column(String(10), nullable=False)
    region_score = Column(Numeric(3, 2))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ----------------------------
# CONTENTS (뉴스 데이터 저장)
# ----------------------------
class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)  # 뉴스 제목
    summary = Column(Text)  # 뉴스 요약
    source_score = Column(Numeric(3, 2))  # 감정/신뢰도 점수
    url = Column(String(500))  # 뉴스 URL
    published_at = Column(DateTime)  # 뉴스 발행 시간
    created_at = Column(DateTime, server_default=func.now())

    notifications = relationship("Notification", back_populates="content")
    report_links = relationship("ReportContent", back_populates="content", cascade="all, delete-orphan")


# ----------------------------
# ANALYTICS (AI 예측 결과 저장)
# ----------------------------
class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    overall_score = Column(Numeric(3, 2))  # 예측 수익률
    features = Column(JSON)  # XAI 피처 중요도
    created_at = Column(DateTime, server_default=func.now())


# ----------------------------
# RECOMMENDED STRATEGIES (AI 대응책 저장)
# ----------------------------
class RecommendedStrategy(Base):
    __tablename__ = "recommended_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # 전략 이름
    horizon = Column(String(50), nullable=False)  # 기간 (1-3일, 1주 등)
    objective = Column(Text, nullable=False)  # 목표
    preconditions = Column(Text)  # 선행 조건
    actions = Column(JSON, nullable=False)  # 행동 목록
    data_evidence = Column(JSON, nullable=False)  # 데이터 근거
    risk_note = Column(Text)  # 리스크 메모
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ----------------------------
# NOTIFICATIONS
# ----------------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content_id = Column(Integer, ForeignKey("contents.id", ondelete="SET NULL"))
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="notifications")
    content = relationship("Content", back_populates="notifications")


# ----------------------------
# CHAT SESSIONS
# ----------------------------
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime)
    context = Column(JSON)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    suggestions = relationship("ChatSuggestion", back_populates="session", cascade="all, delete-orphan")


# ----------------------------
# CHAT MESSAGES
# ----------------------------
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")
    suggestions = relationship("ChatSuggestion", back_populates="message", cascade="all, delete-orphan")


# ----------------------------
# CHAT SUGGESTIONS
# ----------------------------
class ChatSuggestion(Base):
    __tablename__ = "chat_suggestions"

    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True)
    suggestion = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("ChatSession", back_populates="suggestions")
    message = relationship("ChatMessage", back_populates="suggestions")


# ----------------------------
# REPORTS (AI 일일 리포트 저장)
# ----------------------------
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(20), nullable=False)  # 'daily' 고정
    start_date = Column(Date, nullable=False)  # 리포트 날짜
    end_date = Column(Date, nullable=False)  # 리포트 날짜 (start_date와 동일)
    html_content = Column(Text, nullable=False)  # AI 생성 HTML 리포트
    images = Column(JSON, nullable=False)  # 카드뉴스 이미지 base64 배열 (daily만 사용)
    created_at = Column(DateTime, server_default=func.now())

    contents = relationship("ReportContent", back_populates="report", cascade="all, delete-orphan")


# ----------------------------
# REPORT-CONTENTS RELATION
# ----------------------------
class ReportContent(Base):
    __tablename__ = "reports_contents"

    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    content_id = Column(Integer, ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, server_default=func.now())

    report = relationship("Report", back_populates="contents")
    content = relationship("Content", back_populates="report_links")


# ----------------------------
# CONTENT-REGION RELATION (다대다)
# ----------------------------
class ContentRegion(Base):
    __tablename__ = "contents_regions"

    content_id = Column(Integer, ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, server_default=func.now())


# ----------------------------
# CRAWLING SOURCES
# ----------------------------
class CrawlingSource(Base):
    __tablename__ = "crawling_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_url = Column(String(500), nullable=False)
    source_name = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ----------------------------
# CRAWLING CATEGORIES
# ----------------------------
class CrawlingCategory(Base):
    __tablename__ = "crawling_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ----------------------------
# INIT DB
# ----------------------------
def init_db():
    print(f"🔄 Connecting to PostgreSQL at {DB_HOST}:{DB_PORT}/{DB_NAME} ...")
    engine = create_engine(DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)
    print("✅ Tables created successfully!")


if __name__ == "__main__":
    init_db()
