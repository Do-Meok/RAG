import os
import gc
import pandas as pd
from tqdm import tqdm   # 진행률 출력
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from langchain_postgres import PGVector
from langchain_core.documents import Document

load_dotenv()

# ==========================================
# [설정] 환경 변수 및 DB 연결 정의
# ==========================================
load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')

# DB 연결
DB_CONNECTION = f"postgresql+psycopg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@localhost:5432/domeok_rag"

# 적재할 csv 파일명
CSV_FILE_PATH = "process_csv/TB_RECIPE_SEARCH-220701.csv"

# 임베딩 모델 지정
underlying_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


# ==========================================
# [임베더] 캐시 백드 임베더 초기화
# ==========================================

# 임베딩 비용 및 속도를 아끼기 위한 로컬 캐시 경로 설정
store = LocalFileStore("./cache/")

cached_embedder = CacheBackedEmbeddings.from_bytes_store(
    underlying_embeddings,
    store,
    namespace=underlying_embeddings.model
)
print("캐시 백드 임베더 준비 완료")

# ==========================================
# [Vector DB] PGVector 통로 개설
# ==========================================
vector_store = PGVector(
    embeddings=cached_embedder,
    connection=DB_CONNECTION,
    collection_name="recipe_vectors"
)
print("PGVector 연결 통로 개설 완료")

# ==========================================
# [적재] Chunk-by-Chunk 스트리밍 적재
# ==========================================
BATCH_SIZE = 1000
print("pgvector 스트리밍 적재 시작")

# 파일 전체 행 수를 파악하여 진행률(tqdm)을 표시하기 위함
total_rows = sum(1 for _ in open(CSV_FILE_PATH, 'r', encoding='utf-8-sig')) - 1  # 헤더 제외
total_chunks = (total_rows // BATCH_SIZE) + (1 if total_rows % BATCH_SIZE != 0 else 0)

# CSVLoader 대신 pandas chunksize 옵션으로 1,000개씩만 메모리에 올리며 전진
chunk_iterator = pd.read_csv(CSV_FILE_PATH, chunksize=BATCH_SIZE, encoding="utf-8-sig")

# tqdm 진행 표시줄 가동
with tqdm(total=total_chunks, desc="적재 진행도", unit="chunk") as pbar:
    for idx, chunk in enumerate(chunk_iterator):
        docs = []

        # 1,000개의 행 데이터 가공
        for _, row in chunk.iterrows():
            # 결측치(NaN) 방어 처리.
            # 벡터 유사도는 식재료만 쓰도록 page_content에 parsed_ingredients만 넣는다.
            # (recipe_name을 같이 넣으면 보유 식재료명=레시피명인 문서가 과다 매칭 이슈 발생)
            recipe_name = str(row.get('recipe_name', '')).strip()
            ingredients = str(row.get('parsed_ingredients', '')).strip()

            page_content = f"parsed_ingredients: {ingredients}"

            # 레시피명·보드 정보는 메타데이터로만 보관 (검색 벡터에 미포함)
            metadata = {
                "recipe_name": recipe_name,
                "board_name": str(row.get('board_name', '')).strip(),
                "author_name": str(row.get('author_name', '')).strip(),
                "recipe_difficulty": str(row.get('recipe_difficulty', '')).strip(),
                "time": str(row.get('time', '')).strip()
            }

            doc = Document(page_content=page_content, metadata=metadata)
            docs.append(doc)

        start_num = idx * BATCH_SIZE

        try:
            # 순수 Insert 파이프라인 가동
            vector_store.add_documents(documents=docs)
        except Exception as e:
            print(f"\n [{start_num:,} ~ {start_num + len(docs):,}번째] 구간 적재 중 실패함: {e}")
            print("캐시가 적용되어 있으므로 에러 원인 해결 후 다시 실행하면 실패한 지점 부근부터 빠르게 이어서 적재")
            break

        # 가비지 컬렉터 가동하여 이 시점의 쓰지 않는 임시 메모리(docs)를 수거
        del docs
        gc.collect()

        pbar.update(1)

print(f"\n 모든 레시피 데이터({total_rows:,} 행)의 pgvector 적재 완료")