# Investing.com에서  
# Brent Oil Futures News 관련
# KST 기준 어제 06시~오늘 06시 기사 수집
# Redis 사용하여 중복 체크

import asyncio
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import redis

BASE_LIST_URL = "https://www.investing.com/commodities/brent-oil-news/{}"

# ----------------------------
# Redis 설정
# ----------------------------
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
REDIS_KEY = "brent_news_urls"

# ----------------------------
# UTC 기반 상대시간 파싱 함수
# ----------------------------
def parse_relative_time(text: str):
    """
    Investing.com 표기 시각은 GMT+2 기준이므로, UTC 기준으로 변환 시 -2h 보정
    """
    now_gmt2 = datetime.utcnow() + timedelta(hours=2)
    text = text.lower().strip()

    try:
        if "hour" in text:
            num = int(text.split()[0])
            dt_gmt2 = now_gmt2 - timedelta(hours=num)
        elif "minute" in text:
            num = int(text.split()[0])
            dt_gmt2 = now_gmt2 - timedelta(minutes=num)
        elif "day" in text:
            num = int(text.split()[0])
            dt_gmt2 = now_gmt2 - timedelta(days=num)
        else:
            try:
                dt_gmt2 = datetime.strptime(text, "%b %d, %Y")
            except Exception:
                return None

        # ✅ GMT+2 → UTC로 변환 (-2h)
        dt_utc = dt_gmt2 - timedelta(hours=2)
        return dt_utc

    except Exception:
        return None


# ----------------------------
# 목록 파싱
# ----------------------------
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

            time_tag = art.select_one("time, .date, .contentSectionDetails span")
            published_text = time_tag.get_text(strip=True) if time_tag else None
            published_dt = parse_relative_time(published_text) if published_text else None

            results.append({
                "url": url,
                "published_at": published_dt
            })
        except Exception as e:
            print(f"[목록 파싱 오류] {e}")
            continue
    return results


# ----------------------------
# 상세 페이지 파싱
# ----------------------------
def parse_detail(html: str):
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    root = (
        soup.select_one("div.articlePage")
        or soup.select_one("#article")
        or soup.select_one("article")
    )
    if not root:
        return None

    paragraphs = [p.get_text(strip=True) for p in root.select("p") if p.get_text(strip=True)]
    content = "\n".join(paragraphs) if paragraphs else None

    desc_tag = soup.select_one("meta[property='og:description'], meta[name='description']")
    description = desc_tag.get("content") if desc_tag and desc_tag.get("content") else None

    return {
        "content": content,
        "title": description if description else None
    }


# ----------------------------
# 기사 상세 크롤링
# ----------------------------
async def crawl_article_detail(crawler, article, run_cfg):
    try:
        res = await crawler.arun(url=article["url"], config=run_cfg)
        if not res or not res.success or not res.html:
            return None

        detail = parse_detail(res.html)
        if not detail or not detail.get("content"):
            return None

        # ✅ published_date 보정
        if article["published_at"]:
            # UTC → KST 변환 + 문자열 포맷
            published_date = (article["published_at"]).strftime("%Y-%m-%d %H:%M")
        else:
            published_date = None

        return {
            "title": detail["title"],
            "url": article["url"],
            "content": detail["content"],
            "published_date": published_date  # ✅ 항상 문자열 형태
        }

    except Exception as e:
        print(f"[⚠️ 상세 크롤링 오류] {article['url']} → {e}")
        return None


# ----------------------------
# 전체 크롤링 (KST 기준 어제 06시~오늘 06시 기사)
# ----------------------------
async def crawl_brent_news(start_page=1, end_page=10, concurrency=3):
    all_news = []

    now_kst = datetime.utcnow() + timedelta(hours=9)
    end_kst = now_kst
    start_kst = end_kst - timedelta(hours=1)

    start_utc = start_kst - timedelta(hours=9)
    end_utc = end_kst - timedelta(hours=9)

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
                    print(f"[목록 로딩 실패] {list_url}")
                    continue

                articles = parse_list(result.html)
                filtered = [
                    a for a in articles
                    if a["published_at"] and start_utc <= a["published_at"] < end_utc
                ]

                if not filtered:
                    continue

            except Exception as e:
                print(f"[목록 요청 오류] {e}")
                continue

            new_articles = []
            for art in filtered:
                if not r.sismember(REDIS_KEY, art["url"]):
                    new_articles.append(art)
                else:
                    print(f"이미 크롤링된 URL: {art['url']}")

            tasks = [asyncio.create_task(crawl_article_detail(crawler, art, run_cfg)) for art in new_articles]
            results = await asyncio.gather(*tasks)
            for rsl in results:
                if rsl:
                    all_news.append(rsl)
                    r.sadd(REDIS_KEY, rsl["url"])

    #         with open("brent_news_timewindow_temp.json", "w", encoding="utf-8") as f:
    #             json.dump(all_news, f, ensure_ascii=False, indent=2)

    # with open("brent_oil_news_timewindow.json", "w", encoding="utf-8") as f:
    #     json.dump(all_news, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(crawl_brent_news(start_page=1, end_page=2, concurrency=5))
