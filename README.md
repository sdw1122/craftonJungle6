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

## TMDB 영화 카탈로그 동기화

화면과 API는 TMDB를 직접 호출하지 않고 PostgreSQL의 영화 데이터를 조회합니다.
기존 Docker 볼륨을 사용하는 환경에서는 최초 한 번 스키마를 갱신합니다.

```powershell
docker compose exec web flask upgrade-movie-catalog-schema
```

`.env`에 `TMDB_ACCESS_TOKEN`을 설정한 뒤 인기 영화, 한국 현재 상영작 전체와 상세정보를 동기화합니다.

```powershell
docker compose exec web flask sync-popular-movies --limit 100
```

동기화 명령만 TMDB API를 호출하며 영화, 한국어 제목, 한국 극장 개봉일, 인기 순위,
한국 현재 상영작 전체의 인기순, 장르, 감독·출연진과 국내 OTT 제공 정보를 DB에 저장합니다. 랭킹 화면은
그중 상위 50편을 표시합니다. 화면의
`박스오피스`는 실제 관객·매출 순위가 아니라 TMDB 기준 한국 극장 상영작 인기순입니다.
