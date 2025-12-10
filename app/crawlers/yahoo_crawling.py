import requests
import json
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timezone, timedelta
import time
from urllib.parse import urljoin

# 메모리 기반 중복 제거
seen_urls = set()

class YahooFinanceNewsScraper:
    def __init__(self):
        self.base_url = "https://finance.yahoo.com"
        self.KST = timezone(timedelta(hours=9))
        self.UTC = timezone.utc
        
        # User-Agent 설정
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://finance.yahoo.com/',
        }
        
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def is_within_last_hour(self, kst_dt):
        """KST 기준 최근 1시간인지 판단"""
        if not isinstance(kst_dt, datetime):
            return False

        now_kst = datetime.now(self.KST)
        start_kst = now_kst - timedelta(hours=24)
        
        result = start_kst <= kst_dt <= now_kst
        
        print(f"[FILTER]")
        print(f"  기사: {kst_dt.strftime('%Y-%m-%d %H:%M:%S')} KST")
        print(f"  현재: {now_kst.strftime('%Y-%m-%d %H:%M:%S')} KST")
        print(f"  범위: {start_kst.strftime('%H:%M')} ~ {now_kst.strftime('%H:%M')} KST")
        print(f"  결과: {'✅ 통과' if result else '❌ 제외'}")
        
        return result


    def scrape_news_pages(self):
        """Yahoo Finance 뉴스 페이지에서 직접 스크래핑"""
        print("Yahoo Finance 원유 관련 뉴스 페이지 스크래핑 중...\n")
        news_links = set()
        
        news_pages = [
            'https://finance.yahoo.com/sector/energy/',
            'https://finance.yahoo.com/commodities',
            'https://finance.yahoo.com/topic/economic-news/',
            'https://finance.yahoo.com/topic/stock-market-news/',
            'https://finance.yahoo.com/news/',
            'https://finance.yahoo.com/topic/latest-news/',
            "https://finance.yahoo.com/quote/CL=F",
            "https://finance.yahoo.com/quote/BZ=F",
            "https://finance.yahoo.com/quote/NG=F",
            "https://finance.yahoo.com/quote/HO=F",
            "https://finance.yahoo.com/quote/RB=F",
            "https://finance.yahoo.com/industry/oil-gas/"
        ]
        
        for page_url in news_pages:
            try:
                print(f"📄 페이지: {page_url}")
                response = self.session.get(page_url, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ❌ 상태 코드: {response.status_code}\n")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    if '/news/' in href:
                        if href.startswith('/'):
                            full_url = urljoin(self.base_url, href)
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue
                        
                        clean_url = full_url.split('?')[0]

                        # ✔ URL 유효성 검사 제거
                        news_links.add(clean_url)
                
                print(f"   ✓ 수집: {len(news_links)}개\n")
                time.sleep(1)
                
            except Exception as e:
                print(f"   ❌ 오류: {e}\n")
                continue
        
        return list(news_links)


    def parse_article(self, url):
        """기사 파싱"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')

            article = {
                "url": url,
                "title": None,
                "content": None,
                "published_date": None 
            }

            title = None
            
            meta_title = soup.find("meta", property="og:title")
            if meta_title and meta_title.get("content"):
                title = meta_title.get("content")
            
            if not title:
                h1_tags = soup.find_all("h1")
                for h1 in h1_tags:
                    text = h1.get_text(strip=True)
                    if text and text != "Yahoo Finance" and len(text) > 8:
                        title = text
                        break

            if not title:
                title_tag = soup.find("title")
                if title_tag:
                    t = title_tag.get_text(strip=True)
                    title = t.replace(" - Yahoo Finance", "").replace(" - Yahoo", "")

            article["title"] = title if title else "No Title"

            # 본문 추출
            content_parts = []

            body = (
                soup.find("article")
                or soup.find("div", class_="caas-body")
                or soup.find("div", class_="article-body")
                or soup.find("div", {"data-test-locator": "article-content"})
            )

            if body:
                for p in body.find_all("p"):
                    txt = p.get_text(strip=True)
                    if len(txt) > 20:
                        content_parts.append(txt)

            if not content_parts:
                for p in soup.find_all("p")[:15]:
                    txt = p.get_text(strip=True)
                    if len(txt) > 20 and 'cookie' not in txt.lower():
                        content_parts.append(txt)

            article["content"] = "\n".join(content_parts) if content_parts else None

            if not article["content"]:
                print("⚠️ 본문 없음")
                return None

            # 시간 처리
            for tag in soup.find_all("time"):
                dt = tag.get("datetime")
                if dt:
                    try:
                        if 'Z' in dt:
                            utc_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                        elif '+' in dt:
                            utc_dt = datetime.fromisoformat(dt)
                        else:
                            utc_dt = datetime.fromisoformat(dt).replace(tzinfo=self.UTC)

                        kst_dt = utc_dt.astimezone(self.KST)

                        article["published_date"] = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        article["kst_time"] = kst_dt
                        return article

                    except Exception:
                        continue

            return None

        except Exception as e:
            print(f"❌ 파싱 실패: {e}")
            return None


    def scrape_news(self, max_articles=300):
        global seen_urls
        
        all_links = self.scrape_news_pages()
        
        print("="*60)
        print(f"총 수집된 링크: {len(all_links)}개")
        print("="*60)

        articles = []
        
        for idx, url in enumerate(all_links[:max_articles], 1):
            print(f"\n[{idx}/{min(len(all_links), max_articles)}] {url}")

            if url in seen_urls:
                print("⏭️ 중복 스킵")
                continue

            seen_urls.add(url)
            data = self.parse_article(url)

            if not data:
                print("⚠️ 기사 파싱 실패 또는 본문/날짜 없음")
                continue

            if not self.is_within_last_hour(data["kst_time"]):
                continue

            del data["kst_time"]
            articles.append(data)

            time.sleep(0.3)

        return pd.DataFrame(articles)


    def save_to_json(self, df, filename):
        if df.empty:
            print("❌ 저장할 데이터 없음")
            return
        
        data = df.to_dict(orient="records")
        json_text = json.dumps(data, indent=2, ensure_ascii=False)
        json_text = json_text.replace("\\/", "/")

        with open(filename, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"✅ 저장 완료 → {filename} (총 {len(df)}개 기사)")


def main():
    scraper = YahooFinanceNewsScraper()
    df = scraper.scrape_news(max_articles=300)

    if not df.empty:
        print("\n" + "="*60)
        print(f"✅ 수집 완료: 총 {len(df)}개 기사")
        print("="*60)
        print(df[["title", "published_date"]])
        scraper.save_to_json(df, "yahoo_finance_last1h.json")
    else:
        print("\n⚠️  최근 1시간 기사 없음.")


if __name__ == "__main__":
    main()