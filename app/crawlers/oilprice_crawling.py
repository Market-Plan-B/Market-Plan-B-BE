"""
OilPrice 일일 보고서 크롤러
- 한국시간 전날 오전 6시 ~ 당일 오전 6시 범위 수집
- OilPrice CST/CDT 시간대 고려
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
import redis
from datetime import datetime, timedelta, timezone
from dateutil import parser

# ----------------------------
# Redis 설정
# ----------------------------
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
REDIS_KEY = "oilprice_news_urls"

# 설정
BASE_URL = "https://oilprice.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DELAY = 1.5
DEBUG_MODE = True

# 시간대 정의
KST = timezone(timedelta(hours=9))
CST = timezone(timedelta(hours=-6))
CDT = timezone(timedelta(hours=-5))

def parse_oilprice_date(date_str):
    """OilPrice 날짜 문자열을 KST로 변환"""
    try:
        if " | " in date_str:
            date_part = date_str.split(" | ")[0].strip()
        else:
            date_part = date_str.strip()
        
        parsed_date = parser.parse(date_part, fuzzy=True)

        current_month = datetime.now().month
        if 4 <= current_month <= 10:
            us_tz = CDT
        else:
            us_tz = CST
        
        oilprice_time = parsed_date.replace(tzinfo=us_tz)
        kst_time = oilprice_time.astimezone(KST)
        
        if DEBUG_MODE:
            print(f"날짜 변환: {date_str} -> {kst_time.strftime('%Y-%m-%d %H:%M KST')}")
        
        return kst_time
        
    except Exception as e:
        if DEBUG_MODE:
            print(f"날짜 파싱 실패: {date_str} ({e})")
        return None

def is_within_target_range(kst_datetime):
    """한국시간 전날 오전 6시 ~ 당일 오전 6시 범위 확인"""
    if not kst_datetime:
        return False
    
    now_kst = datetime.now(KST)
    
    if now_kst.hour >= 6:
        end_time = now_kst.replace(hour=6, minute=0, second=0, microsecond=0)
    else:
        end_time = (now_kst - timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
    
    start_time = end_time - timedelta(days=1)
    
    return start_time <= kst_datetime < end_time

def get_article_content(url):
    """개별 기사 본문 추출"""
    try:
        time.sleep(DELAY)
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        content_parts = []
        content_selectors = [
            "article",
            ".article-body",
            ".article__content",
            ".article-content",
            ".entry-content",
            ".post-content",
            "div[itemprop='articleBody']",
            "#article-content"
        ]
        
        content_container = None
        for selector in content_selectors:
            container = soup.select_one(selector)
            if container:
                content_container = container
                break
        
        if content_container:
            for tag in content_container.find_all(['script', 'style', 'nav', 'aside', 'header', 'footer', 'iframe']):
                tag.decompose()
            
            paragraphs = content_container.find_all("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if (len(text) > 20 and 
                    not text.startswith("SetOilPrice.com") and
                    "oilprice.com" not in text.lower()):
                    content_parts.append(text)
        
        if not content_parts:
            all_paragraphs = soup.find_all("p")
            for p in all_paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 80:
                    content_parts.append(text)
        
        full_text = "\n\n".join(content_parts)
        
        author = "OilPrice.com"
        author_selectors = [".article-byline", ".byline", ".author-name", ".author"]
        
        for selector in author_selectors:
            author_tag = soup.select_one(selector)
            if author_tag:
                author_text = author_tag.get_text(strip=True)
                if " | " in author_text:
                    author = author_text.split(" | ")[1].strip()
                elif author_text.startswith("By "):
                    author = author_text[3:]
                else:
                    author = author_text
                break
        
        return full_text, author
        
    except Exception as e:
        if DEBUG_MODE:
            print(f"본문 수집 실패: {e}")
        return "", "OilPrice.com"

def crawl_recent_pages(max_pages=2):
    """최근 1-2페이지만 크롤링하여 24시간 범위 기사 수집"""
    collected_articles = []
    seen_urls = set()
    
    print(f"최근 {max_pages}페이지 크롤링 시작")

    for page in range(1, max_pages + 1):
        if page == 1:
            url = f"{BASE_URL}/Energy/Crude-Oil/"
        else:
            url = f"{BASE_URL}/Energy/Crude-Oil/?page={page}"
        
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            
            articles = soup.select(".categoryArticle__content") or soup.select(".categoryArticle")
            if not articles:
                print(f"페이지 {page}: 기사를 찾지 못함")
                continue
            
            page_count = 0
            for art in articles:
                try:
                    link_tag = (art.select_one("h2 a") or 
                               art.select_one("h3 a") or
                               art.select_one(".categoryArticle__title a") or
                               art.select_one("a[href*='/Energy/Crude-Oil/']"))
                    
                    if not link_tag:
                        continue
                    
                    title = link_tag.get_text(strip=True)
                    if not title:
                        parent_heading = link_tag.find_parent(['h2', 'h3'])
                        if parent_heading:
                            title = parent_heading.get_text(strip=True)
                    
                    href = link_tag.get("href", "")
                    if href.startswith("/"):
                        article_url = BASE_URL + href
                    elif href.startswith("http"):
                        article_url = href
                    else:
                        continue
                    
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)
                    
                    # Redis 중복 체크
                    if r.sismember(REDIS_KEY, article_url):
                        if DEBUG_MODE:
                            print(f"  ⚠️ 중복 URL 스킵: {title[:50]}...")
                        continue
                    
                    date_meta = art.select_one(".categoryArticle__meta")
                    if not date_meta:
                        continue
                    
                    date_text = date_meta.get_text(strip=True)
                    article_kst_time = parse_oilprice_date(date_text)
                    
                    if not is_within_target_range(article_kst_time):
                        if DEBUG_MODE:
                            print(f"범위 외 기사 제외: {title[:50]} ({date_text})")
                        continue
                    
                    content, author = get_article_content(article_url)
                    
                    if not title:
                        url_parts = article_url.split('/')[-1].replace('.html', '').replace('-', ' ')
                        title = url_parts.title() if url_parts else "제목 없음"
                    
                    # KST를 UTC로 변환
                    if article_kst_time:
                        article_utc_time = article_kst_time.astimezone(timezone.utc)
                        published_date = article_utc_time.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        published_date = date_text
                    
                    collected_articles.append({
                        "title": title,
                        "content": content,
                        "published_date": published_date,
                        "url": article_url
                    })
                    
                    # Redis에 URL 저장 (24시간 만료)
                    r.sadd(REDIS_KEY, article_url)
                    r.expire(REDIS_KEY, 86400)  # 24시간
                    
                    page_count += 1
                    print(f"[{page_count}] {title[:70]}")

                except Exception as e:
                    if DEBUG_MODE:
                        print(f"기사 처리 오류: {e}")
                    continue
            
            time.sleep(1)
            
        except Exception as e:
            print(f"페이지 {page} 로드 실패: {e}")
            continue
    
    return collected_articles

if __name__ == "__main__":
    articles = crawl_recent_pages()
    print(f"\n수집 완료: {len(articles)}개 기사")