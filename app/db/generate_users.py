from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User
from app.db.database import DATABASE_URL
import random

def generate_users():
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    surnames = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신", "권", "황", "안", "송", "류", "전"]
    given_names = ["민준", "서준", "도윤", "예준", "시우", "하준", "주원", "지호", "지후", "준서", "건우", "현우", "민재", "준혁", "지훈", "서연", "서윤", "지우", "서현", "민서", "하은", "윤서", "지유", "채원", "지민", "수아", "다은", "예은", "소율", "예린"]
    
    users = []
    for i in range(1, 301):
        emp_id = f"EMP{i:04d}"
        email = f"users{i:03d}@company.com"
        name = random.choice(surnames) + random.choice(given_names)
        
        user = User(
            name=name,
            email=email,
            password=emp_id
        )
        users.append(user)
    
    session.add_all(users)
    session.commit()
    session.close()
    print("✅ 300명의 사용자 데이터가 생성되었습니다.")

if __name__ == "__main__":
    generate_users()