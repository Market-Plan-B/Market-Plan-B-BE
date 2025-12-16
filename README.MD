# Market Plan B - Backend 개발환경 설정 가이드

## 📋 목차
- [프로젝트 소개](#프로젝트-소개)
- [시스템 요구사항](#시스템-요구사항)
- [개발환경 설정](#개발환경-설정)
- [실행 방법](#실행-방법)
- [프로젝트 구조](#프로젝트-구조)
- [API 문서](#api-문서)
- [트러블슈팅](#트러블슈팅)

---

## 🎯 프로젝트 소개

Market Plan B는 금융 뉴스 크롤링, AI 분석, 투자 전략 추천을 제공하는 백엔드 시스템입니다.

**주요 기능:**
- 금융 뉴스 자동 크롤링 (Google, Yahoo, Investing.com 등)
- AI 기반 뉴스 분석 및 감정 점수 산출
- ChromaDB 벡터 데이터베이스를 활용한 뉴스 임베딩 저장
- LangGraph 기반 AI 에이전트 챗봇
- 일일/주간 리포트 자동 생성
- 투자 전략 추천 시스템

---

## 💻 시스템 요구사항

### 필수 소프트웨어
- **Python**: 3.11 이상
- **Docker Desktop**: 최신 버전
- **Git**: 최신 버전

### 권장 사양
- RAM: 8GB 이상
- 디스크 여유 공간: 10GB 이상

---

## 🚀 개발환경 설정

### 1. 프로젝트 클론

```bash
git clone <repository-url>
cd Market-Plan-B-BE
```

### 2. 환경변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 입력합니다:

```env
# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here
MODEL=gpt-3.5-turbo

# LangChain
LANGCHAIN_API_KEY=your_langchain_api_key_here
LANGCHAIN_PROJECT=your_project_name

# Tavily Search API
TAVILY_API_KEY=your_tavily_api_key_here

# Stability AI (이미지 생성)
STABILITY_API_KEY=your_stability_api_key_here

# Google Gemini
GEMINI_API_KEY=your_gemini_api_key_here

# EIA (에너지 정보)
EIA_API_KEY=your_eia_api_key_here

# PostgreSQL 데이터베이스
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=market-plan-b

# ChromaDB 벡터 데이터베이스
CHROMA_HOST=your_chroma_host_here
CHROMA_AUTH_TOKEN=your_chroma_auth_token_here

# 디버그 모드
DEBUG=True
```

> ⚠️ **주의**: `.env` 파일은 절대 Git에 커밋하지 마세요!

### 3. 자동 설정 스크립트 실행

#### Windows 사용자

```cmd
setup.bat
```

#### Linux/Mac 사용자

```bash
chmod +x setup.sh
./setup.sh
```

**자동 설정 스크립트가 수행하는 작업:**
1. PostgreSQL Docker 컨테이너 실행 (포트 5433)
2. Python 가상환경 생성
3. 필요한 패키지 설치
4. 데이터베이스 테이블 초기화

### 4. 수동 설정 (선택사항)

자동 스크립트가 실패할 경우 수동으로 설정할 수 있습니다:

#### 4-1. PostgreSQL 실행

```bash
docker run -d \
    --name market-plan-b \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=market-plan-b \
    -p 5433:5432 \
    ankane/pgvector:latest
```

#### 4-2. Python 가상환경 생성

**Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 4-3. 패키지 설치

```bash
pip install --upgrade pip
pip install -r app/requirements.txt
```

#### 4-4. Playwright 브라우저 설치

```bash
playwright install chromium
```

#### 4-5. 데이터베이스 초기화

```bash
python app/db/db_setting.py
```

---

## ▶️ 실행 방법

### 개발 모드 실행

가상환경을 활성화한 상태에서:

```bash
cd app
python main.py
```

또는 uvicorn 직접 실행:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

서버가 정상적으로 실행되면 다음 주소에서 접근 가능합니다:
- API 서버: http://localhost:8000
- Swagger 문서: http://localhost:8000/docs
- ReDoc 문서: http://localhost:8000/redoc

### Docker Compose 실행

전체 시스템을 Docker로 실행하려면:

```bash
docker-compose up -d
```

중지:
```bash
docker-compose down
```

로그 확인:
```bash
docker-compose logs -f backend
```

### 백그라운드 스케줄러 실행

뉴스 크롤링 및 리포트 생성을 자동화하려면:

**Windows:**
```cmd
cd app\tasks
run_background.bat
```

**Linux/Mac:**
```bash
cd app/tasks
chmod +x run_background.sh
./run_background.sh
```

---

## 📁 프로젝트 구조

```
Market-Plan-B-BE/
├── app/
│   ├── ai/                    # AI 에이전트 (LangGraph)
│   │   ├── nodes/            # 에이전트 노드
│   │   ├── tools/            # 에이전트 도구
│   │   ├── graph.py          # 에이전트 그래프 정의
│   │   └── state.py          # 에이전트 상태 관리
│   ├── crawlers/             # 뉴스 크롤러
│   │   ├── google_crawling.py
│   │   ├── yahoo_crawling.py
│   │   └── investing_crawling.py
│   ├── db/                   # 데이터베이스 설정
│   │   ├── database.py       # DB 연결
│   │   └── db_setting.py     # 테이블 정의
│   ├── models/               # SQLAlchemy 모델
│   ├── routers/              # FastAPI 라우터
│   │   ├── chat_router.py    # 챗봇 API
│   │   ├── dashboard_router.py
│   │   ├── report_router.py
│   │   └── analytics_router.py
│   ├── schemas/              # Pydantic 스키마
│   ├── services/             # 비즈니스 로직
│   │   ├── chroma_service.py # ChromaDB 서비스
│   │   ├── chat_service.py   # 챗봇 서비스
│   │   └── ai_service.py     # AI 분석 서비스
│   ├── tasks/                # 백그라운드 작업
│   │   └── full_scheduler.py # 스케줄러
│   ├── main.py               # FastAPI 앱 진입점
│   └── requirements.txt      # Python 패키지 목록
├── data/                     # 데이터 파일
├── tests/                    # 테스트 코드
├── .env                      # 환경변수 (생성 필요)
├── docker-compose.yml        # Docker Compose 설정
├── Dockerfile                # Docker 이미지 빌드
├── setup.bat                 # Windows 자동 설정
├── setup.sh                  # Linux/Mac 자동 설정
└── README.md                 # 이 문서
```

---

## 📚 API 문서

서버 실행 후 다음 주소에서 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 주요 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/reports/daily` | GET | 일일 리포트 조회 |
| `/api/dashboard/summary` | GET | 대시보드 요약 |
| `/api/analytics/predict` | POST | AI 예측 실행 |
| `/api/chat/sessions` | POST | 챗봇 세션 생성 |
| `/api/chat/message` | POST | 챗봇 메시지 전송 |
| `/api/chroma/stats` | GET | ChromaDB 통계 |

---

## 🔧 트러블슈팅

### 1. Docker 컨테이너가 시작되지 않음

**증상**: `docker run` 명령 실행 시 오류 발생

**해결방법**:
- Docker Desktop이 실행 중인지 확인
- 포트 5433이 이미 사용 중인지 확인: `netstat -ano | findstr :5433` (Windows)
- 기존 컨테이너 삭제: `docker rm -f market-plan-b`

### 2. 패키지 설치 실패

**증상**: `pip install` 중 오류 발생

**해결방법**:
```bash
pip install --upgrade pip setuptools wheel
pip install -r app/requirements.txt --no-cache-dir
```

### 3. Playwright 브라우저 오류

**증상**: 크롤링 시 브라우저 실행 실패

**해결방법**:
```bash
playwright install chromium
playwright install-deps
```

### 4. 데이터베이스 연결 실패

**증상**: `connection refused` 또는 `could not connect to server`

**해결방법**:
- PostgreSQL 컨테이너 상태 확인: `docker ps`
- 컨테이너 재시작: `docker restart market-plan-b`
- `.env` 파일의 DB 설정 확인

### 5. ChromaDB 연결 오류

**증상**: ChromaDB 서버 연결 실패

**해결방법**:
- `.env` 파일의 `CHROMA_HOST`와 `CHROMA_AUTH_TOKEN` 확인
- 로컬 모드로 전환: `CHROMA_HOST` 환경변수 제거

### 6. API 키 오류

**증상**: `401 Unauthorized` 또는 `Invalid API Key`

**해결방법**:
- `.env` 파일의 API 키가 올바른지 확인
- API 키에 공백이나 따옴표가 없는지 확인
- 서버 재시작

---

## 📞 문의 및 지원

문제가 지속되면 다음을 확인하세요:
1. 로그 파일: `app/tasks/full_scheduler.log`
2. Docker 로그: `docker logs market-plan-b`
3. 서버 로그: 터미널 출력 확인

---

## 📝 라이선스

이 프로젝트는 내부 사용을 위한 것입니다.
