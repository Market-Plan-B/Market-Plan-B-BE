"""
AI 모델 실행 및 결과 저장 서비스
- 일일 모델링 실행
- 대응책 생성
- 리포트 생성
- 기존 DB 테이블에 저장
"""
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
import pandas as pd
import json
import os

from app.ai.services.brent_data_pipeline import build_full_dataset
from app.ai.services.unstructured_refine import unstructure_refine
from app.ai.services.pipeline_inference import run_inference
from app.ai.services.unstructured_summary import daily_news_data
from app.ai.nodes.actiongenerator import actiongenerator
from app.ai.nodes.reportgenerator import reportgenerator

from app.db.db_setting import Analytics, RecommendedStrategy, Report, Content


def load_news_from_file() -> list:
    """
    테스트용: 파일에서 뉴스 데이터 로드
    app/ai/repository/data/news 폴더의 첫 번째 JSON 파일 사용
    """
    load_path = "app/ai/repository/data/news"
    
    if not os.path.exists(load_path):
        raise FileNotFoundError(f"{load_path} 폴더가 없습니다")
    
    files = [f for f in os.listdir(load_path) if f.endswith('.json')]
    
    if not files:
        raise FileNotFoundError(f"{load_path}에 JSON 파일이 없습니다")
    
    file_path = os.path.join(load_path, files[0])
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 리스트가 아니면 리스트로 변환
    if not isinstance(data, list):
        data = [data]
    
    return data


def load_news_from_db(db: Session, start_time: datetime, end_time: datetime) -> list:
    """
    실제 운영용: DB에서 뉴스 데이터 로드
    전날 06시 ~ 당일 06시 데이터 조회
    """
    news_records = db.query(Content).filter(
        Content.published_at >= start_time,
        Content.published_at < end_time
    ).all()
    
    # DB 레코드를 AI 모델 입력 형식으로 변환
    news_list = []
    for record in news_records:
        news_list.append({
            "title": record.title,
            "summary": record.summary or "",
            "content": record.summary or "",  # content 필드가 없으면 summary 사용
            "published": record.published_at.isoformat() if record.published_at else None,
            "url": record.url,
            "sentiment": {"score": float(record.source_score) if record.source_score else 0.0},
            "trust": {"score": float(record.source_score) if record.source_score else 0.0}
        })
    
    return news_list


def build_compact_news_list(unstructured_data: list, max_news: int = 5) -> str:
    """뉴스 데이터를 압축된 문자열로 변환"""
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
            f'본문 일부: {item.get("content", "")[:600]}'
        )
        compact_list.append(compact)
    
    return "\n".join(compact_list)


def run_daily_modeling(news_list: list, start_date: str = "2025-11-18") -> dict:
    """
    일일 모델링 실행
    
    Returns:
        {"prediction": {...}, "xai": [...]}
    """
    df = build_full_dataset(news=news_list)
    df_filtered = df[df.index >= pd.to_datetime(start_date)]
    df_refined = unstructure_refine(df_filtered)
    output = run_inference(news_list=news_list, df=df_refined)
    
    return output


def generate_action_plan(
    date: str,
    structured_data: pd.DataFrame,
    model_prediction: dict,
    xai_result: list,
    unstructured_data: str
) -> dict:
    """대응책 생성"""
    action_json_str = actiongenerator(
        date=date,
        structured_data=structured_data,
        model_prediction=model_prediction,
        xai_result=xai_result,
        unstructured_data=unstructured_data
    )
    
    return json.loads(action_json_str)


def generate_daily_report(
    date: str,
    structured_data: pd.DataFrame,
    model_prediction: dict,
    xai_result: list,
    unstructured_data: str,
    action_strategies: dict
) -> str:
    """일일 리포트 생성 (HTML)"""
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
            for s in action_strategies.get("strategies", [])
        ]
    }
    
    minimal_strategies_str = json.dumps(minimal_strategies, ensure_ascii=False, indent=2)
    
    report_html = reportgenerator(
        date=date,
        structured_data=structured_data,
        model_prediction=model_prediction,
        xai_result=xai_result,
        unstructured_data=unstructured_data,
        precomputed_strategies=minimal_strategies_str
    )
    
    return report_html


# ============================================
# 기존 DB 테이블에 저장
# ============================================

def save_prediction_to_analytics(db: Session, target_date: date, prediction_result: dict) -> Analytics:
    """
    예측 결과를 analytics 테이블에 저장
    
    매핑:
    - date: 예측 날짜
    - overall_score: 예측 수익률 (predicted_return)
    - features: XAI 피처 중요도 (JSON)
    - variable_scores: 예측 가격 정보 (JSON)
    """
    pred = prediction_result.get("prediction", {})
    xai = prediction_result.get("xai", [])
    
    # 기존 데이터 확인 (중복 방지)
    existing = db.query(Analytics).filter(Analytics.date == target_date).first()
    if existing:
        # 업데이트
        existing.overall_score = pred.get("pred_return", 0.0)
        existing.features = xai
        existing.variable_scores = {
            "current_close": pred.get("today_close", 0.0),
            "predicted_close": pred.get("predicted_next_close", 0.0)
        }
        db.commit()
        db.refresh(existing)
        return existing
    
    # 신규 생성
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
    
    return db_analytics


