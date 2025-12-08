from fastapi import APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Any
import asyncio
from functools import lru_cache
import time

router = APIRouter(prefix="/api/financial", tags=["Financial Data"])

# 캐시 설정 
CACHE_DURATION = 60  # 1분
cache_data = {}
cache_timestamps = {}

# 지원하는 심볼 목록
SUPPORTED_SYMBOLS = {
    "BZ=F": "Brent Oil",
    "CL=F": "WTI Oil", 
    "RB=F": "Gasoline",
    "NG=F": "Natural Gas",
    "KRW=X": "USD/KRW",
    "CNYUSD=X": "CNY/USD",
    "DX-Y.NYB": "Dollar Index",
    "^TNX": "10Y Treasury",
    "^IRX": "2Y Treasury",
    "^GSPC": "S&P 500",
    "^VIX": "VIX",
    "GC=F": "Gold",
    "HG=F": "Copper"
}

def is_cache_valid(symbol: str) -> bool:
    """캐시가 유효한지 확인"""
    if symbol not in cache_timestamps:
        return False
    return time.time() - cache_timestamps[symbol] < CACHE_DURATION

def get_cached_data(symbol: str) -> Dict[str, Any]:
    """캐시된 데이터 반환"""
    if is_cache_valid(symbol):
        return cache_data[symbol]
    return None

def set_cache_data(symbol: str, data: Dict[str, Any]):
    """데이터를 캐시에 저장"""
    cache_data[symbol] = data
    cache_timestamps[symbol] = time.time()

def fetch_symbol_data(symbol: str) -> Dict[str, Any]:
    """yfinance로 심볼 데이터 가져오기"""
    try:
        # 캐시 확인
        cached = get_cached_data(symbol)
        if cached:
            return cached
        
        # yfinance로 데이터 가져오기
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="2d")
        
        if hist.empty:
            raise ValueError(f"No data available for {symbol}")
        
        # 현재가와 전일종가 계산
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100 if prev_close != 0 else 0
        
        result = {
            "symbol": symbol,
            "name": SUPPORTED_SYMBOLS.get(symbol, symbol),
            "price": round(float(current_price), 4),
            "prevClose": round(float(prev_close), 4),
            "change": round(float(change), 4),
            "changePercent": round(float(change_percent), 2),
            "timestamp": datetime.now().isoformat(),
            "cached": False
        }
        
        # 캐시에 저장
        set_cache_data(symbol, result)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data for {symbol}: {str(e)}")

@router.get("/all")
async def get_all_symbols_data():
    """모든 심볼 데이터 일괄 조회"""
    results = {}
    errors = {}
    
    for symbol in SUPPORTED_SYMBOLS.keys():
        try:
            data = fetch_symbol_data(symbol)
            data["cached"] = is_cache_valid(symbol)
            results[symbol] = data
        except Exception as e:
            errors[symbol] = str(e)
    
    response = {
        "data": results,
        "timestamp": datetime.now().isoformat(),
        "total_symbols": len(SUPPORTED_SYMBOLS),
        "successful": len(results),
        "failed": len(errors)
    }
    
    if errors:
        response["errors"] = errors
    
    return response

@router.get("/{symbol}")
async def get_symbol_data(symbol: str):
    """개별 심볼 데이터 조회"""
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {symbol}")
    
    try:
        data = fetch_symbol_data(symbol)
        data["cached"] = is_cache_valid(symbol)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))