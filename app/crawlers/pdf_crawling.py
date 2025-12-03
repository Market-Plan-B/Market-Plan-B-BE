# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options
# from bs4 import BeautifulSoup
# from datetime import datetime
# import time, os, requests, redis

# def download_crude_oil_pdfs():
#     r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
#     redis_key = "crude_oil_reports"

#     url = "https://finance.naver.com/research/industry_list.naver?searchType=upjong&upjong=%BC%AE%C0%AF%C8%AD%C7%D0"
#     chrome_options = Options()
#     chrome_options.add_argument("--headless")
#     chrome_options.add_argument("--disable-gpu")
#     driver = webdriver.Chrome(options=chrome_options)

#     driver.get(url)
#     time.sleep(3)

#     soup = BeautifulSoup(driver.page_source, "html.parser")
#     driver.quit()

#     rows = soup.select("table.type_1 tbody tr")
#     # os.makedirs("crude_oil_reports", exist_ok=True)
#     headers = {"User-Agent": "Mozilla/5.0"}

#     today_str = datetime.today().strftime("%y.%m.%d")
#     count_new = 0
#     count_skip = 0

#     for row in rows:
#         pdf_tag = row.select_one("td.file a[href$='.pdf']")
#         title_tag = row.select_one("td:nth-child(2) a")
#         date_tag = row.select_one("td.date")

#         if not (pdf_tag and title_tag and date_tag):
#             continue

#         report_date = date_tag.text.strip()
#         if report_date != today_str:
#             continue

#         pdf_url = pdf_tag["href"]
#         title = title_tag.text.strip()

#         if r.sismember(redis_key, title):
#             count_skip += 1
#             continue

#         # pdf_data = requests.get(pdf_url, headers=headers).content
#         # filename = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_"))[:100]
#         # path = os.path.join("crude_oil_reports", f"{filename}.pdf")
#         # with open(path, "wb") as f:
#         #     f.write(pdf_data)

#         r.sadd(redis_key, title)
#         count_new += 1

# if __name__ == "__main__":
#     download_crude_oil_pdfs()
