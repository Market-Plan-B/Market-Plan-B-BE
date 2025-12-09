import os
import requests
import zipfile
from io import BytesIO

import numpy as np
import pandas as pd
import yfinance as yf


API_KEY = os.getenv("EIA_API_KEY")

# ------------------------------
# 0. 브렌트/WTI 시계열 (가격 + 파생 피처)
# ------------------------------

def make_brent_wti_features(start: str = "2013-09-01",
                            end: str | None = None,
                            target_horizon: int = 1) -> pd.DataFrame:
    """
    Brent(BZ=F) / WTI(CL=F) 가격 기반 피처 생성.
    - target_horizon에 따라 누출되는 return feature 제거 로직 포함.
    """
    brent = yf.download("BZ=F", start=start, end=end, auto_adjust=False, progress=False)
    wti = yf.download("CL=F", start=start, end=end, auto_adjust=False, progress=False)

    brent = brent.rename(columns=str.lower)
    wti = wti.rename(columns=str.lower)

    df = pd.DataFrame(index=brent.index)
    df["brent_close"] = brent["close"]
    df["wti_close"] = wti["close"].reindex(df.index)

    # Spread
    df["brent_wti_spread"] = df["brent_close"] - df["wti_close"]

    # Returns (미래 정보 포함 가능성 있으므로 horizon에 따라 필터링)
    df["brent_ret_5d"] = df["brent_close"].pct_change(5)

    # Moving averages
    df["brent_ma_5"] = df["brent_close"].rolling(5).mean()
    df["brent_ma_20"] = df["brent_close"].rolling(20).mean()
    df["brent_ma_60"] = df["brent_close"].rolling(60).mean()

    df["wti_ma_5"] = df["wti_close"].rolling(5).mean()
    df["wti_ma_20"] = df["wti_close"].rolling(20).mean()
    df["wti_ma_60"] = df["wti_close"].rolling(60).mean()

    # Volatility proxies
    df["brent_vol_5d"] = df["brent_close"].pct_change().rolling(5).std()
    df["wti_vol_5d"] = df["wti_close"].pct_change().rolling(5).std()

    df["high_low_range"] = (brent["high"] - brent["low"]) / brent["close"]

    if target_horizon == 1:
        # 1D 예측은 크게 신경 쓸 것 없음
        pass

    elif target_horizon == 5:
        # 5D 예측 → 5D/20D return feature 중 타깃(brent_ret_5d) 외 모두 제거
        drop_cols = [
            c
            for c in df.columns
            if (("ret_5d" in c or "ret_20d" in c) and c != "brent_ret_5d")
        ]
        df = df.drop(columns=drop_cols)

    elif target_horizon == 20:
        drop_cols = [
            c
            for c in df.columns
            if ("ret_5d" in c or "ret_20d" in c) and c != "brent_ret_20d"
        ]
        if drop_cols:
            df = df.drop(columns=drop_cols)

    return df.dropna()


def build_market_df(end_date: str,
                    target_horizon: int = 5,
                    lookback_days: int = 180) -> pd.DataFrame:
    """
    리포트용 Brent/WTI 시계열
    - end_date 기준 lookback_days만큼만 yfinance에서 가져와서 feature 생성
    """
    end_dt = pd.to_datetime(end_date)
    start_dt = end_dt - pd.Timedelta(days=lookback_days)

    # yfinance end는 exclusive라 하루 더해줌
    end_for_yf = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    df = make_brent_wti_features(
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_for_yf,
        target_horizon=target_horizon,
    )

    df = df.copy()
    df.index.name = "date"

    # 인덱스를 컬럼으로 꺼내기
    df = df.reset_index()

    # date 컬럼을 명시적으로 datetime으로 변환
    df["date"] = pd.to_datetime(df["date"])

    return df



# ------------------------------
# 1. EIA: 재고 / 생산 / 수입·수출 / 정제 가동률
# ------------------------------

