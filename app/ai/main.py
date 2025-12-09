from app.ai.services.brent_data_pipeline import build_full_dataset
from app.ai.services.unstructured_refine import unstructure_refine
from app.ai.services.pipeline_inference import run_inference
from app.ai.services.unstructured_summary import daily_news_data
from app.ai.services.card2 import generate_top5_cards


import pandas as pd
import json


def db_load():
    """
    나중에 db 로드해서 사용할 함수 
    지금은 임시로 파일에서 가져오는 것으로

    """
    import os
    import json
    load_path = "app/ai/repository/data/news"

    # 해당 폴더에서 파일 하나 가져와서 json으로
    files = [f for f in os.listdir(load_path) if os.path.isfile(os.path.join(load_path, f))]
    first_file = files[0]

    # 파일 로드
    file_path = os.path.join(load_path, first_file)
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data

def daily_news(news):
    news_list = daily_news_data(news)

    return news_list

def daily_modeling(news_list):
    """
    하루치 가져와서 데이터 만들고 모델 돌리는 함수

    output = {
        "prediction": {
            "pred_return": pred_ret,
            "today_close": today_close,
            "predicted_next_close": pred_close
        },
        "xai": xai
    }

    """
    print("STEP 1: Building dataset (raw + cluster)...")
    df0, news_clusters = build_full_dataset(news=news_list)

    print("STEP 2: Refining dataset (news impact)...")
    df1 = unstructure_refine(df0)

    print("STEP 3: Running inference...")
    output = run_inference(news_list=news_list, df=df1)

    return output


data = db_load()
news_list = daily_news(data)
date = "2025-11-18"


result = daily_modeling(news_list)


# ===============================================================================================
# ===============================Card 생성======================================================
# ===============================================================================================

result = generate_top5_cards(
    news_list,
    output_dir="./" # 경로 지정해줄 고대영??
)
print(result["card_images"])


# ===============================================================================================
# ============================================ 대응책 ============================================
# ===============================================================================================

from app.ai.nodes.actiongenerator import actiongenerator
from app.ai.nodes.reportgenerator import reportgenerator
from datetime import datetime, timedelta
import pandas as pd
import json
from dotenv import load_dotenv

def build_compact_news_list(unstructured_data, max_news=5):
    compact_list = []

    for idx, item in enumerate(unstructured_data[:max_news], start=1):
        title = item.get('title', 'N/A')
        summary = item.get('summary', 'N/A')
        sentiment = item.get('sentiment', {}).get('score', 'N/A')
        trust = item.get('trust', {}).get('score', 'N/A')

        compact = (
            f'[뉴스 {idx}] '
            f'제목: {title} | '
            f'요약: {summary} | '
            f'영향도: {sentiment} | '
            f'신뢰도: {trust} | '
            f'본문 일부: {item.get("content")[:600]}'
        )

        compact_list.append(compact)
    compact_list = "\n".join(compact_list)
    return compact_list


# 대응책 날짜 설정해야됨
date = '2025-11-19'

d = datetime.strptime(date, "%Y-%m-%d")
prev_date = d - timedelta(days=1)

date_str = d.strftime("%Y-%m-%d")
prev_date_str = prev_date.strftime("%Y-%m-%d")

# 그래서 오늘 어제꺼만 들어감 
structured_data = pd.read_csv('data/llm_input_sample.csv') ## 여기에 모델 추론에 들어가는 데이터 데려오면 됨
filtered = structured_data[
    structured_data["Date"].isin([date_str, prev_date_str])
]

# 여기는 모델이 추론한 값 + xai 값 데려와야댐
# with open('data/prediction_2025_11_19.json', 'r', encoding='utf-8') as f:
#     xai_result=json.load(f)

model_prediction=result['prediction']
xai=result['xai']

# 얜 오늘 뉴스 들어온거 summary 된 것
with open('data/extra_embedded (1).json', 'r', encoding='utf-8') as f:
    unstructured_data = json.load(f)

news = build_compact_news_list(unstructured_data, max_news=5)

action=actiongenerator(date=date,
                       structured_data=filtered, 
                       model_prediction=model_prediction, 
                       xai_result=xai, 
                       unstructured_data=news)

print(action)
parsed_json = json.loads(action)


# 대응책 저장
with open("action_output.json", "w", encoding="utf-8") as f:
    json.dump(parsed_json, f, ensure_ascii=False, indent=2)



# ===============================================================================================
# ======================================== daily report =========================================
# ===============================================================================================

#위에꺼 + 대응책 넣어주는 것임
minimal_strategies = {
    "strategies": [
        {
            "name": s["name"],
            "horizon": s["horizon"],
            "objective": s["objective"],
            "actions": s["actions"],
            "data_evidence": s["data_evidence"],
            "risk_note": s["risk_note"],
        }
        for s in parsed_json["strategies"]
    ]
}

minimal_strategies_str = json.dumps(minimal_strategies, ensure_ascii=False, indent=2)

report = reportgenerator(
    date=date,
    structured_data=filtered,
    model_prediction=model_prediction,
    xai_result=xai,
    unstructured_data=news,
    precomputed_strategies=minimal_strategies_str
)

print(report)

with open("daily_report.html", "w", encoding="utf-8") as f:
    f.write(report)


# ==================================================================
# ========================위클리리포트=============================
# ==================================================================
from app.ai.services.data_pipeline import (
    build_report_sources,  # full_df, eia_objs, cot_weekly, cot_daily
    build_eia_weekly,
    build_cot_weekly,
)
from app.ai.nodes.weeklyreportgenerator import refine_weekly_news, build_weekly_report_payload, weeklyreportgenerator

"""
실제 yfinance + EIA + CFTC API를 호출하고,
로컬 JSON (뉴스/모델 output)까지 붙여서
Weekly Report를 생성하기.
"""

# 1) 리포트 기준일
END_DATE = "2025-11-19"

# 2) 리포트용 공통 데이터 소스 생성
sources = build_report_sources(end_date=END_DATE)

full_df = sources["full_df"]
eia_objs = sources["eia_objs"]
cot_weekly = sources["cot_weekly"]

# 3) 하루치 모델 output (예측 + XAI) 로드
with open("data/prediction_2025_11_19.json", "r", encoding="utf-8") as f:
    one_day_output = json.load(f)

# build_weekly_* 함수가 기대하는 daily_results 형태로 래핑
daily_model_results = [
    {
        "date": END_DATE,
        "prediction": one_day_output["prediction"],
        "xai": one_day_output.get("xai", []),
    }
]

# 5) 뉴스 로드
with open("data/extra_embedded (1).json", "r", encoding="utf-8") as f:
    raw_news = json.load(f)

if isinstance(raw_news, list):
    news_weekly = raw_news
elif isinstance(raw_news, dict):
    if "data" in raw_news:
        news_weekly = raw_news["data"]
    elif "items" in raw_news:
        news_weekly = raw_news["items"]
    else:
        news_weekly = [raw_news]
else:
    news_weekly = []

news_weekly = refine_weekly_news(news_weekly)


# 7) 주간 리포트 payload 생성
payload = build_weekly_report_payload(
    end_date=END_DATE,
    full_df=full_df,
    daily_model_results=daily_model_results,
    news_weekly=news_weekly,
    eia_objs=eia_objs,
    cot_weekly=cot_weekly,
)

# 8) LLM 호출로 HTML 리포트 생성
html = weeklyreportgenerator(payload)

print(html)
