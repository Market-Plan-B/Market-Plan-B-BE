from faker import Faker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import random
from typing import Dict, List

from app.db.db_setting import (
    Base, User, Region, Content, Analytics, RecommendedStrategy,
    Notification, ChatSession, ChatMessage, ChatSuggestion,
    Report, ReportContent
)

DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5433/market-plan-b"

fake = Faker()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()


# -----------------------------------------------------------------
# Helper
# -----------------------------------------------------------------
def random_date(days=30):
    return datetime.now() - timedelta(days=random.randint(0, days))


def generate_features() -> Dict[str, List[float]]:
    """Analytics.features 구조에 맞게 feature1~feature3 생성"""
    return {
        "feature1": [round(random.uniform(-5, 0), 2), round(random.uniform(10, 60), 2)],
        "feature2": [round(random.uniform(-30, -5), 2), round(random.uniform(5, 20), 2)],
        "feature3": [round(random.uniform(-15, -3), 2), round(random.uniform(20, 40), 2)]
    }


# -----------------------------------------------------------------
# Seed Functions
# -----------------------------------------------------------------
def seed_users(n=5):
    users = []
    for _ in range(n):
        u = User(
            name=fake.name(),
            email=fake.unique.email(),
            password="hashed_password"
        )
        session.add(u)
        users.append(u)
    session.commit()
    return users


def seed_regions(n=5):
    regions = []
    existing_codes = {r.code for r in session.query(Region).all()}

    for _ in range(n):
        code = fake.country_code()

        # 중복 코드 피하기
        while code in existing_codes:
            code = fake.country_code()

        existing_codes.add(code)

        r = Region(
            name=fake.country(),
            code=code,
            region_score=round(random.uniform(0, 5), 2)
        )
        session.add(r)
        regions.append(r)

    session.commit()
    return regions



def seed_contents(regions, n=5):
    contents = []
    for _ in range(n):
        c = Content(
            region_id=random.choice(regions).id,
            title=fake.sentence(),
            summary=fake.text(),
            source_score=round(random.uniform(0, 3), 2),
            url=fake.url(),
            published_at=random_date(10)
        )
        session.add(c)
        contents.append(c)
    session.commit()
    return contents


def seed_analytics(n=5):
    analytics_list = []
    for i in range(n):
        a = Analytics(
            date=(datetime.now().date() - timedelta(days=i)),
            overall_score=round(random.uniform(1, 5), 2),
            features=generate_features(),
            variable_scores={"factor1": round(random.uniform(0, 1), 2)},
        )
        session.add(a)
        analytics_list.append(a)
    session.commit()
    return analytics_list


def seed_recommended_strategies(n=5):
    strategies = []
    for _ in range(n):
        s = RecommendedStrategy(
            date=datetime.now().date(),
            title=fake.sentence(),
            description=fake.text()
        )
        session.add(s)
        strategies.append(s)
    session.commit()
    return strategies


def seed_notifications(users, contents, n=5):
    items = []
    for _ in range(n):
        nt = Notification(
            user_id=random.choice(users).id,
            content_id=random.choice(contents).id,
            is_read=random.choice([True, False])
        )
        session.add(nt)
        items.append(nt)
    session.commit()
    return items


def seed_chat_sessions(users, n=5):
    sessions = []
    for _ in range(n):
        cs = ChatSession(
            user_id=random.choice(users).id,
            context={"topic": fake.word()}
        )
        session.add(cs)
        sessions.append(cs)
    session.commit()
    return sessions


def seed_chat_messages(sessions, n=5):
    messages = []

    # 먼저 각 세션에 메시지 1개씩 보장
    for s in sessions:
        m = ChatMessage(
            session_id=s.id,
            sender=random.choice(["user", "bot"]),
            message=fake.sentence()
        )
        session.add(m)
        messages.append(m)

    # 추가 메시지
    for _ in range(n):
        m = ChatMessage(
            session_id=random.choice(sessions).id,
            sender=random.choice(["user", "bot"]),
            message=fake.sentence()
        )
        session.add(m)
        messages.append(m)

    session.commit()
    return messages


def seed_chat_suggestions(sessions, messages, n=5):
    suggestions = []
    existing_pairs = set()

    # 기존 DB 값도 로드 (재실행 안정성)
    for s in sessions:
        for sg in s.suggestions:
            existing_pairs.add((sg.session_id, sg.message_id))

    tries = 0

    while len(suggestions) < n and tries < 50:
        tries += 1
        session_obj = random.choice(sessions)

        session_messages = [m for m in messages if m.session_id == session_obj.id]
        if not session_messages:
            continue

        msg = random.choice(session_messages)
        pair = (session_obj.id, msg.id)

        if pair in existing_pairs:
            continue

        sg = ChatSuggestion(
            session_id=session_obj.id,
            message_id=msg.id,
            suggestion=fake.sentence()
        )
        session.add(sg)
        suggestions.append(sg)
        existing_pairs.add(pair)

    session.commit()
    return suggestions


def seed_reports(n=5):
    reports = []
    for _ in range(n):
        r = Report(
            report_type=random.choice(["daily", "weekly"]),
            start_date=datetime.now().date(),
            end_date=datetime.now().date(),
            html_content="<h1>Dummy Report</h1><p>Generated Data</p>"
        )
        session.add(r)
        reports.append(r)
    session.commit()
    return reports


def seed_reports_contents(reports, contents, n=5):
    items = []

    # 이미 존재하는 pair 미리 로드 (재실행 대비)
    existing_pairs = set()
    for report in reports:
        for rc in report.contents:
            existing_pairs.add((rc.report_id, rc.content_id))

    tries = 0

    while len(items) < n and tries < 50:
        tries += 1

        report_obj = random.choice(reports)
        content_obj = random.choice(contents)

        pair = (report_obj.id, content_obj.id)

        # 이미 있는 pair 는 skip
        if pair in existing_pairs:
            continue

        rc = ReportContent(
            report_id=report_obj.id,
            content_id=content_obj.id
        )
        session.add(rc)
        items.append(rc)
        existing_pairs.add(pair)

    session.commit()
    return items



# -----------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------
def run_seed():
    print("🌱 Seeding dummy data...")

    users = seed_users()
    regions = seed_regions()
    contents = seed_contents(regions)
    analytics = seed_analytics()
    strategies = seed_recommended_strategies()
    notifications = seed_notifications(users, contents)

    sessions = seed_chat_sessions(users)
    messages = seed_chat_messages(sessions)
    seed_chat_suggestions(sessions, messages)

    reports = seed_reports()
    seed_reports_contents(reports, contents)

    print("✅ Dummy data inserted successfully!")


if __name__ == "__main__":
    run_seed()
