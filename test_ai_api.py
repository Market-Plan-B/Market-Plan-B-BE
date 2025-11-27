"""AI API 테스트 스크립트"""
import requests

# 테스트 실행
try:
    response = requests.post(
        "http://127.0.0.1:8000/ai/run-prediction",
        params={"date": "2025-11-19", "use_file": True}
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
