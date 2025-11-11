# Redis 설정 (크롤링 중복 방지)
1. Docker 로 Redis 서버 띄우기
 - docker run -d --name redis-server -p 6379:6379 redis:latest
2. Python에 Redis 라이브러리 설치
 - pip install redis