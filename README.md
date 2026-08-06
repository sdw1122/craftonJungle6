# Flask + PostgreSQL Docker 개발 환경

## 실행

Docker Desktop을 실행한 뒤 프로젝트 폴더에서 다음 명령을 실행합니다.

```powershell
docker compose up --build
```

브라우저에서 `http://localhost:5000`을 열어 확인합니다.
PostgreSQL은 호스트의 `localhost:5432`에서 접근할 수 있습니다.

## 주요 명령

```powershell
# 백그라운드 실행
docker compose up --build -d

# 로그 확인
docker compose logs -f web

# 컨테이너 종료
docker compose down

# 컨테이너와 PostgreSQL 데이터까지 삭제
docker compose down -v
```

`docker compose down -v`는 개발 DB 데이터를 모두 삭제하므로 초기화가 필요할 때만 사용합니다.
