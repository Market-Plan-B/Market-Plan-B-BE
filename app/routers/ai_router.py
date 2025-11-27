"""
AI 관련 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.database import get_db
from app.services.ai_service_simple import run_ai_pipeline_simple
from app.db.db_setting import Analytics, RecommendedStrategy, Report

router = APIRouter(
    prefix="/ai",
    tags=["AI Prediction & Analysis"]
)


@router.post("/run-prediction")
async def run_ai_prediction(
    date: str,  # YYYY-MM-DD
    use_file: bool = True,  # True: 파일에서 로드 (테스트), False: DB에서 로드 (운영)
    db: Session = Depends(get_db)
):
    """
    AI 예측 파이프라인 실행
    
    Args:
        date: 예측 날짜 (YYYY-MM-DD)
        use_file: True=파일에서 뉴스 로드 (테스트), False=DB에서 뉴스 로드 (운영)
    
    Returns:
        실행 결과 요약
    """
    try:
        # 간소화 버전 사용 (예측만)
        result = run_ai_pipeline_simple(db, date)
        
        return {
            "status": "success",
            "message": f"{date} AI 예측 완료",
            "analytics_id": result["analytics"].id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 예측 실행 실패: {str(e)}")


@router.get("/predictions/{date}")
async def get_prediction_by_date(
    date: str,  # YYYY-MM-DD
    db: Session = Depends(get_db)
):
    """특정 날짜의 예측 결과 조회"""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        prediction = db.query(Analytics).filter(Analytics.date == target_date).first()
        
        if not prediction:
            raise HTTPException(status_code=404, detail=f"{date} 예측 결과를 찾을 수 없습니다")
        
        return {
            "id": prediction.id,
            "date": prediction.date.strftime("%Y-%m-%d"),
            "predicted_return": float(prediction.overall_score) if prediction.overall_score else 0.0,
            "price_info": prediction.variable_scores,
            "xai_explanation": prediction.features,
            "created_at": prediction.created_at
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/{date}")
async def get_action_by_date(
    date: str,  # YYYY-MM-DD
    db: Session = Depends(get_db)
):
    """특정 날짜의 대응책 조회"""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        strategies = db.query(RecommendedStrategy).filter(
            RecommendedStrategy.created_at >= target_date
        ).all()
        
        if not strategies:
            raise HTTPException(status_code=404, detail=f"{date} 대응책을 찾을 수 없습니다")
        
        return {
            "date": date,
            "strategies": [
                {
                    "id": s.id,
                    "name": s.name,
                    "horizon": s.horizon,
                    "objective": s.objective,
                    "preconditions": s.preconditions,
                    "actions": s.actions,
                    "data_evidence": s.data_evidence,
                    "risk_note": s.risk_note,
                    "created_at": s.created_at
                }
                for s in strategies
            ]
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{date}")
async def get_report_by_date(
    date: str,  # YYYY-MM-DD
    db: Session = Depends(get_db)
):
    """특정 날짜의 일일 리포트 조회 (HTML)"""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        
        report = db.query(Report).filter(
            Report.report_type == 'daily',
            Report.start_date == target_date
        ).first()
        
        if not report:
            raise HTTPException(status_code=404, detail=f"{date} 리포트를 찾을 수 없습니다")
        
        return {
            "id": report.id,
            "date": report.start_date.strftime("%Y-%m-%d"),
            "html_content": report.html_content,
            "created_at": report.created_at
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/latest")
async def get_latest_prediction(db: Session = Depends(get_db)):
    """가장 최근 예측 결과 조회"""
    try:
        prediction = db.query(Analytics).order_by(Analytics.date.desc()).first()
        
        if not prediction:
            raise HTTPException(status_code=404, detail="예측 결과가 없습니다")
        
        return {
            "id": prediction.id,
            "date": prediction.date.strftime("%Y-%m-%d"),
            "predicted_return": float(prediction.overall_score) if prediction.overall_score else 0.0,
            "price_info": prediction.variable_scores,
            "xai_explanation": prediction.features,
            "created_at": prediction.created_at
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
