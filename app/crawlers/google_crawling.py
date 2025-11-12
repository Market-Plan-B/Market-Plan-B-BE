"""
Google 뉴스 크롤러
---------------------------------------
수집 범위:
  - 한국시간(KST): 전날 오전 6시 ~ 오늘 오전 6시
  - UTC 변환 시: 전전날 21:00 ~ 전날 21:00

수집 항목:
  - keyword, title, url, content, published_date
"""

import feedparser
import requests
from bs4 import BeautifulSoup
import json
import redis
from datetime import datetime, timedelta, timezone
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from dateutil import parser

# ----------------------------
# Redis 설정
# ----------------------------
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
REDIS_KEY = "google_news_urls"

# ==== 설정 ====
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
KST = timezone(timedelta(hours=9))
UTC = timezone.utc
DEBUG_MODE = True


# Selenium 설정
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)


driver = get_driver()


# Google redirect → 실제 언론사 URL 추출
def extract_real_url(google_url):
    try:
        driver.get(google_url)
        time.sleep(2)
        final_url = driver.current_url
        if 'news.google.com' not in final_url and 'gstatic.com' not in final_url:
            print(f" 실제 URL: {final_url[:100]}")
            return final_url
        else:
            print(" 리디렉션 실패 (Google 내부 링크)")
            return None
    except Exception as e:
        print(f" URL 추출 오류: {e}")
        return None


#  본문 추출
def extract_content(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        if len(soup.get_text(strip=True)) < 500:
            try:
                driver.get(url)
                time.sleep(3)
                soup = BeautifulSoup(driver.page_source, "html.parser")
            except Exception as e:
                print(f" Selenium 재시도 실패: {e}")

        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        selectors = [
            "article",
            '[id*="article"]',
            '[class*="article"]',
            '[class*="content"]',
            '[class*="body"]',
            '[class*="post"]',
            '[class*="entry"]',
            'section',
        ]

        text = ""
        for sel in selectors:
            section = soup.select_one(sel)
            if section:
                candidate = section.get_text(separator="\n", strip=True)
                if len(candidate) > len(text):
                    text = candidate

        if len(text) < 50:
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 30
            ]
            text = "\n".join(paragraphs)

        if len(text) > 50:
            print(f"   ✓ 본문 추출 완료 ({len(text)}자)")
            return text
        else:
            print("   ⚠️ 본문 부족하거나 없음")
            return None

    except Exception as e:
        print(f"   ⚠️ 본문 추출 오류: {e}")
        return None


# UTC 범위 필터 (KST 전날 6시 ~ 당일 6시 = UTC 전전날 21시 ~ 전낡 21시)
def is_within_kst_day(pub_date):
    if not isinstance(pub_date, datetime):
        return False

    pub_date = pub_date.astimezone(UTC)
    now_kst = datetime.now(KST)
    
    # 한국시간 기준 당일 06:00
    if now_kst.hour >= 6:
        end_kst = now_kst.replace(hour=6, minute=0, second=0, microsecond=0)
    else:
        end_kst = (now_kst - timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    
    start_kst = end_kst - timedelta(days=1)  # 전날 06:00
    
    # KST를 UTC로 변환
    end_utc = end_kst.astimezone(UTC)    # 전낡 21:00 UTC
    start_utc = start_kst.astimezone(UTC)  # 전전낡 21:00 UTC

    if DEBUG_MODE:
        print(f"   🕓 UTC Range: {start_utc.isoformat()} ~ {end_utc.isoformat()}")
        print(f"   🕓 Article Time (UTC): {pub_date.isoformat()}")

    return start_utc <= pub_date < end_utc


#  RSS 크롤러
def crawl_google_news(keyword):
    encoded = requests.utils.quote(keyword)
    feed_url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"

    print(f"\n{'='*70}")
    print(f"🔍 키워드: {keyword}")
    print(f"{'='*70}")

    feed = feedparser.parse(feed_url)
    total_articles = len(feed.entries)
    print(f"   ✓ {total_articles}개 기사 발견")

    results = []
    success_count = 0

    for i, entry in enumerate(feed.entries, 1):
        print(f"\n[{i}/{total_articles}] ▶ {entry.title[:60]}...")

        # 먼저 날짜 확인
        raw_date = entry.get("published", "")
        parsed_date = None
        try:
            if raw_date:
                parsed_date = parser.parse(raw_date)
        except Exception as e:
            print(f" 날짜 파싱 오류: {e}")
            continue

        if not parsed_date or not is_within_kst_day(parsed_date):
            print(" 기사 시간대 범위 외 - 크롤링 스킵")
            continue

        # 시간대 범위에 맞으면 본문 크롤링 시작
        real_url = extract_real_url(entry.link)
        if not real_url:
            continue
            
        # Redis 중복 체크
        if r.sismember(REDIS_KEY, real_url):
            if DEBUG_MODE:
                print(f"  중복 URL 스킵: {entry.title[:50]}...")
            continue

        content = extract_content(real_url)
        if not content:
            continue

        published_utc = parsed_date.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

        results.append({
            "keyword": keyword,
            "title": entry.title,
            "url": real_url,
            "content": content,
            "published_date": published_utc
        })
        
        # Redis에 URL 저장 (24시간 만료)
        r.sadd(REDIS_KEY, real_url)
        r.expire(REDIS_KEY, 86400)  # 24시간
        
        success_count += 1
        print(f"    저장 완료 ({success_count}/{total_articles})")

    print(f"\n 키워드 '{keyword}' 결과 요약: {success_count}/{total_articles}개 저장")
    return results


def get_latest_google_news():
    """최신 Google News 수집"""
    print(f"\n{'='*50}")
    print("🔍 Google News 최신 24시간 뉴스 수집 시작")
    print(f"{'='*50}")
    
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

    all_results = []
    for kw in keywords:
        data = crawl_google_news(kw)
        all_results.extend(data)

    print(f"\n 수집 결과:")
    print(f"  ▶ 총 {len(all_results)}개 기사 수집 완료")
    
    return all_results

if __name__ == "__main__":
    try:
        news_data = get_latest_google_news()
        
        if news_data:
            print(f"\n 추출된 데이터:")
            print("="*80)
            for i, article in enumerate(news_data, 1):
                print(f"\n[{i}] {article['title']}")
                print(f"URL: {article['url']}")
                print(f"날짜: {article['published_date']}")
                print(f"본문: {article['content'][:200]}..." if len(article['content']) > 200 else f"본문: {article['content']}")
                print("-" * 80)
        else:
            print("\n⚠️ 수집된 기사가 없습니다.")
    
    finally:
        driver.quit()