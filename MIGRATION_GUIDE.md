# 스케줄러 및 DB 마이그레이션 가이드

## 변경 사항

### 1. 스케줄러 변경
- **1시간마다 (매 정각)**: 크롤링 → contents 저장만
- **24시간마다 (매일 00:05)**: 전체 AI 파이프라인 실행 (analytics, strategies, report 생성)

### 2. DB 스키마 변경
- `analytics.variable_scores` 컬럼 삭제
- `contents.region_id` 컬럼 삭제

## 마이그레이션 실행

### 1. DB 컬럼 삭제
```bash
psql -U postgres -d market-plan-b -p 5433 -f app/db/migrate_remove_columns.sql
```

또는 PostgreSQL 클라이언트에서 직접 실행:
```sql
ALTER TABLE analytics DROP COLUMN IF EXISTS variable_scores;
ALTER TABLE contents DROP COLUMN IF EXISTS region_id;
```

### 2. 스케줄러 재시작
```bash
# Windows
cd app/tasks
run_background.bat

# Linux/Mac
cd app/tasks
./run_background.sh
```

## 동작 방식

### 시간별 작업 (hourly_job)
1. 4개 크롤러 병렬 실행 (OilPrice, Google, Investing, Yahoo)
2. JSON 파일 저장: `app/ai/repository/data/news/news_YYYYMMDD.json`
3. 뉴스 임베딩 처리
4. regions 테이블 업데이트
5. contents 테이블에 저장

### 일일 작업 (daily_job)
1. 당일 JSON 파일 로드 (24시간 누적 데이터)
2. 전체 AI 파이프라인 실행:
   - 모델링 (예측)
   - analytics 저장
   - 대응책 생성 (strategies)
   - 리포트 생성 (reports)

## 주의사항
- 일일 작업은 24시간 동안 수집된 데이터를 사용하므로 매일 00:05에 실행
- JSON 파일이 없으면 일일 작업은 스킵됨
- 크롤링 실패 시에도 다음 시간에 재시도
