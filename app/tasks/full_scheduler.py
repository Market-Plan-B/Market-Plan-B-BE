"""
통합 스케줄러: 크롤링 → AI 모델링 파이프라인
매 시간 정각에 실행
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json
import logging

from app.crawlers.oilprice_crawling import crawl_oilprice_last_hour
from app.crawlers.google_crawling import get_latest_google_news
from app.crawlers.investing_crawling import crawl_brent_news_hourly
from app.crawlers.yahoo_crawling import YahooFinanceNewsScraper
from app.db.database import SessionLocal
from app.db.db_setting import Notification, User
from app.services.ai_service import run_full_pipeline, load_news_from_json, save_contents, save_regions, update_region_scores, create_notification
from app.models.crawling_source import CrawlingSource
from app.models.crawling_category import CrawlingCategory
from app.services.weekly_service import generate_weekly_report

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app/tasks/full_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_single_crawler(crawler_func, timeout=2700):
    """단일 크롤러 실행"""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(crawler_func)
            return future.result(timeout=timeout)
    except TimeoutError:
        logger.warning(f"{crawler_func.__name__} 타임아웃")
        return []
    except Exception as e:
        logger.error(f"{crawler_func.__name__} 실패: {e}")
        return []


def run_oilprice():
    try:
        articles = crawl_oilprice_last_hour(max_pages=2)
        logger.info(f"OilPrice: {len(articles)}개")
        return articles
    except Exception as e:
        logger.error(f"OilPrice 실패: {e}")
        return []


def run_google():
    try:
        articles = get_latest_google_news()
        logger.info(f"Google: {len(articles)}개")
        return articles
    except Exception as e:
        logger.error(f"Google 실패: {e}")
        return []


def run_investing():
    try:
        import asyncio
        articles = asyncio.run(crawl_brent_news_hourly(start_page=1, end_page=2))
        logger.info(f"Investing: {len(articles)}개")
        return articles
    except Exception as e:
        logger.error(f"Investing 실패: {e}")
        return []





def run_yahoo():
    try:
        scraper = YahooFinanceNewsScraper()
        df = scraper.scrape_news(max_articles=300)
        articles = df.to_dict('records') if not df.empty else []
        logger.info(f"Yahoo: {len(articles)}개")
        return articles
    except Exception as e:
        logger.error(f"Yahoo 실패: {e}")
        return []


def get_active_sources(db):
    """is_active=true인 크롤링 소스 조회"""
    try:
        sources = db.query(CrawlingSource).filter(CrawlingSource.is_active == True).all()
        active_sources = {source.source_name.lower(): source.base_url for source in sources}
        logger.info(f"활성화된 크롤링 소스: {list(active_sources.keys())}")
        return active_sources
    except Exception as e:
        logger.error(f"크롤링 소스 조회 실패: {e}")
        return {}

def crawl_all_news():
    """모든 크롤러 병렬 실행 → JSON 저장"""
    logger.info("=" * 80)
    logger.info("크롤링 시작")
    logger.info("=" * 80)
    
    # 활성화된 소스 확인
    db = SessionLocal()
    try:
        active_sources = get_active_sources(db)
    finally:
        db.close()
    
    if not active_sources:
        logger.warning("활성화된 크롤링 소스가 없습니다")
        return None, []
    
    # 활성화된 소스만 크롤링
    futures = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        if 'oilprice' in active_sources:
            futures['oilprice'] = executor.submit(run_single_crawler, run_oilprice, 600)
        if 'google' in active_sources:
            futures['google'] = executor.submit(run_single_crawler, run_google, 600)
        if 'yahoo' in active_sources:
            futures['yahoo'] = executor.submit(run_single_crawler, run_yahoo, 600)
        
        oilprice = futures.get('oilprice').result(timeout=700) if 'oilprice' in futures else []
        google = futures.get('google').result(timeout=700) if 'google' in futures else []
        investing = []  # 임시로 빈 배열
        yahoo = futures.get('yahoo').result(timeout=700) if 'yahoo' in futures else []
    
    all_articles = []
    for name, articles in [('oilprice', oilprice), ('google', google), ('investing', investing), ('yahoo', yahoo)]:
        if articles:
            all_articles.extend(articles)
            logger.info(f"{name}: {len(articles)}개 수집")
    
    logger.info(f"총 {len(all_articles)}개 기사 수집")
    
    # JSON 저장
    import os
    date_str = datetime.now().strftime('%Y%m%d')
    json_dir = 'app/ai/repository/data/news'
    json_path = f'{json_dir}/news_{date_str}.json'
    
    try:
        os.makedirs(json_dir, exist_ok=True)
        logger.info(f"디렉토리 확인/생성: {json_dir}")
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON 저장 완료: {json_path} ({len(all_articles)}개 기사)")
        
    except Exception as e:
        logger.error(f"JSON 저장 실패: {e}", exc_info=True)
        raise
    
    return json_path, all_articles


def filter_by_active_categories(db, news_list):
    """is_active=true인 카테고리만 필터링"""
    try:
        active_categories = db.query(CrawlingCategory).filter(CrawlingCategory.is_active == True).all()
        active_category_names = {cat.category for cat in active_categories}
        logger.info(f"활성화된 카테고리: {active_category_names}")
        
        filtered_news = []
        for news in news_list:
            category = news.get("category")
            if category in active_category_names:
                filtered_news.append(news)
            else:
                logger.debug(f"카테고리 필터링 제외: {category} - {news.get('title', '')[:50]}")
        
        logger.info(f"카테고리 필터링: {len(news_list)}개 → {len(filtered_news)}개")
        return filtered_news
    except Exception as e:
        logger.error(f"카테고리 필터링 실패: {e}")
        return news_list

def save_hourly_contents(json_path):
    """1시간마다 크롤링 데이터를 contents에만 저장"""
    import gc
    db = SessionLocal()
    
    try:
        logger.info("Contents 저장 시작")
        
        from app.ai.services.unstructured_summary import daily_news_data
        raw_news = load_news_from_json(json_path)
        
        if not raw_news:
            logger.warning("뉴스 데이터가 없습니다")
            return
        
        if raw_news and "summary_embedding" in raw_news[0]:
            # 기존 임베딩 검증
            valid_count = sum(1 for n in raw_news if isinstance(n.get("summary_embedding"), list) and len(n.get("summary_embedding", [])) == 64)
            if valid_count / len(raw_news) >= 0.5:
                news_list = raw_news
                logger.info(f"기존 임베딩 재사용 ({valid_count}/{len(raw_news)} 유효)")
            else:
                logger.warning(f"기존 임베딩 무효 ({valid_count}/{len(raw_news)}) → 재생성")
                news_list = daily_news_data(raw_news)
        else:
            logger.info("뉴스 처리 시작 (메모리 집약적)")
            try:
                news_list = daily_news_data(raw_news)
            except Exception as e:
                logger.error(f"뉴스 처리 실패: {e}", exc_info=True)
                return
            gc.collect()
        
        # 활성화된 카테고리만 필터링
        news_list = filter_by_active_categories(db, news_list)
        
        try:
            save_regions(db, news_list)
        except Exception as e:
            logger.error(f"Region 저장 실패: {e}", exc_info=True)
        
        try:
            saved_contents = save_contents(db, news_list)
        except Exception as e:
            logger.error(f"Content 저장 실패: {e}", exc_info=True)
            saved_contents = []
        
        try:
            update_region_scores(db, news_list)
        except Exception as e:
            logger.error(f"Region 점수 업데이트 실패: {e}", exc_info=True)

        # 알림 생성
        try:
            impact_threshold = 0.8
            users = db.query(User).all()
            
            for content in saved_contents:
                try:
                    score = float(content.source_score)
                except Exception as e:
                    logger.error(f"[SCORE ERROR] invalid score: {content.source_score} ({e})")
                    continue

                if score >= impact_threshold:
                    for user in users:
                        try:
                            create_notification(db, user.id, content.id)
                            logger.info(f"[알림 생성] user={user.id}, content={content.id}, score={score}")
                        except Exception as e:
                            logger.error(f"알림 생성 실패: {e}")
        except Exception as e:
            logger.error(f"알림 처리 실패: {e}", exc_info=True)

        # ChromaDB에 저장
        try:
            from app.services.ai_service import save_to_chroma
            save_to_chroma(news_list)
        except Exception as e:
            logger.error(f"ChromaDB 저장 실패: {e}", exc_info=True)
        
        logger.info(f"Contents 저장 완료: {len(saved_contents)}개")
        
    except Exception as e:
        logger.error(f"Contents 저장 실패: {e}", exc_info=True)
    finally:
        db.close()
        gc.collect()


def run_ai_pipeline(json_path):
    """24시간 데이터로 전체 AI 파이프라인 실행"""
    db = SessionLocal()
    
    try:
        logger.info("전체 AI 파이프라인 시작")
        
        result = run_full_pipeline(db, datetime.now(), json_path)
        
        logger.info(f"AI 파이프라인 완료: analytics_id={result['analytics'].id}, "
                   f"strategies={len(result['strategies'])}, "
                   f"report_id={result['report'].id}, "
                   f"contents={len(result['contents'])}")
        
        return result
        
    except Exception as e:
        logger.error(f"AI 파이프라인 실패: {e}", exc_info=True)
        
    finally:
        db.close()


def hourly_job():
    """1시간마다: 크롤링 → contents 저장"""
    logger.info("=== hourly_job 시작 ===")
    try:
        json_path, articles = crawl_all_news()
        
        if not articles:
            logger.warning("크롤링된 기사가 없습니다")
            return
        
        logger.info(f"JSON 파일 경로: {json_path}")
        save_hourly_contents(json_path)
        
        logger.info("=== hourly_job 완료 ===")
        
    except Exception as e:
        logger.error(f"hourly_job 실패: {e}", exc_info=True)


def daily_job():
    """24시간마다: 전체 AI 파이프라인 실행"""
    logger.info("=== daily_job 시작 ===")
    try:
        import os
        date_str = datetime.now().strftime('%Y%m%d')
        json_path = f'app/ai/repository/data/news/news_{date_str}.json'
        
        if not os.path.exists(json_path):
            logger.error(f"24시간 데이터 파일 없음: {json_path}")
            return
        
        logger.info(f"JSON 파일 발견: {json_path}")
        result = run_ai_pipeline(json_path)
        
        logger.info("=" * 80)
        logger.info("=== daily_job 완료 ===")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"daily_job 실패: {e}", exc_info=True)


def weekly_job():
    """매주 목요일: 7일치 데이터로 주간 리포트 생성"""
    db = SessionLocal()
    
    try:
        logger.info("=" * 80)
        logger.info("주간 리포트 생성 시작")
        logger.info("=" * 80)
        
        end_date = datetime.now()
        weekly_report = generate_weekly_report(db, end_date)
        
        logger.info(f"주간 리포트 생성 완료: id={weekly_report.id}, "
                   f"기간={weekly_report.start_date} ~ {weekly_report.end_date}")
        
    except Exception as e:
        logger.error(f"주간 리포트 생성 실패: {e}", exc_info=True)
    finally:
        db.close()


def main():
    """스케줄러 시작"""
    scheduler = BlockingScheduler()
    
    # 매 시간 정각: 크롤링 + contents 저장
    scheduler.add_job(
        hourly_job,
        CronTrigger(minute=0),
        id='hourly_crawl',
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True
    )
    
    # 매일 자정: 24시간 데이터로 전체 파이프라인
    scheduler.add_job(
        daily_job,
        CronTrigger(hour=0, minute=30),
        id='daily_pipeline',
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True
    )
    
    # 매주 목요일 오전 1시: 주간 리포트 생성
    scheduler.add_job(
        weekly_job,
        CronTrigger(day_of_week='thu', hour=1, minute=0),
        id='weekly_report',
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True
    )
    
    logger.info("통합 스케줄러 시작")
    logger.info(f"현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("- 매 시간 0분: 크롤링 + contents 저장 + Chroma DB 저장")
    logger.info("- 매일 00:30: 전체 AI 파이프라인")
    logger.info("- 매주 목요일 01:00: 주간 리포트 생성")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("스케줄러 종료")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
