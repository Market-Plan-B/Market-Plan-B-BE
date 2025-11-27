from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timezone, timedelta
import json
import time

# 메모리 기반 중복 제거
seen_urls = set()

class YahooFinanceNewsScraperPlaywright:
    def __init__(self):
        self.base_url = "https://finance.yahoo.com"
        self.news_url = "https://finance.yahoo.com/news/"
        self.KST = timezone(timedelta(hours=9))
        self.UTC = timezone.utc

    # 최근 1시간 필터링 (한국시간 기준)
    def is_within_last_hour(self, kst_dt):
        """KST 기준 최근 1시간인지 판단"""
        if not isinstance(kst_dt, datetime):
            return False

        # KST 기준 최근 1시간 범위 계산
        now_kst = datetime.now(self.KST)
        start_kst = now_kst - timedelta(hours=1)
        
        result = start_kst <= kst_dt <= now_kst

        print(f"[YAHOO FILTER] 결과: {result}")
        
        return result
    
    # 링크 스크롤 수집
    def scroll_and_collect_links(self, page, scroll_count=20, scroll_pause=1.2):
        print(f"Yahoo Finance 뉴스 페이지 접속 중...")
        page.goto(self.news_url, wait_until='domcontentloaded')
        time.sleep(2)
        news_links = set()
        print(f"페이지 스크롤 시작...")
        for i in range(scroll_count):
            links = page.query_selector_all('a[href*="/news/"]')
            for link in links:
                try:
                    href = link.get_attribute('href')
                    if href and '/news/' in href and '.html' in href:
                        if href.startswith('/'):
                            full_url = f"https://finance.yahoo.com{href}"
                        else:
                            full_url = href
                        clean_url = full_url.split('?')[0]
                        news_links.add(clean_url)
                except:
                    continue
            print(f"  스크롤 {i+1}/{scroll_count}: {len(news_links)}개")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(scroll_pause)
        return list(news_links)


    # 기사 파싱
    def parse_article(self, page, url):
        try:
            page.goto(url, wait_until='domcontentloaded')
            time.sleep(0.7)
            soup = BeautifulSoup(page.content(), 'html.parser')

            article = {
                "url": url,
                "title": None,
                "content": None,
                "published_date": None 
            }

            # 제목 (우선순위별 추출)
            title = None
            
            # 1. meta og:title 우선 
            meta_title = soup.select_one("meta[property='og:title']")
            if meta_title and meta_title.get("content"):
                title = meta_title.get("content")
            
            # 2. h1 태그들 중 "Yahoo Finance"가 아닌 것
            if not title:
                h1_tags = soup.find_all("h1")
                for h1 in h1_tags:
                    h1_text = h1.get_text(strip=True)
                    if h1_text and h1_text != "Yahoo Finance" and len(h1_text) > 10:
                        title = h1_text
                        break
            
            # 3. title 태그 백업
            if not title:
                title_tag = soup.select_one("title")
                if title_tag:
                    title_text = title_tag.get_text(strip=True)
                    if " - Yahoo Finance" in title_text:
                        title = title_text.replace(" - Yahoo Finance", "")
                    else:
                        title = title_text
            
            article["title"] = title if title else "No Title"

            # 본문
            content_parts = []
            body = soup.find("article") or soup.find("div", class_="caas-body")
            if body:
                for p in body.find_all("p"):
                    txt = p.get_text(strip=True)
                    if len(txt) > 20:
                        content_parts.append(txt)

            article["content"] = "\n".join(content_parts) if content_parts else None

            # 발행 시간 처리 (Yahoo Finance는 한국시간 표시)
            time_tags = soup.find_all("time")
            for tag in time_tags:
                dt = tag.get("datetime")
                if dt:
                    try:
                        # datetime 파싱 (UTC 기준)
                        utc_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                        # KST로 변환 (Yahoo Finance는 한국시간 기준)
                        kst_dt = utc_dt.astimezone(self.KST)
                        
                        # published_date는 UTC로 저장
                        article["published_date"] = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        article["kst_time"] = kst_dt  # 필터링용
                        
                        return article
                    except:
                        continue

            return article

        except Exception as e:
            print("파싱 실패:", e)
            return None

    # 메인 크롤링
    def scrape_news(self, scroll_count=30, max_articles=500, headless=True):
        global seen_urls

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            try:
                links = self.scroll_and_collect_links(page, scroll_count)

                articles = []
                for idx, url in enumerate(links[:max_articles], 1):
                    print(f"[{idx}/{len(links)}] {url}")

                    if url in seen_urls:
                        print(" - 중복 스킵")
                        continue
                    seen_urls.add(url)

                    data = self.parse_article(page, url)
                    if not data or not data.get("published_date") or not data.get("kst_time"):
                        continue

                    # KST 기준으로 필터링
                    kst_dt = data["kst_time"]
                    if not self.is_within_last_hour(kst_dt):
                        print(f"필터링 제외: 1시간 범위 밖")
                        continue

                    # kst_time 필드 제거 후 추가
                    del data["kst_time"]
                    articles.append(data)
                    print(f"필터링 통과: 수집 대상")

                return pd.DataFrame(articles)

            finally:
                context.close()
                browser.close()

    # 저장
    def save_to_json(self, df, filename):
        if df.empty:
            print("저장할 데이터 없음")
            return
        df.to_json(filename, orient="records", indent=2, force_ascii=False)
        print(f"저장 완료 → {filename}")

# 실행부
def main():
    scraper = YahooFinanceNewsScraperPlaywright()
    df = scraper.scrape_news(scroll_count=25, max_articles=300, headless=True)

    if not df.empty:
        print(df[["title", "published_date"]])
        scraper.save_to_json(df, "yahoo_finance_last1h.json")
    else:
        print("최근 1시간 기사 없음.")


if __name__ == "__main__":
    main()