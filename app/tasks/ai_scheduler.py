"""
AI 파이프라인 스케줄러
매 시간마다 실행하여 전날 06시~당일 06시 뉴스 데이터로 AI 모델링 수행
"""
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

from app.db.database import SessionLocal
from app.services.ai_service_full import run_full_pipeline

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app/tasks/ai_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_ai_pipeline_job():
    """
    AI 파이프라인 실행 작업
    크롤링된 JSON 파일에서 24시간 뉴스 로드
    """
    db = SessionLocal()
    
    try:
        current_time = datetime.now()
        logger.info(f"AI 파이프라인 시작: {current_time}")
        
        # 크롤링된 JSON 파일 경로 (날짜별 파일명)
        date_str = current_time.strftime("%Y%m%d")
        json_path = f"app/ai/repository/data/news/news_{date_str}.json"
        
        # AI 파이프라인 실행
        result = run_full_pipeline(db, current_time, json_path)
        
        logger.info(f"AI 파이프라인 완료: analytics_id={result['analytics'].id}, "
                   f"strategies_count={len(result['strategies'])}, report_id={result['report'].id}, "
                   f"contents_count={len(result['contents'])}")
        
    except Exception as e:
        logger.error(f"AI 파이프라인 실행 실패: {str(e)}", exc_info=True)
        
    finally:
        db.close()


def start_ai_scheduler():
    """
    스케줄러 시작
    매 시간마다 AI 파이프라인 실행
    """
    scheduler = BackgroundScheduler()
    
    # 매 시간 정각에 실행
    scheduler.add_job(
        run_ai_pipeline_job,
        trigger='cron',
        hour='*',  # 매 시간
        minute=0,  # 정각
        id='ai_pipeline_job',
        name='AI 파이프라인 실행',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("AI 스케줄러 시작됨 (매 시간 정각 실행)")
    
    return scheduler


if __name__ == "__main__":
    # 스케줄러 시작
    scheduler = start_ai_scheduler()
    
    # 즉시 한 번 실행 (테스트용)
    logger.info("테스트 실행 시작...")
    run_ai_pipeline_job()
    
    # 스케줄러 유지
    try:
        import time
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("AI 스케줄러 종료됨")
