"""
APScheduler cron 방식으로 1시간마다 뉴스 크롤링 실행 (병렬 처리)
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import asyncio
from app.crawlers.oilprice_crawling import crawl_recent_pages
from app.crawlers.google_crawling import get_latest_google_news
from app.crawlers.investing_crawling import crawl_brent_news_hourly
from app.crawlers.pdf_crawling import download_crude_oil_pdfs
from app.crawlers.yahoo_crawling import YahooFinanceNewsScraperPlaywright

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
        import asyncio
        articles = asyncio.run(crawl_brent_news_hourly(start_page=1, end_page=2, concurrency=3))
        print(f"Investing.com: {len(articles)}개 기사 수집")
        return articles
    except Exception as e:
        print(f"Investing.com 크롤링 실패: {e}")
        return []

def run_yahoo():
    """Yahoo Finance 크롤러 실행"""
    try:
        scraper = YahooFinanceNewsScraperPlaywright()
        df = scraper.scrape_news(scroll_count=15, max_articles=200, headless=True)
        articles = df.to_dict('records') if not df.empty else []
        print(f"Yahoo Finance: {len(articles)}개 기사 수집")
        return articles
    except Exception as e:
        print(f"Yahoo Finance 크롤링 실패: {e}")
        return []

def run_pdf():
    """PDF 리포트 다운로드 실행"""
    try:
        download_crude_oil_pdfs()
        print("PDF 리포트 다운로드 완료")
    except Exception as e:
        print(f"PDF 리포트 다운로드 실패: {e}")

def run_single_crawler(crawler_func, timeout=2700):  
    """단일 크롤러를 타임아웃과 함께 실행"""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(crawler_func)
            return future.result(timeout=timeout)
    except TimeoutError:
        print(f" {crawler_func.__name__} 타임아웃 (45분 초과)")
        return []
    except Exception as e:
        print(f" {crawler_func.__name__} 오류: {e}")
        return []

def run_crawlers():
    """병렬로 크롤러 실행하여 json 파일로 저장"""
    print(f"\n{'='*80}")
    print(f" [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 크롤링 시작")
    print(f"{'='*80}")
    
    # 병렬 실행 
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            'oilprice': executor.submit(run_single_crawler, run_oilprice, 2700),
            'google': executor.submit(run_single_crawler, run_google, 2700), 
            'investing': executor.submit(run_single_crawler, run_investing, 2700),
            'yahoo': executor.submit(run_single_crawler, run_yahoo, 2700),
            'pdf': executor.submit(run_single_crawler, run_pdf, 900)
        }
        
        # 결과 수집
        oilprice_articles = futures['oilprice'].result()
        google_articles = futures['google'].result()
        investing_articles = futures['investing'].result()
        yahoo_articles = futures['yahoo'].result()
        futures['pdf'].result()  

    all_articles = oilprice_articles + google_articles + investing_articles + yahoo_articles
    
    print(f"\n{'='*60}")
    print(f" 최종 결과: 총 {len(all_articles)}개 기사 수집 완료")
    print(f"{'='*60}")
    
    # 무조건 JSON 파일 생성 (비어있어도)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'news_data_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    
    if all_articles:
        print(f" 데이터 저장: {filename}")
    else:
        print(f" 빈 파일 생성: {filename}")


def main():
    """메인 스케줄러"""
   
    scheduler = BlockingScheduler()
    
    # 매시 0분에 실행 
    scheduler.add_job(
        run_crawlers,
        CronTrigger(minute=0),
        id='news_crawler',
        max_instances=1,
        misfire_grace_time=3600,  # 1시간 지연까지 허용
        coalesce=True  # 누락된 작업들을 하나로 합침
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