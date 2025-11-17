from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timezone, timedelta
import json
import time
import redis

# Redis 설정
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
REDIS_KEY = "yahoo_news_urls"

class YahooFinanceNewsScraperPlaywright:
    def __init__(self):
        self.base_url = "https://finance.yahoo.com"
        self.news_url = "https://finance.yahoo.com/news/"
    
    def scroll_and_collect_links(self, page, scroll_count=30, scroll_pause=1.5):
        """
        페이지를 스크롤하면서 뉴스 링크 수집
        """
        print(f"🔍 Yahoo Finance 뉴스 페이지 접속 중...")
        page.goto(self.news_url, wait_until='domcontentloaded')
        time.sleep(2)
        news_links = set()
        
        print(f"📜 페이지 스크롤 시작 (최대 {scroll_count}회)...")
        
        for i in range(scroll_count):
            links = page.query_selector_all('a[href*="/news/"]')
            
            for link in links:
                try:
                    href = link.get_attribute('href')
                    if href and '/news/' in href and '.html' in href:
                        if href.startswith('/'):
                            full_url = f"https://finance.yahoo.com{href}"
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue
                        
                        clean_url = full_url.split('?')[0].rstrip('/')
                        news_links.add(clean_url)
                except:
                    continue
            
            print(f"   스크롤 {i+1}/{scroll_count}: {len(news_links)}개 링크 발견")
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(scroll_pause)
        
        print(f"총 {len(news_links)}개의 고유한 뉴스 링크를 찾았습니다.")
        return list(news_links)
    
    def parse_article(self, page, url):
        """개별 뉴스 기사 파싱"""
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
            time.sleep(1)
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            article_data = {
                'url': url,
                'title': None,
                'content': None,
                'published_date': None
            }
            
            # 제목 추출
            title_tag = soup.find('h1')
            if title_tag:
                article_data['title'] = title_tag.get_text(strip=True)
            
            if not article_data['title'] or article_data['title'] == 'Yahoo Finance':
                meta_title = soup.find('meta', {'property': 'og:title'})
                if meta_title:
                    article_data['title'] = meta_title.get('content', '').strip()
            
            if not article_data['title'] or article_data['title'] == 'Yahoo Finance':
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text(strip=True)
                    title_text = title_text.replace(' - Yahoo Finance', '').replace('Yahoo Finance', '').strip()
                    if title_text:
                        article_data['title'] = title_text
            
            # 본문 추출
            content_parts = []
            article_tag = soup.find('article')
            if article_tag:
                paragraphs = article_tag.find_all('p')
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and len(text) > 20:
                        content_parts.append(text)
            
            if not content_parts:
                caas_body = soup.find('div', class_=lambda x: x and 'caas-body' in x)
                if caas_body:
                    paragraphs = caas_body.find_all('p')
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 20:
                            content_parts.append(text)
            
            article_data['content'] = '\n\n'.join(content_parts) if content_parts else None
            
            # 발행일 추출
            time_tags = soup.find_all('time')
            for tag in time_tags:
                datetime_attr = tag.get('datetime')
                if datetime_attr:
                    try:
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        # UTC로 저장
                        article_data['published_date'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                        break
                    except:
                        continue
            
            if not article_data['published_date']:
                meta_date = soup.find('meta', {'property': 'article:published_time'})
                if meta_date:
                    content = meta_date.get('content')
                    if content:
                        try:
                            dt = datetime.fromisoformat(content.replace('Z', '+00:00'))
                            article_data['published_date'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except:
                            pass
            
            return article_data
            
        except PlaywrightTimeout:
            print(f" 타임아웃: {url}")
            return None
        except Exception as e:
            print(f" 파싱 실패: {e}")
            return None
    
    def filter_by_kst_range(self, articles_df):
        """
        한국 시간 기준으로 필터링
        Yahoo Finance 뉴스는 한국 시간(GMT+9)으로 표시됨
        전날 06:00 ~ 당일 06:00 (KST) 필터링
        """
        if articles_df.empty:
            return articles_df
        
        # 현재 한국 시간
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        
        # 한국 시간 기준 당일 06:00
        end_time_kst = now_kst.replace(hour=6, minute=0, second=0, microsecond=0)
        
        # 한국 시간 기준 전날 06:00
        start_time_kst = end_time_kst - timedelta(days=1)
        
        # 만약 현재 시간이 오늘 06:00 이전이면, 하루 전으로 조정
        if now_kst.hour < 6:
            start_time_kst = start_time_kst - timedelta(days=1)
            end_time_kst = end_time_kst - timedelta(days=1)
        
        print(f"\n시간 범위 설정 (한국 시간 기준):")
        print(f"   KST: {start_time_kst.strftime('%Y-%m-%d %H:%M')} ~ {end_time_kst.strftime('%Y-%m-%d %H:%M')}")
        print(f"   (Yahoo Finance 뉴스는 GMT+9로 표시됩니다)")
        
        # published_date를 datetime으로 변환 (UTC로 파싱 후 KST로 변환)
        def parse_datetime(date_str):
            if pd.isna(date_str):
                return None
            try:
                # 'YYYY-MM-DD HH:MM:SS UTC' 형식을 UTC로 파싱
                dt = datetime.strptime(date_str.split(' UTC')[0], '%Y-%m-%d %H:%M:%S')
                # UTC 시간대 설정 후 KST로 변환
                dt_utc = dt.replace(tzinfo=timezone.utc)
                dt_kst = dt_utc.astimezone(kst)
                return dt_kst
            except:
                return None
        
        articles_df['parsed_datetime'] = articles_df['published_date'].apply(parse_datetime)
        
        # 날짜 분포 출력 (KST 기준)
        print(f"\n📊 발견된 기사 시간 분포 (상위 10개, KST):")
        valid_dates = articles_df[articles_df['parsed_datetime'].notna()]['parsed_datetime']
        if len(valid_dates) > 0:
            for idx, dt in enumerate(sorted(valid_dates, reverse=True)[:10]):
                if dt:
                    print(f"   - {dt.strftime('%Y-%m-%d %H:%M:%S KST')}")
            if len(valid_dates) > 10:
                print(f"   ... 외 {len(valid_dates) - 10}개")
        
        original_count = len(articles_df)
        
        # 시간 범위 필터링 (KST 기준)
        filtered_df = articles_df[
            (articles_df['parsed_datetime'] >= start_time_kst) & 
            (articles_df['parsed_datetime'] < end_time_kst)  
        ].copy()
        
        # UTC로 다시 변환하여 저장 (JSON에는 UTC로 저장)
        def convert_to_utc_string(dt):
            if pd.isna(dt):
                return None
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # UTC로 다시 변환하여 저장 (JSON에는 UTC로 저장, 'UTC' 표기 제거)
        def convert_to_utc_string_clean(dt):
            if pd.isna(dt):
                return None
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        filtered_df['published_date'] = filtered_df['parsed_datetime'].apply(convert_to_utc_string_clean)
        filtered_df = filtered_df.drop('parsed_datetime', axis=1)
        
        print(f"\n 시간 범위 필터링: {original_count}개 → {len(filtered_df)}개")
        
        return filtered_df
    
    def scrape_news(self, scroll_count=30, max_articles=500, headless=True):
        """
        뉴스 크롤링 메인 함수
        """
        with sync_playwright() as p:
            print(f" Playwright 브라우저 시작...")
            browser = p.chromium.launch(headless=headless)
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = context.new_page()
            
            try:
                # 뉴스 링크 수집
                news_links = self.scroll_and_collect_links(page, scroll_count=scroll_count)
                
                if not news_links:
                    print("⚠️ 뉴스 링크를 찾을 수 없습니다.")
                    return pd.DataFrame()
                
                # 최대 기사 수 제한
                news_links = news_links[:max_articles]
                
                # 각 기사 크롤링
                articles_data = []
                print(f"\n📰 개별 기사 크롤링 시작 (최대 {len(news_links)}개)...")
                
                for idx, link in enumerate(news_links, 1):
                    print(f"📄 [{idx}/{len(news_links)}] 크롤링 중...")
                    
                    # Redis 중복 체크
                    if r.sismember(REDIS_KEY, link):
                        print(f"   ⚠️ 중복 URL 스킵")
                        continue
                    
                    article = self.parse_article(page, link)
                    if article and article['title']:
                        articles_data.append(article)
                        print(f"   ✓ {article['title'][:60]}...")
                        
                        if article['published_date']:
                            print(f"   📅 {article['published_date']}")
                        
                        # Redis에 URL 저장 (24시간 만료)
                        r.sadd(REDIS_KEY, link)
                        r.expire(REDIS_KEY, 86400)  # 24시간
                    else:
                        print(f"   ✗ 기사 파싱 실패")
                
                # DataFrame 생성
                df = pd.DataFrame(articles_data)
                print(f"\n 총 {len(df)}개의 기사를 크롤링했습니다.")
                
                # 한국 시간 기준 필터링
                df = self.filter_by_kst_range(df)
                
                return df
                
            finally:
                context.close()
                browser.close()
                print("\n 브라우저 종료")
    
    def save_to_json(self, df, filename='yahoo_finance_news.json'):
        """DataFrame을 JSON 파일로 저장"""
        if df.empty:
            print("⚠️ 저장할 데이터가 없습니다.")
            return
        
        data = df.to_dict('records')
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f" 데이터가 '{filename}'에 저장되었습니다.")


def main():
    scraper = YahooFinanceNewsScraperPlaywright()
    df = scraper.scrape_news(scroll_count=30, max_articles=500, headless=True)
    
    if not df.empty:
        print("\n" + "="*80)
        print(" 크롤링 결과")
        print("="*80)
        print(df[['title', 'published_date']].to_string())
        
        scraper.save_to_json(df, 'yahoo_finance_news.json')
        
        print(f"\n 통계:")
        print(f"  - 총 기사 수: {len(df)}")
        print(f"  - 제목 있음: {df['title'].notna().sum()}")
        print(f"  - 본문 있음: {df['content'].notna().sum()}")
        print(f"  - 날짜 있음: {df['published_date'].notna().sum()}")
    else:
        print("\n 지정된 시간 범위의 뉴스가 없습니다.")


if __name__ == "__main__":
    main()