# app/ai/tools/graph_tool.py

from typing import Dict, Any
import json


def run_graph_tool(instruction: str) -> Dict[str, Any]:
    """
    프론트엔드용 Chart.js 그래프 스펙 JSON을 생성하는 툴
    
    Args:
        instruction: 그래프 생성 지시사항 (예: "브렌트 유가 라인 차트")
    
    Returns:
        Chart.js 형태의 그래프 스펙 JSON
    """
    print(f"[GRAPH_TOOL_LOG] 그래프 생성 요청: {instruction}")
    
    # 간단한 샘플 데이터 생성 (실제로는 LLM이나 더 복잡한 로직 사용)
    if "브렌트" in instruction and ("라인" in instruction or "차트" in instruction):
        result = {
            "chartType": "line",
            "title": "브렌트 유가 추이",
            "labels": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "datasets": [
                {
                    "label": "브렌트 유가",
                    "data": [75.2, 76.1, 74.8, 75.5, 76.3],
                    "borderColor": "#FF6384",
                    "backgroundColor": "rgba(255, 99, 132, 0.2)",
                    "borderWidth": 2,
                    "fill": False
                }
            ],
            "yAxisLabel": "가격 (USD/배럴)"
        }
    elif "스프레드" in instruction:
        result = {
            "chartType": "line", 
            "title": "브렌트-WTI 스프레드",
            "labels": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "datasets": [
                {
                    "label": "브렌트-WTI 스프레드",
                    "data": [3.2, 3.5, 2.8, 3.1, 3.4],
                    "borderColor": "#36A2EB",
                    "backgroundColor": "rgba(54, 162, 235, 0.2)",
                    "borderWidth": 2,
                    "fill": False
                }
            ],
            "yAxisLabel": "스프레드 (USD)"
        }
    elif "재고" in instruction:
        result = {
            "chartType": "bar",
            "title": "원유 재고량",
            "labels": ["1주차", "2주차", "3주차", "4주차"],
            "datasets": [
                {
                    "label": "원유 재고",
                    "data": [427.5, 425.2, 430.1, 428.7],
                    "backgroundColor": "#FFCE56",
                    "borderColor": "#FF9F40",
                    "borderWidth": 1
                }
            ],
            "yAxisLabel": "재고량 (백만 배럴)"
        }
    else:
        # 기본 차트
        result = {
            "chartType": "line",
            "title": "데이터 차트",
            "labels": ["A", "B", "C", "D"],
            "datasets": [
                {
                    "label": "데이터",
                    "data": [10, 20, 15, 25],
                    "borderColor": "#4BC0C0",
                    "backgroundColor": "rgba(75, 192, 192, 0.2)",
                    "borderWidth": 2,
                    "fill": False
                }
            ],
            "yAxisLabel": "값"
        }
    
    print(f"[GRAPH_TOOL_LOG] 생성된 차트 타입: {result['chartType']}")
    print(f"[GRAPH_TOOL_LOG] 데이터셋 수: {len(result['datasets'])}")
    
    return result