def fetch_crude_stock() -> pd.DataFrame:
    """
    상업 원유 재고 (PET.WCESTUS1.W)
    """
    url = "https://api.eia.gov/v2/seriesid/PET.WCESTUS1.W"
    params = {"api_key": API_KEY}
    r = requests.get(url, params=params)
    r.raise_for_status()
    js = r.json()

    df = pd.DataFrame(js["response"]["data"])
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.sort_values("period")

    df = df.rename(columns={"value": "crude_stock_level"})
    return df[["period", "crude_stock_level"]]


BASE_STOCK = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"


def fetch_raw_stock(product_code: str) -> pd.DataFrame:
    """
    wstk 원본 fetch (향후 세부 재고 시리즈 뽑을 때 사용 가능)
    """
    params = {
        "api_key": API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[product][]": product_code,
        "start": "2009-01-01",
        "end": "2025-10-31",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }
    r = requests.get(BASE_STOCK, params=params)
    r.raise_for_status()
    data = r.json()["response"]["data"]
    df = pd.DataFrame(data)
    df["period"] = pd.to_datetime(df["period"])
    df = df.sort_values("period").reset_index(drop=True)
    return df


def fetch_gas_stock_total() -> pd.DataFrame:
    """
    휘발유 재고 (PET.WGTSTUS1.W)
    """
    url = "https://api.eia.gov/v2/seriesid/PET.WGTSTUS1.W"
    params = {"api_key": API_KEY}
    r = requests.get(url, params=params)
    r.raise_for_status()
    js = r.json()

    df = pd.DataFrame(js["response"]["data"])
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.sort_values("period")

    df = df.rename(columns={"value": "gas_stock_level"})
    return df[["period", "gas_stock_level"]]


def fetch_dist_stock_total() -> pd.DataFrame:
    """
    디젤(증류유) 재고
    - 지금은 휘발유와 같은 seriesid 사용 중 (실제 운용 시 distillate용 코드로 교체 가능)
    """
    url = "https://api.eia.gov/v2/seriesid/PET.WGTSTUS1.W"
    params = {"api_key": API_KEY}
    r = requests.get(url, params=params)
    r.raise_for_status()
    js = r.json()

    df = pd.DataFrame(js["response"]["data"])
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.sort_values("period")

    df = df.rename(columns={"value": "dist_stock_level"})
    return df[["period", "dist_stock_level"]]


