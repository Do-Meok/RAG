# RAG (레시피 벡터 데이터 적재 파이프라인)

만개의레시피 CSV 원본 데이터를 정제하여 임베딩한 뒤, PGVector(`domeok_rag` DB)에 적재하는 오프라인 배치 파이프라인\
여기서 만들어진 `recipe_vectors` 컬렉션은 백엔드([Back](../Back)) 프로젝트의 `domains/rag`에서 레시피 추천(RAG 검색) 시 조회하는 데이터입니다.

## 파이프라인 흐름

```
raw_csv/*.csv  →  preprocess.py  →  process_csv/*.csv  →  embed_and_store.py  →  PGVector(recipe_vectors)
```

1. **[preprocess.py](preprocess.py)** - `raw_csv/`의 원본 레시피 CSV(cp949 인코딩, "만개의레시피" 원본 컬럼)를 읽어
   - 필요한 컬럼만 추출 후 `board_name`, `recipe_name`, `author_name`, `recipe_materials`, `recipe_difficulty`, `time`으로 매핑
   - 재료 텍스트에서 대괄호/단위/숫자/불용어(약간, 적당량, 큰술 등)를 제거해 순수 재료명만 남긴 `parsed_ingredients` 컬럼 생성
   - `recipe_name`, `recipe_materials`가 비어있는 행 제거
   - 결과를 UTF-8-SIG로 `process_csv/`에 저장

2. **[embed_and_store.py](embed_and_store.py)** - `process_csv/`의 정제된 CSV를 읽어
   - OpenAI `text-embedding-3-small` 모델로 `parsed_ingredients`만 임베딩 (레시피명은 벡터에 포함하지 않음 - 보유 재료명과 레시피명이 같아 과다 매칭되는 문제 방지)
   - `recipe_name`, `board_name`, `author_name`, `recipe_difficulty`, `time`은 메타데이터로만 저장
   - `CacheBackedEmbeddings` + `LocalFileStore("./cache/")`로 임베딩 결과를 로컬 캐시하여 재실행 시 비용/속도 절감
   - 1,000행 단위(`BATCH_SIZE`)로 청크 스트리밍하며 PGVector `recipe_vectors` 컬렉션에 적재
   - 적재 중 실패 시 해당 지점까지 로그를 남기고 중단 - 캐시가 남아있으므로 원인 해결 후 재실행하면 실패 지점부터 빠르게 이어서 진행 가능

`main.py`는 현재 사용되지 않는 placeholder 진입점입니다.

## 사전 준비

- Python 3.14, [uv](https://docs.astral.sh/uv/) 패키지 매니저
- PostgreSQL + pgvector 확장이 설치된 `domeok_rag` 데이터베이스 (Back 프로젝트와 동일 DB 인스턴스 사용)
- `raw_csv/` 디렉토리에 원본 CSV 배치 (Git에는 포함되지 않음, `.gitignore` 처리됨)

### 환경 변수 (`.env`)

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | 임베딩 생성을 위한 OpenAI API 키 |
| `DB_USER` | PostgreSQL 사용자명 |
| `DB_PASSWORD` | PostgreSQL 비밀번호 |

`embed_and_store.py`는 `localhost:5432/domeok_rag`에 접속합니다. 원격 DB를 사용한다면 `DB_CONNECTION` 값을 직접 수정해야 합니다.

## 실행

```bash
uv sync
```

```bash
uv run preprocess.py
```

```bash
uv run embed_and_store.py
```

`preprocess.py`, `embed_and_store.py`의 상단 상수(`RAW_FILE_PATH`, `CSV_FILE_PATH`)는 처리할 CSV 파일 하나를 가리키므로, `raw_csv/` 내 여러 파일을 모두 적재하려면 파일별로 값을 바꿔가며 반복 실행해야 합니다.

## 디렉토리 구성

| 경로 | 설명 |
| --- | --- |
| `raw_csv/` | 원본 레시피 CSV (gitignore) |
| `process_csv/` | 전처리 완료된 CSV (gitignore) |
| `cache/` | 임베딩 결과 로컬 캐시 (gitignore) |
