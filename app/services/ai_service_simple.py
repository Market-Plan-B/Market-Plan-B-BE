"""
AI 서비스 간소화 버전 (테스트용)
daily_news_data 함수 호출 없이 직접 처리
"""
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
import pandas as pd
import json
import os

from app.ai.services.brent_data_pipeline import build_full_dataset
from app.ai.services.unstructured_refine import unstructure_refine
from app.ai.services.pipeline_inference import run_inference

from app.db.db_setting import Analytics, RecommendedStrategy, Report


def load_news_from_file_simple() -> list:
    """파일에서 뉴스 로드 (summary_embedding 포함된 파일)"""
    # embedded_news.json 또는 extra_embedded.json 사용
    possible_paths = [
        "app/ai/data/embedded_news.json",
        "app/ai/data/extra_embedded (1).json",
        "app/ai/repository/data/news/news_oil.json"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    # summary_embedding이 있는지 확인
                    if "summary_embedding" in data[0]:
                        print(f"뉴스 로드 완료: {path} ({len(data)}개)")
                        return data
    
    raise FileNotFoundError("summary_embedding이 포함된 뉴스 파일을 찾을 수 없습니다")


def run_modeling_simple(news_list: list, start_date: str) -> dict:
    """간소화된 모델링 실행"""
    df = build_full_dataset(news=news_list)
    # index를 DatetimeIndex로 변환
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    # 최근 60일 데이터 사용 (필터링 안함)
    df_filtered = df.tail(60) if len(df) > 60 else df
    df_refined = unstructure_refine(df_filtered)
    output = run_inference(news_list=news_list, df=df_refined)
    return output


def save_to_db_simple(db: Session, target_date: date, prediction_result: dict) -> dict:
    """DB 저장 (예측 결과만)"""
    pred = prediction_result.get("prediction", {})
    xai = prediction_result.get("xai", [])
    
    # Analytics 저장
    existing = db.query(Analytics).filter(Analytics.date == target_date).first()
    if existing:
        existing.overall_score = pred.get("pred_return", 0.0)
        existing.features = xai
        existing.variable_scores = {
            "current_close": pred.get("today_close", 0.0),
            "predicted_close": pred.get("predicted_next_close", 0.0)
        }
        db.commit()
        db.refresh(existing)
        return {"analytics": existing}
    
    db_analytics = Analytics(
        date=target_date,
        overall_score=pred.get("pred_return", 0.0),
        features=xai,
        variable_scores={
            "current_close": pred.get("today_close", 0.0),
            "predicted_close": pred.get("predicted_next_close", 0.0)
        }
    )
    
    db.add(db_analytics)
    db.commit()
    db.refresh(db_analytics)
    
    return {"analytics": db_analytics}


def run_ai_pipeline_simple(db: Session, date_str: str) -> dict:
    """
    간소화된 AI 파이프라인 (예측만)
    대응책/리포트 생성 제외
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # 1. 파일에서 뉴스 로드
    news_list = load_news_from_file_simple()
    
    # 2. 모델링 실행
    modeling_result = run_modeling_simple(news_list, date_str)
    
    # 3. DB 저장
    result = save_to_db_simple(db, target_date, modeling_result)
    
    return result
