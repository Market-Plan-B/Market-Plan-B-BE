from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import yfinance as yf  # ✅ 새로 추가

# 부장님이 작성하신 data_pipeline 모듈 사용
from app.ai.services.data_pipeline import (
    build_report_sources,
    build_eia_weekly,
    build_cot_weekly,
)


def _period_to_lookback_days(period: str) -> int:
    """
    yfinance 스타일 period 문자열을 lookback 일수로 단순 매핑.
    - planner에서 들어오는 값: "1mo", "3mo", "6mo", "1y" 정도 가정
    """
    mapping = {
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
    }
    return mapping.get(period, 180)


# ✅ 스냅샷 전용: 단순 브렌트/WTI 가격만 yfinance에서 직접 가져오는 함수
def fetch_price_timeseries_for_snapshot(
    end_date: str,
    lookback_days: int,
    date_filter_start: pd.Timestamp | None = None,
    date_filter_end: pd.Timestamp | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """
    예측용 DP를 건드리지 않고,
    스냅샷용으로만 브렌트/WTI 종가 시계열을 단순 조회하는 함수.
    - 파생 피처 없음
    - dropna()로 다 날리지 않도록 최소한의 처리만 수행
    """
    end_dt = pd.to_datetime(end_date)
    start_dt = end_dt - pd.Timedelta(days=lookback_days)

    start_for_yf = start_dt.strftime("%Y-%m-%d")
    end_for_yf = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # yfinance end exclusive

    # 브렌트 / WTI 다운로드
    brent = yf.download("BZ=F", start=start_for_yf, end=end_for_yf,
                        auto_adjust=False, progress=False)
    wti = yf.download("CL=F", start=start_for_yf, end=end_for_yf,
                      auto_adjust=False, progress=False)

    if brent.empty:
        return [], None

    brent = brent.rename(columns=str.lower)
    wti = wti.rename(columns=str.lower)

    df = pd.DataFrame(index=brent.index)
    df["brent_close"] = brent["close"]
    df["wti_close"] = wti["close"].reindex(df.index)
    df["brent_wti_spread"] = df["brent_close"] - df["wti_close"]

    df.index.name = "date"
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"])

    # 필요하면 start/end로 한 번 더 필터링
    if date_filter_start is not None and date_filter_end is not None:
        df = df[
            (df["date"] >= date_filter_start) &
            (df["date"] <= date_filter_end)
        ]

    # 브렌트 가격이 없는 날은 제외
    df = df[pd.notna(df["brent_close"])]

    if df.empty:
        return [], None

    price_timeseries: list[dict[str, Any]] = []
    for _, row in df.sort_values("date").iterrows():
        price_timeseries.append(
            {
                "date": row["date"].date().isoformat(),
                "brent_close": float(row["brent_close"])
                if pd.notna(row["brent_close"]) else None,
                "wti_close": float(row["wti_close"])
                if pd.notna(row["wti_close"]) else None,
                "brent_wti_spread": float(row["brent_wti_spread"])
                if pd.notna(row["brent_wti_spread"]) else None,
            }
        )

    latest_row = df.sort_values("date").iloc[-1]
    price_latest = {
        "date": latest_row["date"].date().isoformat(),
        "brent_close": float(latest_row["brent_close"])
        if pd.notna(latest_row["brent_close"]) else None,
        "wti_close": float(latest_row["wti_close"])
        if pd.notna(latest_row["wti_close"]) else None,
        "brent_wti_spread": float(latest_row["brent_wti_spread"])
        if pd.notna(latest_row["brent_wti_spread"]) else None,
    }

    return price_timeseries, price_latest


# -----------------------------
# 기존 run_indicator_snapshot 수정
# -----------------------------
def run_indicator_snapshot(
    tickers: List[str] | None = None,
    period: str = "1mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> Dict[str, Any]:
    """
    - tickers: 기본 브렌트 티커 리스트
    - period: start/end가 없을 때 사용하는 상대 기간 (예: "1mo")
    - interval: yfinance interval (현재 내부에선 크게 쓰지 않지만 입력으로 받음)
    - start, end: "YYYY-MM-DD" 형식의 절대 날짜 구간
        - 둘 다 주어지면 해당 구간 기준으로 price_timeseries를 필터링한다.
        - 둘 다 없으면 period 기준으로 최근 구간을 조회한다.
    """
    if tickers is None:
        tickers = ["BZ=F"]

    # -------------------------
    # 0) end_date / lookback_days 결정
    # -------------------------
    if start is not None and end is not None:
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)

        # 잘못 들어온 경우 방어: 뒤집기
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        end_date = end_dt.strftime("%Y-%m-%d")
        lookback_days = max((end_dt - start_dt).days + 1, 1)
        date_filter_start = start_dt
        date_filter_end = end_dt
    else:
        today = pd.Timestamp.today().normalize()
        end_date = today.strftime("%Y-%m-%d")
        lookback_days = _period_to_lookback_days(period)
        date_filter_start = None
        date_filter_end = None

    # -------------------------
    # 1) 통합 소스 생성 (EIA + COT 중심)
    #    full_df는 이제 가격에 사용하지 않음
    # -------------------------
    sources = build_report_sources(
        end_date=end_date,
        target_horizon=5,
        price_lookback_days=lookback_days,  # 예전 그대로 두되, 가격은 별도 함수에서 조회
        eia_lookback_days=365,
        cot_years_back=3,
    )

    eia_objs: dict = sources["eia_objs"]
    cot_weekly: pd.DataFrame | None = sources.get("cot_weekly")

    # -------------------------
    # 2) 가격 시계열: 새로 만든 함수 사용
    # -------------------------
    price_timeseries, price_latest = fetch_price_timeseries_for_snapshot(
        end_date=end_date,
        lookback_days=lookback_days,
        date_filter_start=date_filter_start,
        date_filter_end=date_filter_end,
    )

    # -------------------------
    # 3) EIA / COT 요약 (가격 없어도 계산)
    # -------------------------
    eia_weekly = build_eia_weekly(end_date=end_date, eia_objs=eia_objs)
    cot_weekly_summary = (
        build_cot_weekly(end_date=end_date, cot_weekly=cot_weekly)
        if cot_weekly is not None and not cot_weekly.empty
        else None
    )

    # -------------------------
    # 4) 최종 반환 JSON
    # -------------------------
    result: Dict[str, Any] = {
        "as_of_date": end_date,
        "input_params": {
            "tickers": tickers,
            "period": period,
            "interval": interval,
            "lookback_days": lookback_days,
            "start": start,
            "end": end,
        },
        "price_timeseries": price_timeseries,
        "price_latest": price_latest,
        "eia_weekly": eia_weekly,
        "cot_weekly": cot_weekly_summary,
    }

    if not price_timeseries:
        result["warning"] = "가격 시계열이 비어 있습니다. (start/end 또는 period 구간을 확인하세요.)"

    return result
