from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import pandas as pd
import re

from app.ai.nodes.weeklyreportgenerator import weeklyreportgenerator, build_weekly_report_payload
from app.ai.services.brent_data_pipeline import build_full_dataset
from app.db.db_setting import Report


def get_last_7_days_reports(db: Session, end_date: datetime) -> list:
    """최근 7일간의 daily report 데이터 조회"""
    start_date = end_date - timedelta(days=6)
    
    reports = db.query(Report).filter(
        Report.report_type == 'daily',
        Report.start_date >= start_date.date(),
        Report.start_date <= end_date.date()
    ).order_by(Report.start_date).all()
    
    return reports


def extract_daily_model_results(reports: list) -> list:
    """daily report에서 모델 예측 결과 추출"""
    daily_results = []
    
    for report in reports:
        daily_results.append({
            "date": report.start_date,
            "prediction": {
                "pred_return": 0.0,
                "today_close": 0.0,
                "predicted_next_close": 0.0,
            },
            "xai": []
        })
    
    return daily_results


def generate_weekly_report(db: Session, end_date: datetime) -> Report:
    """주간 리포트 생성"""
    start_date = end_date - timedelta(days=6)
    
    # 1. 최근 7일 daily report 조회
    daily_reports = get_last_7_days_reports(db, end_date)
    
    if len(daily_reports) < 7:
        raise ValueError(f"7일치 데이터 부족: {len(daily_reports)}개만 존재")
    
    # 2. 모델 결과 추출
    daily_model_results = extract_daily_model_results(daily_reports)
    
    # 3. 데이터 준비
    full_df = build_full_dataset(news=[])
    if not isinstance(full_df.index, pd.DatetimeIndex):
        full_df.index = pd.to_datetime(full_df.index)
    
    # 4. payload 생성
    payload = build_weekly_report_payload(
        end_date=end_date.strftime("%Y-%m-%d"),
        full_df=full_df,
        daily_model_results=daily_model_results,
        news_weekly=[],
        eia_objs=[],
        cot_weekly=pd.DataFrame(),
    )
    
    # 5. 주간 리포트 생성
    report_html = weeklyreportgenerator(payload)
    
    # 6. HTML body 추출
    body_match = re.search(r'<body[^>]*>(.*?)</body>', report_html, re.DOTALL | re.IGNORECASE)
    body_content = body_match.group(1) if body_match else report_html
    
    # 7. reports 테이블에 저장
    existing = db.query(Report).filter(
        Report.report_type == 'weekly',
        Report.start_date == start_date.date(),
        Report.end_date == end_date.date()
    ).first()
    
    if existing:
        existing.html_content = body_content
        db.commit()
        db.refresh(existing)
        return existing
    
    weekly_report = Report(
        report_type='weekly',
        start_date=start_date.date(),
        end_date=end_date.date(),
        html_content=body_content
    )
    
    db.add(weekly_report)
    db.commit()
    db.refresh(weekly_report)
    
    return weekly_report
