"""전체 파이프라인 테스트"""
from datetime import datetime
from app.db.database import SessionLocal
from app.services.ai_service_full import run_full_pipeline

db = SessionLocal()

try:
    # JSON 파일 경로 지정 (임베딩이 포함된 파일 사용)
    json_path = "app/ai/data/extra_embedded (1).json"
    
    # 현재 시간으로 실행
    result = run_full_pipeline(db, datetime.now(), json_path)
    
    print(f"✅ 성공!")
    print(f"Analytics ID: {result['analytics'].id}")
    print(f"Strategies: {len(result['strategies'])}개")
    print(f"Report ID: {result['report'].id}")
    print(f"Contents: {len(result['contents'])}개")
    
except Exception as e:
    print(f"❌ 실패: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    db.close()
