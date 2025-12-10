"""
Google 뉴스 크롤러 (최근 1시간)
---------------------------------------
수집 항목:
  - keyword, title, url, content, published_date
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from dateutil import parser
import re

# ==== 설정 ====
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
KST = timezone(timedelta(hours=9))
UTC = timezone.utc

# 최근 1시간 내 범위 계산 
def is_within_last_hour(pub_date: datetime):
    """KST 기준 최근 1시간 기사인지 확인"""
    if not isinstance(pub_date, datetime):
        return False

    # 날짜를 UTC로 정규화
    if pub_date.tzinfo is None:
        pub_date_utc = pub_date.replace(tzinfo=UTC)
    else:
        pub_date_utc = pub_date.astimezone(UTC)
    
    # KST 기준 최근 1시간 범위 계산
    now_kst = datetime.now(KST)
    start_kst = now_kst - timedelta(hours=24)
    
    start_utc = start_kst.astimezone(UTC)
    end_utc = now_kst.astimezone(UTC)
    
    result = start_utc <= pub_date_utc <= end_utc
    print(f"[FILTER] 결과: {result}")
    
    return result


# Selenium 설정
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)

driver = None

# Google redirect → 실제 URL
def extract_real_url(google_url, driver):
    try:
        driver.get(google_url)
        time.sleep(1)
        final_url = driver.current_url

        if 'news.google.com' not in final_url:
            return final_url
        
        return None
    except:
        return None


# 기사 본문 및 발행시간 추출
def extract_content_and_date(url, driver=None):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        # 콘텐츠 추출을 위한 Selenium 사용 
        if driver and len(soup.get_text(strip=True)) < 300:
            try:
                driver.get(url)
                time.sleep(2)
                soup = BeautifulSoup(driver.page_source, "html.parser")
            except:
                pass

        # 실제 발행시간 추출
        actual_date = None
        
        # 1. time 태그의 datetime 속성
        time_tag = soup.select_one("time[datetime]")
        if time_tag and time_tag.get("datetime"):
            try:
                actual_date = parser.parse(time_tag.get("datetime"))
            except:
                pass
        
        # 2. meta 태그에서 시간 추출
        if not actual_date:
            meta_tags = soup.find_all("meta")
            for meta in meta_tags:
                content = meta.get("content", "")
                if "published" in meta.get("property", "").lower() or "date" in meta.get("name", "").lower():
                    try:
                        actual_date = parser.parse(content)
                        break
                    except:
                        continue
        
        # 3. 본문에서 "Published" 패턴 찾기
        if not actual_date:
            import re
            text = soup.get_text()
            patterns = [
                r"Published\s+(\d{4}\.\d{1,2}\.\d{1,2}\.\s+\d{1,2}:\d{2})",
                r"Published\s+(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})",
                r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)",
                r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        date_str = match.group(1)
                        if "." in date_str:
                            date_str = date_str.replace(".", "-")
                        actual_date = parser.parse(date_str)
                        break
                    except:
                        continue
        
        # 4. Selenium으로 다시 시도 (시간 정보가 없을 때)
        if driver and not actual_date and len(soup.get_text(strip=True)) < 300:
            try:
                driver.get(url)
                time.sleep(3)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
                # 다시 시간 추출 시도
                time_tag = soup.select_one("time[datetime]")
                if time_tag and time_tag.get("datetime"):
                    try:
                        actual_date = parser.parse(time_tag.get("datetime"))
                    except:
                        pass
            except:
                pass

        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        selectors = [
            "article",
            '[class*=\"article\"]',
            '[class*=\"content\"]',
            '[class*=\"body\"]',
            "[itemprop='articleBody']",
        ]

        text = ""
        for sel in selectors:
            section = soup.select_one(sel)
            if section:
                candidate = section.get_text(" ", strip=True)
                if len(candidate) > len(text):
                    text = candidate

        # fallback
        if len(text) < 100:
            ps = soup.find_all("p")
            text = "\n".join(p.get_text(strip=True) for p in ps if len(p.get_text(strip=True)) > 30)

        content = text if len(text) > 100 else None
        return content, actual_date

    except:
        return None, None


# 하나의 키워드에 대한 크롤링
def crawl_google_news(keyword, seen_urls, driver):
    encoded = requests.utils.quote(keyword)
    feed_url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"

    feed = feedparser.parse(feed_url)
    results = []
    
    print(f"[RSS] {len(feed.entries)}개 엔트리 발견")

    for entry in feed.entries:
        raw_date = entry.get("published", "")
        try:
            pub_date = parser.parse(raw_date)
        except:
            continue

        # 최근 1시간 이내인지 먼저 확인
        if not is_within_last_hour(pub_date):
            continue

        real_url = extract_real_url(entry.link, driver)
        if not real_url:
            continue

        if real_url in seen_urls:
            print(f"[DUPLICATE] 중복 URL 스킵: {real_url}")
            continue
        seen_urls.add(real_url)
        print(f"[NEW URL] 새로운 URL 추가: {real_url}")

        content, actual_date = extract_content_and_date(real_url, driver)
        if not content:
            continue

        # 실제 발행시간이 있으면 사용, 없으면 RSS 시간 사용
        final_date = actual_date if actual_date else pub_date
        
        # 최종 시간으로 1시간 필터링 재확인
        if not is_within_last_hour(final_date):
            print(f"필터링 제외: 1시간 범위 밖")
            continue
            
        # UTC로 정규화 후 문자열 변환
        if final_date.tzinfo is None:
            final_date_utc = final_date.replace(tzinfo=UTC)
        else:
            final_date_utc = final_date.astimezone(UTC)
        published_utc = final_date_utc.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"UTC 변환: {published_utc}")
        print(f"필터링 통과: 수집 대상")

        results.append({
            "keyword": keyword,
            "title": entry.title,
            "url": real_url,
            "content": content,
            "published_date": published_utc
        })

    return results


def get_latest_google_news():
    driver = get_driver()
    
    try:
        keywords = [
       # Oil & Refining Market
    "crude oil market outlook OR refining industry trends",
    "oil price forecast OR Brent oil OR Dubai oil OR WTI price trends",
    "OPEC production OR OPEC+ cuts OR global oil supply",
    "oil refining margin OR gasoline diesel prices OR product profitability",
    "oil supply chain OR refinery utilization OR import diversification",
    
    # Raw Materials / Transport / Storage
    "refining capacity OR refinery expansion OR production efficiency",
    "oil storage OR crude reserves OR storage facilities OR stockpiling policy",
    "petrochemical feedstock OR naphtha OR chemical production",
    "shipping cost OR tanker freight OR logistics cost increase",
    "oil export import OR crude oil trade OR import source diversification",
    
    # Energy Policy / Environmental Issues
    "energy security OR oil dependency OR supply chain stability",
    "renewable energy transition OR carbon neutrality OR decarbonization policy",
    
    # Geopolitical / War Risks
    "Middle East conflict OR Israel war OR Iran tension OR Strait of Hormuz",
    "Russia Ukraine war OR oil sanctions OR supply disruption OR price surge",
    "Red Sea shipping disruption OR crude transport route change",
    "geopolitical tension OR oil market volatility OR OPEC conflict",
    
    # Macroeconomic / Financial Factors
    "exchange rate impact OR dollar strength OR USD KRW OR oil price fluctuation",
    "interest rate policy OR Fed monetary policy OR oil demand pressure",
    "global inflation OR economic recession OR energy demand decline",
    "currency volatility OR petrodollar OR oil trade currency",
    "oil demand forecast OR business cycle OR economic recovery",
    ]

        seen_urls = set()  # 전체 키워드에서 공유
        all_results = []

        for i, kw in enumerate(keywords, 1):
            print(f"\n[KEYWORD {i}/{len(keywords)}] {kw}")
            print(f"[SEEN_URLS] 현재 {len(seen_urls)}개 URL 저장됨")
            
            keyword_results = crawl_google_news(kw, seen_urls, driver)
            all_results.extend(keyword_results)
            
            print(f"[KEYWORD RESULT] {len(keyword_results)}개 기사 수집")
            print(f"[TOTAL SEEN] 누적 {len(seen_urls)}개 URL")

        print(f"\n⏱ 최근 1시간 기사 수집 완료: {len(all_results)}개")
        return all_results
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    try:
        news = get_latest_google_news()
        for i, a in enumerate(news, 1):
            print(f"\n[{i}] {a['title']}")
            print(a["url"])
            print(a["published_date"])
            print(a["content"][:200], "...\n")
    finally:
        driver.quit()