"""LLM 연결 테스트"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')
model_name = os.getenv('OPENAI_MODEL', 'gpt-4o')

print(f"API Key: {api_key[:10]}..." if api_key else "API Key: None")
print(f"Model: {model_name}")

try:
    llm = ChatOpenAI(
        model=model_name,
        temperature=0.0,
        api_key=api_key,
        model_kwargs={"response_format": {"type": "json_object"}}
    )
    
    response = llm.invoke("Return a simple JSON: {\"test\": \"success\"}")
    print(f"✅ 성공: {response.content}")
    
except Exception as e:
    print(f"❌ 실패: {e}")
