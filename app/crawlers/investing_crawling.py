# -*- coding: utf-8 -*-
"""
Brent Oil Futures News Crawler (Investing.com)

"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# 환경 설정
BASE_LIST_URL = "https://www.investing.com/commodities/brent-oil-news/{}"
KST = timezone(timedelta(hours=9))

# 메모리 기반 중복 제거
seen_urls = set()


# 상대시간 → UTC 변환
def parse_relative_time(text: str):
    """Investing.com 표기 시각 → UTC 변환 (한국시간 기준)"""
    text = text.strip()
    
    try:
        # 상대시간 처리 ("3 hours ago") - 한국시간(KST) 기준으로 계산
        text_lower = text.lower()
        if "hour" in text_lower and "ago" in text_lower:
            num = int(text_lower.split()[0])
            # KST 기준 현재 시각에서 계산
            now_kst = datetime.now(KST)
            dt_kst = now_kst - timedelta(hours=num)
            result = dt_kst.astimezone(timezone.utc)
            return result
        elif "minute" in text_lower and "ago" in text_lower:
            num = int(text_lower.split()[0])
            now_kst = datetime.now(KST)
            dt_kst = now_kst - timedelta(minutes=num)
            result = dt_kst.astimezone(timezone.utc)
            return result
        elif "day" in text_lower and "ago" in text_lower:
            num = int(text_lower.split()[0])
            now_kst = datetime.now(KST)
            dt_kst = now_kst - timedelta(days=num)
            result = dt_kst.astimezone(timezone.utc)
            return result
        
        # 절대시간 처리 ("11/24/2025, 11:36 PM")
        if "/" in text and ("AM" in text or "PM" in text):
            # 한국시간(KST) 기준으로 처리
            dt_local = datetime.strptime(text, "%m/%d/%Y, %I:%M %p")
            dt_kst = dt_local.replace(tzinfo=KST)
            result = dt_kst.astimezone(timezone.utc)
            return result
            
        # 다른 절대시간 형식들
        for fmt in ["%b %d, %Y", "%Y-%m-%d"]:
            try:
                dt_local = datetime.strptime(text, fmt)
                # 한국시간(KST) 기준으로 처리
                dt_kst = dt_local.replace(tzinfo=KST)
                result = dt_kst.astimezone(timezone.utc)
                return result
            except:
                continue
                
        return None
    except:
        return None

# 목록 파싱
def parse_list(html: str):
    soup = BeautifulSoup(html or "", "lxml")
    cards = soup.select("article.js-article-item") or soup.select("article")
    results = []

    for art in cards:
        try:
            a = art.select_one("a.title") or art.select_one("a[href*='/news/']")
            if not a or not a.get("href"):
                continue

            url = a["href"]
            if url.startswith("/"):
                url = "https://www.investing.com" + url

            print(f"\n[INVESTING PARSE] {url}")
            print(f"상세 페이지에서 시간 추출 예정")

            results.append({
                "url": url,
                "published_at": None  
            })
        except:
            continue

    return results


# 상세 파싱
def parse_detail(html: str):
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    title = None
    
    # 1. meta og:title
    meta_title = soup.select_one("meta[property='og:title']")
    if meta_title and meta_title.get("content"):
        title = meta_title.get("content")
    
    # 2. title 태그
    if not title:
        title_tag = soup.select_one("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if " - " in title_text:
                title = title_text.split(" - ")[0]
            else:
                title = title_text
    
    # 3. h1 태그
    if not title:
        h1_tag = soup.select_one("h1")
        if h1_tag:
            title = h1_tag.get_text(strip=True)

    # 발행시간 추출 (원본 그대로 사용)
    published_at = None
    original_time_str = None
    
    # 1. "Published" 패턴 찾기
    published_patterns = [
        r"Published\s+(\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s*[AP]M)",
        r"Updated\s+(\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s*[AP]M)",
        r"(\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s*[AP]M)"
    ]
    
    page_text = soup.get_text()
    for pattern in published_patterns:
        import re
        match = re.search(pattern, page_text)
        if match:
            date_str = match.group(1)
            original_time_str = date_str  # 원본 시간 저장
            try:
                # 원본 시간을 그대로 파싱 (Investing.com 시간대 그대로)
                if "/" in date_str and ("AM" in date_str or "PM" in date_str):
                    # 콤마 제거 후 파싱
                    clean_date = date_str.replace(",", "")
                    dt_local = datetime.strptime(clean_date, "%m/%d/%Y %I:%M %p")
                    # Investing.com의 시간대를 그대로 사용 (UTC로 가정)
                    published_at = dt_local.replace(tzinfo=timezone.utc)
                    print(f"[INVESTING TIME] 원본 시간 추출: {date_str} -> {published_at}")
                    break
            except Exception as e:
                print(f"[INVESTING TIME] 시간 파싱 실패: {date_str} - {e}")
                continue
    
    # 2. time 태그 백업
    if not published_at:
        time_tags = soup.find_all("time")
        for tag in time_tags:
            dt_attr = tag.get("datetime")
            if dt_attr:
                try:
                    published_at = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                    print(f"[INVESTING TIME] time 태그 추출: {dt_attr} -> UTC: {published_at}")
                    break
                except:
                    continue

    # 본문 추출
    root = (
        soup.select_one("div.articlePage")
        or soup.select_one("#article")
        or soup.select_one("article")
    )
    if not root:
        return None

    paragraphs = [p.get_text(strip=True) for p in root.select("p") if p.get_text(strip=True)]
    content = "\n".join(paragraphs) if paragraphs else None

    return {"title": title, "content": content, "published_at": published_at, "original_time": original_time_str}


# ----------------------------
# 개별 기사 async 크롤링
# ----------------------------
async def crawl_article_detail(crawler, article, run_cfg):
    try:
        res = await crawler.arun(url=article["url"], config=run_cfg)
        if not res or not res.success or not res.html:
            return None

        detail = parse_detail(res.html)
        if not detail or not detail["content"] or not detail["published_at"]:
            return None

        # UTC 기준 시간 처리
        published_at_utc = detail["published_at"]
        pub_date = published_at_utc.strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"\n[INVESTING DETAIL] {article['url']}")
        print(f"UTC 시간: {pub_date}")

        return {
            "title": detail["title"],
            "content": detail["content"],
            "published_date": pub_date,
            "published_at_utc": published_at_utc,  # 필터링용
            "url": article["url"]
        }

    except Exception:
        return None


# ----------------------------
# 메인 크롤러 (1시간 기준)
# ----------------------------
async def crawl_brent_news_hourly(start_page=1, end_page=5):
    global seen_urls

    all_news = []

    # UTC 기준 최근 1시간
    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc
    start_utc = end_utc - timedelta(hours=24)

    browser_cfg = BrowserConfig(
        headless=True,
        browser_type="chromium",
        extra_args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        viewport={"width": 1366, "height": 900}
    )

    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=90000
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for page in range(start_page, end_page + 1):

            list_url = BASE_LIST_URL.format(page)

            try:
                result = await crawler.arun(url=list_url, config=run_cfg)
                if not result or not result.success or not result.html:
                    continue

                articles = parse_list(result.html)
                print(f"\n[INVESTING] 목록에서 {len(articles)}개 기사 발견")
                
                if not articles:
                    continue
                
                new_articles = [
                    a for a in articles if a["url"] not in seen_urls
                ]
                for a in new_articles:
                    seen_urls.add(a["url"])

                tasks = [
                    crawl_article_detail(crawler, art, run_cfg)
                    for art in new_articles
                ]

                results = await asyncio.gather(*tasks)

                # UTC 기준 1시간 필터링
                print(f"\n[INVESTING FILTER] UTC 범위: {start_utc.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_utc.strftime('%Y-%m-%d %H:%M:%S')}")
                
                for rsl in results:
                    if rsl and rsl.get("published_at_utc"):
                        pub_utc = rsl["published_at_utc"]
                        print(f"\n[INVESTING DEBUG] {rsl['url']}")
                        print(f"기사 UTC: {pub_utc.strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        if start_utc <= pub_utc <= end_utc:
                            print(f"필터링 통과: 수집 대상")
                            # published_at_utc 필드 제거 후 추가
                            final_result = {k: v for k, v in rsl.items() if k != "published_at_utc"}
                            all_news.append(final_result)
                        else:
                            print(f"필터링 제외: 1시간 범위 밖")

            except Exception as e:
                print(f"[오류] {e}")
                continue

    print(f"Investing.com 최근 1시간 기사: {len(all_news)}개")
    return all_news

# 테스트 실행
if __name__ == "__main__":
    news = asyncio.run(crawl_brent_news_hourly(start_page=1, end_page=3))
    print(json.dumps(news, ensure_ascii=False, indent=2))