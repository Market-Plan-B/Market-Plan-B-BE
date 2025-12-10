"""
AI 전체 파이프라인 (예측 + 대응책 + 리포트 + DB 저장)
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

from app.db.db_setting import Analytics, RecommendedStrategy, Report, Content, Region, ReportContent, ContentRegion
from app.db.db_setting import Notification
from app.services.chroma_service import chroma_service

# ISO 국가 코드 매핑
COUNTRY_CODES = {
    "미국": "USA", "United States": "USA", "USA": "USA",
    "중국": "CN", "China": "CN",
    "러시아": "RU", "Russia": "RU",
    "사우디아라비아": "SA", "Saudi Arabia": "SA",
    "이란": "IR", "Iran": "IR",
    "이라크": "IQ", "Iraq": "IQ",
    "UAE": "AE", "아랍에미리트": "AE",
    "한국": "KR", "대한민국": "KR", "South Korea": "KR",
    "일본": "JP", "Japan": "JP",
    "독일": "DE", "Germany": "DE",
    "영국": "GB", "UK": "GB", "United Kingdom": "GB",
    "프랑스": "FR", "France": "FR",
}


def get_country_code(country_name: str) -> str:
    """국가명을 ISO 코드로 변환"""
    return COUNTRY_CODES.get(country_name, "XX")


def load_news_from_json(json_path: str) -> list:
    """크롤링된 JSON 파일에서 뉴스 로드"""
    with open(json_path, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    
    if not isinstance(news_data, list):
        news_data = [news_data]
    
    return news_data


def build_compact_news_list(unstructured_data: list, max_news: int = 5) -> str:
    """뉴스 압축"""
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


def save_analytics(db: Session, target_date: date, prediction_result: dict, df: pd.DataFrame) -> Analytics:
    """analytics 테이블 저장"""
    pred = prediction_result.get("prediction", {})
    
    structured_features = {}
    for col in df.columns:
        if col not in ['brent_close', 'wti_close', 'date']:
            structured_features[col] = df[col].tail(1).tolist()
    
    existing = db.query(Analytics).filter(Analytics.date == target_date).first()
    if existing:
        existing.overall_score = pred.get("pred_return", 0.0)
        existing.features = structured_features
        db.commit()
        db.refresh(existing)
        return existing
    
    db_analytics = Analytics(
        date=target_date,
        overall_score=pred.get("pred_return", 0.0),
        features=structured_features
    )
    
    db.add(db_analytics)
    db.commit()
    db.refresh(db_analytics)
    
    return db_analytics


def save_contents(db: Session, news_list: list) -> list:
    """contents 테이블 저장 + contents_regions 연결"""
    saved_contents = []
    
    for news in news_list:
        existing = db.query(Content).filter(Content.url == news.get("url")).first()
        if existing:
            saved_contents.append(existing)
            continue
        
        sentiment = news.get("sentiment") or {}
        sentiment_score = sentiment.get("score", 0.0) if isinstance(sentiment, dict) else 0.0
        
        db_content = Content(
            title=news.get("title", ""),
            summary=news.get("summary", ""),
            source_score=sentiment_score,
            url=news.get("url", ""),
            published_at=pd.to_datetime(news.get("published")) if news.get("published") else None
        )
        
        db.add(db_content)
        db.flush()  # content.id 생성
        
        # contents_regions 연결
        relation_nations = news.get("relation_nation", [])
        if isinstance(relation_nations, list):
            for item in relation_nations:
                if isinstance(item, dict):
                    country_name = item.get("name")
                    if country_name:
                        region = db.query(Region).filter(Region.name == country_name).first()
                        if region:
                            # 중복 체크
                            existing_link = db.query(ContentRegion).filter(
                                ContentRegion.content_id == db_content.id,
                                ContentRegion.region_id == region.id
                            ).first()
                            
                            if not existing_link:
                                content_region = ContentRegion(
                                    content_id=db_content.id,
                                    region_id=region.id
                                )
                                db.add(content_region)
        
        saved_contents.append(db_content)
    
    db.commit()
    
    for content in saved_contents:
        db.refresh(content)
    
    return saved_contents

def save_to_chroma(news_list: list) -> int:
    """Chroma DB에 벡터 저장"""
    try:
        chroma_count = chroma_service.add_news_embeddings(news_list)
        print(f"Chroma DB 저장 완료: {chroma_count}개 뉴스")
        return chroma_count
    except Exception as e:
        print(f"Chroma DB 저장 실패: {e}")
        return 0


def save_regions(db: Session, news_list: list):
    """regions 테이블 업데이트"""
    countries = {}
    
    print(f"[save_regions] 뉴스 개수: {len(news_list)}")
    
    for news in news_list:
        relation_nations = news.get("relation_nation", [])
        
        if not relation_nations:
            continue
            
        if isinstance(relation_nations, list):
            for item in relation_nations:
                if isinstance(item, dict):
                    name = item.get("name")
                    code = item.get("code")
                    if name:
                        countries[name] = code
                        print(f"[save_regions] 발견된 국가: {name} ({code})")
    
    print(f"[save_regions] 총 {len(countries)}개 국가 발견")
    
    if not countries:
        print("[save_regions] Warning: relation_nation 데이터가 없습니다")
        return
    
    for name, code in countries.items():
        try:
            existing = db.query(Region).filter(Region.name == name).first()
            if existing:
                if code:
                    existing.code = code
                print(f"[save_regions] 업데이트: {name}")
            else:
                db_region = Region(
                    name=name,
                    code=code or "XX",
                    region_score=0.0
                )
                db.add(db_region)
                print(f"[save_regions] 신규 추가: {name} ({code})")
        except Exception as e:
            print(f"[save_regions] 에러 ({name}): {e}")
    
    try:
        db.commit()
        print(f"[save_regions] DB 커밋 완료")
    except Exception as e:
        print(f"[save_regions] 커밋 실패: {e}")
        db.rollback()
        raise


def update_region_scores(db: Session, news_list: list):
    """contents 저장 후 region_score 계산 및 업데이트"""
    country_scores = {}
    
    print(f"[update_region_scores] 뉴스 개수: {len(news_list)}")
    
    for news in news_list:
        sentiment = news.get("sentiment") or {}
        sentiment_score = sentiment.get("score", 0.0) if isinstance(sentiment, dict) else 0.0
        
        relation_nations = news.get("relation_nation", [])
        if isinstance(relation_nations, list):
            for item in relation_nations:
                if isinstance(item, dict):
                    name = item.get("name")
                    if name:
                        if name not in country_scores:
                            country_scores[name] = []
                        country_scores[name].append(abs(float(sentiment_score)))
    
    print(f"[update_region_scores] {len(country_scores)}개 국가의 점수 계산")
    
    for country, scores in country_scores.items():
        region = db.query(Region).filter(Region.name == country).first()
        if region and scores:
            avg_score = sum(scores) / len(scores)
            region.region_score = avg_score
            print(f"[update_region_scores] {country}: {avg_score:.4f}")
    
    try:
        db.commit()
        print(f"[update_region_scores] DB 커밋 완료")
    except Exception as e:
        print(f"[update_region_scores] 커밋 실패: {e}")
        db.rollback()
        raise


def save_strategies(db: Session, action_content: dict) -> list:
    """recommended_strategies 테이블 저장"""
    strategies = action_content.get("strategies", [])
    
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


def save_report(db: Session, target_date: date, report_html: str, content_ids: list, card_images: list = None) -> Report:
    """reports 테이블 저장"""
    # HTML body 내부만 추출
    import re
    body_match = re.search(r'<body[^>]*>(.*?)</body>', report_html, re.DOTALL | re.IGNORECASE)
    body_content = body_match.group(1) if body_match else report_html
    
    if card_images is None:
        card_images = []
    
    existing = db.query(Report).filter(
        Report.report_type == 'daily',
        Report.start_date == target_date
    ).first()
    
    if existing:
        existing.html_content = body_content
        existing.images = card_images
        db.commit()
        db.refresh(existing)
        report = existing
    else:
        db_report = Report(
            report_type='daily',
            start_date=target_date,
            end_date=target_date,
            html_content=body_content,
            images=card_images
        )
        db.add(db_report)
        db.commit()
        db.refresh(db_report)
        report = db_report
    
    # reports_contents 연결
    db.query(ReportContent).filter(ReportContent.report_id == report.id).delete()
    
    for content_id in content_ids:
        db_rc = ReportContent(
            report_id=report.id,
            content_id=content_id
        )
        db.add(db_rc)
    
    db.commit()
    
    return report


def run_full_pipeline(db: Session, target_datetime: datetime, json_path: str) -> dict:
    """
    전체 AI 파이프라인 실행
    크롤링된 JSON 파일에서 24시간 뉴스 사용
    """
    target_date = target_datetime.date()
    date_str = target_date.strftime("%Y-%m-%d")
    
    # 1. JSON 파일에서 뉴스 로드
    raw_news = load_news_from_json(json_path)
    
    if not raw_news:
        raise ValueError(f"{json_path} 파일에 뉴스 데이터가 없습니다")
    
    # 2. 뉴스 처리 (임베딩이 이미 있으면 스킵)
    if raw_news and "summary_embedding" in raw_news[0]:
        news_list = raw_news
    else:
        news_list = daily_news_data(raw_news)
    
    # 3. regions 저장
    save_regions(db, news_list)
    
    # 4. contents 저장
    saved_contents = save_contents(db, news_list)
    content_ids = [c.id for c in saved_contents]
    
    # 5. Chroma DB에 벡터 저장
    save_to_chroma(news_list)
    
    # 6. region_score 업데이트
    update_region_scores(db, news_list)
    
    # 7. 모델링 실행
    df, _ = build_full_dataset(news=news_list)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df_filtered = df.tail(60) if len(df) > 60 else df
    df_refined = unstructure_refine(df_filtered)
    modeling_result = run_inference(news_list=news_list, df=df_refined)
    
    # 8. analytics 저장
    db_analytics = save_analytics(db, target_date, modeling_result, df_filtered)
    
    # 10. 뉴스 압축
    news_compact = build_compact_news_list(news_list, max_news=5)
    
    # 11. 대응책 생성
    try:
        action_result = actiongenerator(
            date=date_str,
            structured_data=df_refined,
            model_prediction=modeling_result["prediction"],
            xai_result=modeling_result["xai"],
            unstructured_data=news_compact
        )
        action_dict = json.loads(action_result) if action_result else {"strategies": []}
    except Exception as e:
        print(f"Warning: 대응책 생성 실패 - {e}")
        action_dict = {"strategies": []}
    
    # 12. strategies 저장
    db_strategies = save_strategies(db, action_dict)
    
    # 13. 리포트 생성
    try:
        report_html = reportgenerator(
            date=date_str,
            structured_data=df_refined,
            model_prediction=modeling_result["prediction"],
            xai_result=modeling_result["xai"],
            unstructured_data=news_compact,
            precomputed_strategies=json.dumps({
                "strategies": [
                    {
                        "name": s["name"],
                        "horizon": s["horizon"],
                        "objective": s["objective"],
                        "actions": s["actions"],
                        "data_evidence": s["data_evidence"],
                        "risk_note": s["risk_note"],
                    }
                    for s in action_dict.get("strategies", [])
                ]
            }, ensure_ascii=False)
        )
    except Exception as e:
        print(f"Warning: 리포트 생성 실패 - {e}")
        report_html = "<html><body><h1>Report Generation Failed</h1></body></html>"
    
    # 14. 카드뉴스 이미지 생성
    card_images = []
    try:
        from app.ai.services.card2 import generate_top5_cards
        card_result = generate_top5_cards(news_list)
        card_images = [img["base64"] for img in card_result.get("card_images", [])]
        print(f"Card images generated: {len(card_images)}")
    except Exception as e:
        print(f"Warning: 카드뉴스 생성 실패 - {e}")
    
    # 15. report 저장
    db_report = save_report(db, target_date, report_html, content_ids, card_images)
    
    return {
        "analytics": db_analytics,
        "strategies": db_strategies,
        "report": db_report,
        "contents": saved_contents
    }


def create_notification(db, user_id: int, content_id: int):
    notif = Notification(
        user_id=user_id,
        content_id=content_id,
        is_read=False,
        read_at=None,
        created_at=datetime.utcnow()
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif