from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, Date,
    DateTime, Numeric, JSON, ForeignKey, func
)
from sqlalchemy.orm import declarative_base, relationship

DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5433/market-plan-b"

Base = declarative_base()

# ----------------------------
# USERS
# ----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
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
    code = Column(String(10), unique=True, nullable=False)
    region_score = Column(Numeric(3, 2))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    contents = relationship("Content", back_populates="region", cascade="all, delete-orphan")


# ----------------------------
# CONTENTS
# ----------------------------
class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="SET NULL"))
    title = Column(String(500), nullable=False)
    summary = Column(Text)
    source_score = Column(Numeric(3, 2))
    url = Column(String(500))
    published_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    region = relationship("Region", back_populates="contents")
    notifications = relationship("Notification", back_populates="content")
    report_links = relationship("ReportContent", back_populates="content", cascade="all, delete-orphan")


# ----------------------------
# ANALYTICS
# ----------------------------
class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    overall_score = Column(Numeric(3, 2))
    features = Column(JSON)
    variable_scores = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


# ----------------------------
# RECOMMENDED STRATEGIES
# ----------------------------
class RecommendedStrategy(Base):
    __tablename__ = "recommended_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255))
    horizon = Column(String(50))
    objective = Column(Text)
    preconditions = Column(Text)
    actions = Column(JSON)
    data_evidence = Column(JSON)
    risk_note = Column(Text)
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
# REPORTS
# ----------------------------
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    html_content = Column(Text, nullable=False)
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
# INIT DB
# ----------------------------
def init_db():
    print("🔄 Connecting to PostgreSQL on localhost:5433 ...")
    engine = create_engine(DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)
    print("✅ Tables created successfully!")


if __name__ == "__main__":
    init_db()
