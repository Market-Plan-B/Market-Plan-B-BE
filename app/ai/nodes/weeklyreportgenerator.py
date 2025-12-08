# app/ai/services/weeklyreportgenerator.py


from app.ai.models.llm import llm_text_format
from app.ai.services.prompt_structure_korean import weeklyreport_prompt

from app.ai.services.data_pipeline import (
    build_report_sources,  # full_df, eia_objs, cot_weekly, cot_daily
    build_eia_weekly,
    build_cot_weekly,
)

from langchain_core.prompts import PromptTemplate
from collections import defaultdict
import json
import pandas as pd



# == 필요 함수 ==
def build_weekly_report_payload(
    end_date,
    full_df,
    daily_model_results,  
    news_weekly,
    eia_objs,
    cot_weekly,
):

    end = pd.to_datetime(end_date)
    start = end - pd.Timedelta(days=6)

    weekly_df = full_df[(full_df["date"] >= start) & (full_df["date"] <= end)]

    model_pred_list = build_weekly_predictions(end_date, daily_model_results)
    xai_summary = build_weekly_xai(end_date, daily_model_results)

    return {
        "week_start": str(start.date()),
        "week_end": str(end.date()),

        "market_trend": {
            "brent_close": weekly_df["brent_close"].tolist(),
            "wti_close": weekly_df["wti_close"].tolist(),
            "spread": (weekly_df["brent_close"] - weekly_df["wti_close"]).tolist(),
            "volatility": weekly_df["brent_vol_5d"].tolist(),
        },

        "weekly_fundamentals": {
            "eia": build_eia_weekly(end_date, eia_objs),
            "cot": build_cot_weekly(end_date, cot_weekly),
        },

        "weekly_predictions": model_pred_list,
        "weekly_xai": xai_summary,
        "weekly_news": news_weekly,
    }

def build_weekly_predictions(end_date, daily_results):
    """
    end_date 기준 7일(= end_date - 6 ~ end_date)의
    모델 예측들을 리스트로 반환.

    daily_results: 위에서 가정한 list[dict] 구조
    """
    end = pd.to_datetime(end_date)
    start = end - pd.Timedelta(days=6)

    rows = []
    for item in daily_results:
        d = pd.to_datetime(item["date"])
        if not (start <= d <= end):
            continue

        pred = item["prediction"]
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "pred_return": float(pred["pred_return"]),
            "today_close": float(pred["today_close"]),
            "predicted_next_close": float(pred["predicted_next_close"]),
        })

    # 날짜순 정렬
    rows = sorted(rows, key=lambda x: x["date"])
    return rows

def build_weekly_xai(end_date, daily_results, top_n_daily=5, top_n_weekly=10):
    end = pd.to_datetime(end_date)
    start = end - pd.Timedelta(days=6)

    # 1) 일별 top-k
    daily_top_features = []
    # 2) 주간 평균용 누적
    agg_importance = defaultdict(list)

    for item in daily_results:
        d = pd.to_datetime(item["date"])
        if not (start <= d <= end):
            continue

        xai_list = item.get("xai", [])
        if not xai_list:
            continue

        # 중요도 기준 정렬
        sorted_xai = sorted(
            xai_list,
            key=lambda x: x.get("importance", 0),
            reverse=True
        )

        # 일별 top-k
        top_k = sorted_xai[:top_n_daily]
        daily_top_features.append({
            "date": d.strftime("%Y-%m-%d"),
            "top_features": [f["feature"] for f in top_k]
        })

        # 주간 집계용 (모든 feature importance 누적)
        for row in xai_list:
            f = row["feature"]
            imp = float(row.get("importance", 0.0))
            agg_importance[f].append(imp)

    # 주간 평균 중요도 계산
    weekly_aggregated = []
    for f, vals in agg_importance.items():
        if len(vals) == 0:
            continue
        weekly_aggregated.append({
            "feature": f,
            "avg_importance": float(sum(vals) / len(vals)),
        })

    weekly_aggregated.sort(key=lambda x: x["avg_importance"], reverse=True)
    weekly_aggregated = weekly_aggregated[:top_n_weekly]

    return {
        "daily_top_features": daily_top_features,
        "weekly_aggregated": weekly_aggregated,
    }

def refine_weekly_news(raw_news):
    cleaned = []
    for item in raw_news:
        pub = item.get("published") or item.get("date") or ""
        summ = item.get("summary") or item.get("content", "")[:200]

        cleaned.append({
            "published": pub,
            "summary": summ,
        })
    return cleaned


# == 보고서 작성 함수 ==
def weeklyreportgenerator(payload):
    """
    payload = build_weekly_report_payload() 의 결과
    """

    # === 1) 프롬프트 템플릿 ===
    template = PromptTemplate(
        input_variables=weeklyreport_prompt["input_variables"],
        template=weeklyreport_prompt["template"],
    )

    # === 2) 각 데이터 문자열화(JSON pretty format) ===
    market_trend_str = json.dumps(
        payload["market_trend"], ensure_ascii=False, indent=2
    )
    weekly_fundamentals_str = json.dumps(
        payload["weekly_fundamentals"], ensure_ascii=False, indent=2
    )

    pred_str = json.dumps(payload["weekly_predictions"], ensure_ascii=False, indent=2)
    xai_str = json.dumps(payload["weekly_xai"], ensure_ascii=False, indent=2)
    news_str = json.dumps(payload["weekly_news"], ensure_ascii=False, indent=2)

    # === 3) LLM 입력 prompt 생성 ===
    final_prompt = template.format(
        role=weeklyreport_prompt["role"],
        rules=weeklyreport_prompt["rules"],
        output_schema=weeklyreport_prompt["output_schema"],
        week_start=payload["week_start"],
        week_end=payload["week_end"],
        market_trend=market_trend_str,
        weekly_fundamentals=weekly_fundamentals_str,
        weekly_predictions=pred_str,
        weekly_xai=xai_str,
        weekly_news=news_str,
    )

    print("### Weekly Report Prompt ###")
    print(final_prompt)

    # === 4) LLM 실행 ===
    try:
        response = (template | llm_text_format).invoke(
            {
                "role": weeklyreport_prompt["role"],
                "rules": weeklyreport_prompt["rules"],
                "output_schema": weeklyreport_prompt["output_schema"],
                "week_start": payload["week_start"],
                "week_end": payload["week_end"],
                "market_trend": market_trend_str,
                "weekly_fundamentals": weekly_fundamentals_str,
                "weekly_predictions": pred_str,
                "weekly_xai": xai_str,
                "weekly_news": news_str,
            }
        )

        return response.content

    except Exception as e:
        return f"weeklyreportgenerator error: {str(e)}"
