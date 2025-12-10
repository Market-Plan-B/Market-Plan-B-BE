# -*- coding: utf-8 -*-
"""
OilPrice 뉴스 크롤러 (최근 1시간)

"""

import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dateutil import parser


# 설정
BASE_URL = "https://oilprice.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
}
DELAY = 1.2

# 시간대
KST = timezone(timedelta(hours=9))
CST = timezone(timedelta(hours=-6))
CDT = timezone(timedelta(hours=-5))

# 중복 URL 저장
seen_urls = set()

# 날짜 변환: CST/CDT 또는 상대시간 → KST
def parse_oilprice_date(date_str):
    """
    OilPrice 날짜 → KST 변환
    """
    s = date_str.strip().lower()
    now_utc = datetime.now(timezone.utc)

    # ---- (1) 상대시간 처리 ----
    if "hour" in s:
        num = int(s.split()[0])
        return (now_utc - timedelta(hours=num)).astimezone(KST)

    if "minute" in s:
        num = int(s.split()[0])
        return (now_utc - timedelta(minutes=num)).astimezone(KST)

    if "day" in s:
        num = int(s.split()[0])
        return (now_utc - timedelta(days=num)).astimezone(KST)

    # ---- (2) 절대시간 처리 ----
    try:
        # "Nov 24, 2025, 3:00 PM CST"
        if "," in date_str:
            parts = date_str.rsplit(" ", 1)
            datetime_part = parts[0]
            tz_part = parts[1].strip()

            # "Nov 24, 2025, 3:00 PM"
            dt = datetime.strptime(datetime_part, "%b %d, %Y, %I:%M %p")

            # 시간대 처리
            if tz_part == "CST":
                us_tz = CST
            elif tz_part == "CDT":
                us_tz = CDT
            else:
                us_tz = timezone.utc  # fallback

            dt_local = dt.replace(tzinfo=us_tz)
            return dt_local.astimezone(KST)

    except Exception:
        return None

    return None

# 최근 1시간 필터
def is_within_last_hour(kst_dt):
    if not kst_dt:
        return False
    now = datetime.now(KST)
    start_kst = now - timedelta(hours=6)
    
    
    result = start_kst <= kst_dt <= now
    print(f"[OILPRICE FILTER] 결과: {result}")
    
    return result

# 본문 추출
def get_article_content(url):
    try:
        time.sleep(DELAY)
        res = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, "html.parser")

        selectors = [
            "article",
            ".article-body",
            ".article-content",
            "div[itemprop='articleBody']",
            "#article-content",
        ]

        text = ""

        for sel in selectors:
            section = soup.select_one(sel)
            if section:
                paragraphs = [
                    p.get_text(strip=True)
                    for p in section.find_all("p")
                    if len(p.get_text(strip=True)) > 20
                ]
                if paragraphs:
                    text = "\n".join(paragraphs)
                    break

        if not text:
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 50
            ]
            text = "\n".join(paragraphs)

        return text if text else None

    except Exception:
        return None

# 목록 페이지 크롤링
def crawl_oilprice_last_hour(max_pages=2):
    global seen_urls

    collected = []

    for page in range(1, max_pages + 1):
        url = (
            f"{BASE_URL}/Energy/Crude-Oil/"
            if page == 1
            else f"{BASE_URL}/Energy/Crude-Oil/?page={page}"
        )

        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
        except:
            continue

        articles = (
            soup.select(".categoryArticle__content")
            or soup.select(".categoryArticle")
        )

        for art in articles:
            try:
                link_el = art.select_one("a[href*='/Energy/Crude-Oil/']")
                if not link_el:
                    continue

                href = link_el.get("href")
                article_url = BASE_URL + href if href.startswith("/") else href

                # 중복 제거
                if article_url in seen_urls:
                    continue
                seen_urls.add(article_url)

                # 날짜 파싱
                meta = art.select_one(".categoryArticle__meta")
                if not meta:
                    continue

                date_text = meta.get_text(strip=True)
                kst_dt = parse_oilprice_date(date_text)


                # 최근 1시간 필터
                if not is_within_last_hour(kst_dt):
                    print(f"필터링 제외: 1시간 범위 밖")
                    continue

                # 본문
                content = get_article_content(article_url)
                if not content:
                    continue

                title = link_el.get_text(strip=True) or "No Title"

                utc_time = kst_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                print(f"UTC 변환: {utc_time}")
                print(f"필터링 통과: 수집 대상")
                
                collected.append({
                    "title": title,
                    "content": content,
                    "published_date": utc_time,
                    "url": article_url
                })

                print(f"✓ {title[:70]}")

            except Exception:
                continue

        time.sleep(0.8)

    print(f"\n총 {len(collected)}개 기사 수집 완료")
    return collected

# 실행
if __name__ == "__main__":
    data = crawl_oilprice_last_hour(max_pages=3)
    import json
    print(json.dumps(data, ensure_ascii=False, indent=2))