def fetch_prod_features() -> pd.DataFrame:
    """
    WCRFPUS2: U.S. Crude Oil Field Production (weekly)
    - prod_weekly, prod_4w_ma, prod_wow_change 생성
    """
    url = "https://api.eia.gov/v2/petroleum/sum/sndw/data/"
    params = {
        "api_key": API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": "WCRFPUS2",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()["response"]["data"]
    df = pd.DataFrame(data)

    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.sort_values("period")

    df["prod_weekly"] = df["value"]
    df["prod_4w_ma"] = df["prod_weekly"].rolling(window=4).mean()
    df["prod_wow_change"] = df["prod_weekly"].pct_change()

    df = df[df["period"] >= "2014-01-01"].reset_index(drop=True)
    feat = df[["period", "prod_weekly", "prod_4w_ma", "prod_wow_change"]]
    return feat


def fetch_import_export_features() -> pd.DataFrame:
    """
    WCRIMUS2: Crude Oil Imports
    WCREXUS2: Crude Oil Exports
    - import_4w_ma, net_imports 생성
    """
    url = "https://api.eia.gov/v2/petroleum/move/wkly/data/"

    params = {
        "api_key": API_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": ["WCRIMUS2", "WCREXUS2"],
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()["response"]["data"]
    df = pd.DataFrame(data)

    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    df = df.sort_values("period")

    wide = df.pivot(index="period", columns="series", values="value").sort_index()

    wide = wide.rename(columns={
        "WCRIMUS2": "crude_imports",
        "WCREXUS2": "crude_exports",
    })

    wide["import_4w_ma"] = wide["crude_imports"].rolling(4).mean()
    wide["net_imports"] = wide["crude_imports"] - wide["crude_exports"]

    wide = wide[wide.index >= "2014-01-01"]
    wide.columns.name = None
    wide = wide.reset_index()  # period 컬럼

    return wide


def fetch_refinery_run_rate() -> pd.DataFrame:
    """
    정제 가동률 (PET.WPULEUS3.W)
    """
    url = "https://api.eia.gov/v2/seriesid/PET.WPULEUS3.W"
    params = {"api_key": API_KEY}

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    js = resp.json()

    data = js["response"]["data"]
    df = pd.DataFrame(data)
    df["period"] = pd.to_datetime(df["period"])
    df["refinery_run_rate"] = pd.to_numeric(df["value"])
    df = df.sort_values("period").reset_index(drop=True)

    ref_feat = df[["period", "refinery_run_rate"]].reset_index(drop=True)
    return ref_feat


def build_eia_objects_for_report(end_date: str, lookback_days: int = 365) -> dict:
    """
    end_date 기준으로 lookback_days만큼만 잘라서 리포트에 넘길 EIA 객체 생성.
    - 원 데이터는 API에서 전체를 받아오되,
      리포트에서 실제로 쓰는 구간은 여기서 잘라줌.
    """
    end = pd.to_datetime(end_date)
    start = end - pd.Timedelta(days=lookback_days)

    crude = fetch_crude_stock()
    gas = fetch_gas_stock_total()
    dist = fetch_dist_stock_total()
    prod = fetch_prod_features()
    imports_exports = fetch_import_export_features()
    refinery = fetch_refinery_run_rate()

    def _clip(df: pd.DataFrame, date_col: str = "period") -> pd.DataFrame:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        return df[(df[date_col] >= start) & (df[date_col] <= end)].reset_index(drop=True)

    return {
        "crude_stock": _clip(crude, "period"),
        "gas_stock": _clip(gas, "period"),
        "dist_stock": _clip(dist, "period"),
        "prod": _clip(prod, "period"),
        "imports_exports": _clip(imports_exports, "period"),
        "refinery": _clip(refinery, "period"),
    }


def build_eia_weekly(end_date: str, eia_objs: dict) -> dict:
    """
    주간 리포트용 EIA 요약 (각 시리즈에서 end_date 기준 최신 주간 한 줄만 사용)
    """

    end = pd.to_datetime(end_date)

    def _latest(df: pd.DataFrame, col: str = "period"):
        if df is None or df.empty:
            return None
        df = df.copy()
        df[col] = pd.to_datetime(df[col])
        df = df[df[col] <= end]
        if df.empty:
            return None
        return df.sort_values(col).iloc[-1]

    crude = _latest(eia_objs.get("crude_stock"), "period")
    gas = _latest(eia_objs.get("gas_stock"), "period")
    dist = _latest(eia_objs.get("dist_stock"), "period")
    prod = _latest(eia_objs.get("prod"), "period")
    imp_exp = _latest(eia_objs.get("imports_exports"), "period")
    ref = _latest(eia_objs.get("refinery"), "period")

    def _as_date(x):
        if x is None:
            return None
        val = x["period"]
        return str(pd.to_datetime(val).date())

    out = {
        "crude_stock": None if crude is None else {
            "period": _as_date(crude),
            "crude_stock_level": float(crude["crude_stock_level"]),
        },
        "gas_stock": None if gas is None else {
            "period": _as_date(gas),
            "gas_stock_level": float(gas["gas_stock_level"]),
        },
        "dist_stock": None if dist is None else {
            "period": _as_date(dist),
            "dist_stock_level": float(dist["dist_stock_level"]),
        },
        "prod": None if prod is None else {
            "period": _as_date(prod),
            "prod_weekly": float(prod["prod_weekly"]),
            "prod_4w_ma": float(prod["prod_4w_ma"])
            if not pd.isna(prod["prod_4w_ma"]) else None,
            "prod_wow_change": float(prod["prod_wow_change"])
            if not pd.isna(prod["prod_wow_change"]) else None,
        },
        "imports_exports": None if imp_exp is None else {
            "period": _as_date(imp_exp),
            "crude_imports": float(imp_exp["crude_imports"]),
            "crude_exports": float(imp_exp["crude_exports"]),
            "import_4w_ma": float(imp_exp["import_4w_ma"])
            if not pd.isna(imp_exp["import_4w_ma"]) else None,
            "net_imports": float(imp_exp["net_imports"])
            if not pd.isna(imp_exp["net_imports"]) else None,
        },
        "refinery": None if ref is None else {
            "period": _as_date(ref),
            "refinery_run_rate": float(ref["refinery_run_rate"]),
        },
    }

    return out


# ------------------------------
# 2. COT (CFTC) WTI 포지션
# ------------------------------

def load_cot_raw_for_report(
    end_date: str,
    years_back: int = 3,
    start_year: int | None = 2025,
) -> pd.DataFrame:
    """
    end_date 기준 최근 years_back년만 다운로드.
    - start_year를 직접 줄 수도 있음 (기본 2025, 최소 2013년).
    """
    end = pd.to_datetime(end_date)
    end_year = end.year

    # start_year를 안 주면(end_year, years_back 기반으로 계산)
    if start_year is None:
        start_year = end_year - years_back + 1

    # 최소 2013년 이후로 보정
    if start_year < 2013:
        start_year = 2013

    # end_year보다 클 수 없도록 보정
    if start_year > end_year:
        start_year = end_year

    base_url = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{}.zip"
    all_df: list[pd.DataFrame] = []

    for y in range(start_year, end_year + 1):
        url = base_url.format(y)
        try:
            print(f"📦 {y}년 COT 다운로드 중...")
            res = requests.get(url)
            res.raise_for_status()
            with zipfile.ZipFile(BytesIO(res.content)) as z:
                for name in z.namelist():
                    if name.endswith(".txt"):
                        df = pd.read_csv(z.open(name), header=None)
                        df["year"] = y
                        all_df.append(df)
            print(f"✅ {y} 완료 (누적 파일 수: {len(all_df)})")
        except Exception as e:
            print(f"❌ {y} 실패: {e}")

    if not all_df:
        raise RuntimeError("COT 데이터를 하나도 가져오지 못했습니다.")

    df_all = pd.concat(all_df, ignore_index=True)
    print("COT 전체 합계 row 수:", len(df_all))
    return df_all


def extract_cot_features(df_all: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    CFTC Disaggregated Futures Only 데이터에서
    WTI 주간 / 일간 포지션 피처 추출.
    """

    # 1️⃣ 헤더 정리
    if df_all.iloc[0, 0] == "Market_and_Exchange_Names":
        df_all.columns = df_all.iloc[0]
        df_all = df_all.drop(index=0).reset_index(drop=True)

    # 2️⃣ 컬럼명 정리
    df_all.columns = [str(c).strip() for c in df_all.columns]
    df_all = df_all.rename(columns=lambda x: x.replace("-", "_").replace(" ", "_"))

    # 날짜 컬럼 탐색
    date_col = next((c for c in df_all.columns if "report_date" in c.lower()), None)
    if not date_col:
        raise KeyError("날짜 컬럼을 찾을 수 없습니다. ('Report_Date_as_' 로 시작해야 함)")

    df_all["date"] = pd.to_datetime(df_all[date_col], errors="coerce")

    # 주요 컬럼 정의
    mm_long = "M_Money_Positions_Long_All"
    mm_short = "M_Money_Positions_Short_All"
    prod_short = "Prod_Merc_Positions_Short_All"
    oi_col = "Open_Interest_All"

    for col in [mm_long, mm_short, prod_short, oi_col]:
        df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

    # 3️⃣ 시장명 소문자로 정리
    df_all["Market_and_Exchange_Names"] = (
        df_all["Market_and_Exchange_Names"].astype(str).str.lower()
    )

    # 4️⃣ 상품 필터링 (WTI만 사용)
    wti = df_all[
        df_all["Market_and_Exchange_Names"].str.contains("crude oil, light sweet", na=False)
    ].copy()

    def make_features(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        df = (
            df.sort_values("date")
            .groupby("date", as_index=False)
            .last()
            .copy()
        )
        df[f"{prefix}_mm_net_long"] = df[mm_long] - df[mm_short]
        df[f"{prefix}_mm_net_long_ratio"] = df[f"{prefix}_mm_net_long"] / df[oi_col]
        df[f"{prefix}_producer_hedge_ratio"] = df[prod_short] / df[oi_col]
        df[f"{prefix}_mm_position_change_wow"] = df[f"{prefix}_mm_net_long"].diff()
        df[f"{prefix}_sentiment_position"] = np.sign(df[f"{prefix}_mm_net_long"])

        # NaN이어도 컬럼 유지
        for col in [
            f"{prefix}_mm_net_long",
            f"{prefix}_mm_net_long_ratio",
            f"{prefix}_producer_hedge_ratio",
            f"{prefix}_mm_position_change_wow",
            f"{prefix}_sentiment_position",
        ]:
            if col not in df.columns:
                df[col] = np.nan

        return df.set_index("date")[
            [
                f"{prefix}_mm_net_long",
                f"{prefix}_mm_net_long_ratio",
                f"{prefix}_producer_hedge_ratio",
                f"{prefix}_mm_position_change_wow",
                f"{prefix}_sentiment_position",
            ]
        ]

    # 5️⃣ 피처 계산 (WTI만)
    wti_feat = make_features(wti, "wti")

    # 6️⃣ 주간 데이터
    cot_weekly = wti_feat.copy()

    # 7️⃣ 일간 데이터 (D 리샘플)
    cot_daily = cot_weekly.resample("D").ffill().copy()

    return cot_weekly, cot_daily


def build_cot_features_for_report(end_date: str,
                                  years_back: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    end_date 기준 최근 years_back년 COT 데이터를 가져와
    WTI 주간/일간 포지션 피처 생성.
    """
    df_all = load_cot_raw_for_report(end_date, years_back=years_back)
    cot_weekly, cot_daily = extract_cot_features(df_all)

    end = pd.to_datetime(end_date)
    cot_weekly = cot_weekly[cot_weekly.index <= end]
    cot_daily = cot_daily[cot_daily.index <= end]
    return cot_weekly, cot_daily


def build_cot_weekly(end_date: str, cot_weekly: pd.DataFrame) -> dict | None:
    """
    end_date 기준 바로 직전(포함) WTI COT 한 줄 요약.
    """
    if cot_weekly is None or cot_weekly.empty:
        return None

    end = pd.to_datetime(end_date)
    df = cot_weekly.copy()
    df.index = pd.to_datetime(df.index)
    df = df[df.index <= end]
    if df.empty:
        return None

    last = df.sort_index().iloc[-1]
    idx_date = df.sort_index().index[-1]

    return {
        "date": str(idx_date.date()),
        "wti_mm_net_long": float(last.get("wti_mm_net_long", np.nan)),
        "wti_mm_net_long_ratio": float(last.get("wti_mm_net_long_ratio", np.nan)),
        "wti_producer_hedge_ratio": float(last.get("wti_producer_hedge_ratio", np.nan)),
        "wti_mm_position_change_wow": float(last.get("wti_mm_position_change_wow", np.nan)),
        "wti_sentiment_position": float(last.get("wti_sentiment_position", np.nan)),
    }


# ------------------------------
# 3. 리포트용 통합 소스 빌더
# ------------------------------

def build_report_sources(
    end_date: str,
    target_horizon: int = 5,
    price_lookback_days: int = 180,
    eia_lookback_days: int = 365,
    cot_years_back: int = 3,
) -> dict:
    """
    Daily/Weekly report에서 공통으로 쓰는 소스들을
    '리포트용 짧은 윈도우' 기준으로 생성.
    """
    # 1) 가격/변동성 피처 – 최근 6개월
    full_df = build_market_df(
        end_date=end_date,
        target_horizon=target_horizon,
        lookback_days=price_lookback_days,
    )

    # 2) EIA fundamentals – 최근 1년
    eia_objs = build_eia_objects_for_report(
        end_date=end_date,
        lookback_days=eia_lookback_days,
    )

    # 3) COT 포지션 – 최근 2~3년
    cot_weekly, cot_daily = build_cot_features_for_report(
        end_date=end_date,
        years_back=cot_years_back,
    )

    return {
        "full_df": full_df,
        "eia_objs": eia_objs,
        "cot_weekly": cot_weekly,
        "cot_daily": cot_daily,
    }