def save_action_to_strategies(db: Session, target_date: date, action_content: dict) -> list:
    """
    대응책을 recommended_strategies 테이블에 저장
    여러 전략을 각각 별도 행으로 저장
    """
    strategies = action_content.get("strategies", [])
    
    # 기존 데이터 삭제 (날짜 기준)
    db.query(RecommendedStrategy).filter(
        RecommendedStrategy.created_at >= target_date
    ).delete()
    
    saved_strategies = []
    
    for strategy in strategies:
        db_strategy = RecommendedStrategy(
            name=strategy.get("name", ""),
            horizon=strategy.get("horizon", ""),
            objective=strategy.get("objective", ""),
            preconditions=strategy.get("preconditions"),
            actions=strategy.get("actions", []),
            data_evidence=strategy.get("data_evidence", {}),
            risk_note=strategy.get("risk_note")
        )
        db.add(db_strategy)
        saved_strategies.append(db_strategy)
    
    db.commit()
    
    for s in saved_strategies:
        db.refresh(s)
    
    return saved_strategies


def save_report_to_reports(db: Session, target_date: date, report_html: str) -> Report:
    """
    일일 리포트를 reports 테이블에 저장
    
    매핑:
    - report_type: 'daily' 고정
    - start_date: 리포트 날짜
    - end_date: 리포트 날짜 (동일)
    - html_content: AI 생성 HTML
    """
    # 기존 데이터 확인
    existing = db.query(Report).filter(
        Report.report_type == 'daily',
        Report.start_date == target_date
    ).first()
    
    if existing:
        existing.html_content = report_html
        db.commit()
        db.refresh(existing)
        return existing
    
    db_report = Report(
        report_type='daily',
        start_date=target_date,
        end_date=target_date,
        html_content=report_html
    )
    
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    
    return db_report


# ============================================
# 전체 파이프라인 실행
# ============================================

def run_full_ai_pipeline_test(db: Session, date_str: str) -> dict:
    """
    테스트용: 파일에서 뉴스 로드 후 AI 파이프라인 실행
    
    Args:
        db: DB 세션
        date_str: 실행 날짜 (YYYY-MM-DD)
    
    Returns:
        {
            "prediction": Analytics,
            "action": RecommendedStrategy,
            "report": Report
        }
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    
    # 1. 파일에서 뉴스 로드 (테스트용)
    news_data = load_news_from_file()
    news_list = daily_news_data(news_data)
    
    # 2. 모델링 실행
    modeling_result = run_daily_modeling(news_list, start_date=date_str)
    
    # 3. 정형 데이터 준비 (임시: 빈 DataFrame)
    filtered_data = pd.DataFrame()
    
    # 4. 뉴스 압축
    news_compact = build_compact_news_list(news_list, max_news=5)
    
    # 5. 대응책 생성
    action_result = generate_action_plan(
        date=date_str,
        structured_data=filtered_data,
        model_prediction=modeling_result["prediction"],
        xai_result=modeling_result["xai"],
        unstructured_data=news_compact
    )
    
    # 6. 리포트 생성
    report_html = generate_daily_report(
        date=date_str,
        structured_data=filtered_data,
        model_prediction=modeling_result["prediction"],
        xai_result=modeling_result["xai"],
        unstructured_data=news_compact,
        action_strategies=action_result
    )
    
    # 7. DB 저장
    db_analytics = save_prediction_to_analytics(db, target_date, modeling_result)
    db_strategy = save_action_to_strategies(db, target_date, action_result)
    db_report = save_report_to_reports(db, target_date, report_html)
    
    return {
        "prediction": db_analytics,
        "action": db_strategy,
        "report": db_report
    }


def run_full_ai_pipeline_production(db: Session, target_datetime: datetime) -> dict:
    """
    실제 운영용: DB에서 뉴스 로드 후 AI 파이프라인 실행
    전날 06시 ~ 당일 06시 데이터 사용
    
    Args:
        db: DB 세션
        target_datetime: 실행 시점 (예: 2025-11-19 06:00:00)
    
    Returns:
        {
            "prediction": Analytics,
            "action": RecommendedStrategy,
            "report": Report
        }
    """
    # 전날 06시 ~ 당일 06시 범위 계산
    end_time = target_datetime.replace(hour=6, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)
    
    target_date = target_datetime.date()
    date_str = target_date.strftime("%Y-%m-%d")
    
    # 1. DB에서 뉴스 로드
    news_data = load_news_from_db(db, start_time, end_time)
    
    if not news_data:
        raise ValueError(f"{start_time} ~ {end_time} 범위에 뉴스 데이터가 없습니다")
    
    news_list = daily_news_data(news_data)
    
    # 2. 모델링 실행
    modeling_result = run_daily_modeling(news_list, start_date=date_str)
    
    # 3. 정형 데이터 준비 (임시: 빈 DataFrame)
    filtered_data = pd.DataFrame()
    
    # 4. 뉴스 압축
    news_compact = build_compact_news_list(news_list, max_news=5)
    
    # 5. 대응책 생성
    action_result = generate_action_plan(
        date=date_str,
        structured_data=filtered_data,
        model_prediction=modeling_result["prediction"],
        xai_result=modeling_result["xai"],
        unstructured_data=news_compact
    )
    
    # 6. 리포트 생성
    report_html = generate_daily_report(
        date=date_str,
        structured_data=filtered_data,
        model_prediction=modeling_result["prediction"],
        xai_result=modeling_result["xai"],
        unstructured_data=news_compact,
        action_strategies=action_result
    )
    
    # 7. DB 저장
    db_analytics = save_prediction_to_analytics(db, target_date, modeling_result)
    db_strategy = save_action_to_strategies(db, target_date, action_result)
    db_report = save_report_to_reports(db, target_date, report_html)
    
    return {
        "prediction": db_analytics,
        "action": db_strategy,
        "report": db_report
    }
