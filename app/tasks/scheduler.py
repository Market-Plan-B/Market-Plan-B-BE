"""
APScheduler cron 방식으로 1시간마다 뉴스 크롤링 실행 (병렬 처리)
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from app.crawlers.oilprice_crawling import crawl_recent_pages
from app.crawlers.google_crawling import get_latest_google_news
from app.crawlers.investing_crawling import crawl_brent_news_hourly
from app.crawlers.pdf_crawling import download_crude_oil_pdfs

def run_oilprice():
    """OilPrice 크롤러 실행"""
    try:
        articles = crawl_recent_pages(max_pages=2)
        print(f"OilPrice: {len(articles)}개 기사 수집")
        return articles
    except Exception as e:
        print(f"OilPrice 크롤링 실패: {e}")
        return []

def run_google():
    """Google News 크롤러 실행"""
    try:
        articles = get_latest_google_news()
        print(f"Google News: {len(articles)}개 기사 수집")
        return articles
    except Exception as e:
        print(f"Google News 크롤링 실패: {e}")
        return []

def run_investing():
    """Investing.com 크롤러 실행"""
    try:
        articles = crawl_brent_news_hourly(start_page=1, end_page=2, concurrency=3)
        print(f"Investing.com: {len(articles)}개 기사 수집")
        return articles
    except Exception as e:
        print(f"Investing.com 크롤링 실패: {e}")
        return []

def run_pdf():
    """PDF 리포트 다운로드 실행"""
    try:
        download_crude_oil_pdfs()
        print("PDF 리포트 다운로드 완료")
    except Exception as e:
        print(f"PDF 리포트 다운로드 실패: {e}")

def run_crawlers():
    """병렬로 크롤러 실행하여 json 파일로 저장"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 병렬 크롤링 시작")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        oilprice_future = executor.submit(run_oilprice)
        google_future = executor.submit(run_google)
        investing_future = executor.submit(run_investing)
        pdf_future = executor.submit(run_pdf)

        oilprice_articles = oilprice_future.result()
        google_articles = google_future.result()
        investing_articles = investing_future.result()
        pdf_future.result()  # PDF 다운로드 결과 확인

    all_articles = oilprice_articles + google_articles + investing_articles
    
    if all_articles:
        print(f" 총 {len(all_articles)}개 기사 수집 완료")
        
        # 모델로 전송 (추후 구현)
        # send_to_model(all_articles)
        
        # 임시로 파일 저장
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(f'news_data_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)
    else:
        print(" 새로운 기사 없음")


def main():
    """메인 스케줄러"""
   
    scheduler = BlockingScheduler()
    
    # 매시 0분에 실행 (1시간마다)
    scheduler.add_job(
        run_crawlers,
        CronTrigger(minute=0),
        id='news_crawler',
        max_instances=1
    )
    
    # 시작 시 한 번 실행
    run_crawlers()
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n스케줄러 종료")
        scheduler.shutdown()

if __name__ == "__main__":
    main()