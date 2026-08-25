import re
import pandas as pd
import os

'''
레시피 csv파일을 읽어와 인코딩 문제와 불필요한 데이터를 정제하고, Vector DB 입력을 위해
가공된 CSV 데이터셋으로 변환하는 전처리 스크립트
'''

# ==========================================
# [설정] 파일 경로 및 상수 정의
# ==========================================
RAW_FILE_PATH = "raw_csv/TB_RECIPE_SEARCH-220701.csv"   # 변환할 파일
OUTPUT_DIR = "process_csv"  # 변환 후 저장할 디렉토리

# 변경된 컬럼 매핑 기준 적용
REQUIRED_COLUMNS = ['RCP_TTL', 'CKG_NM', 'RGTR_NM', 'CKG_MTRL_CN', 'CKG_DODF_NM', 'CKG_TIME_NM']
RENAME_MAP = {
    'RCP_TTL': 'board_name',
    'CKG_NM': 'recipe_name',
    'RGTR_NM': 'author_name',
    'CKG_MTRL_CN': 'recipe_materials',
    'CKG_DODF_NM': 'recipe_difficulty',
    'CKG_TIME_NM': 'time',
}

# 제외할 불용어 목록
STOPWORDS = {"약간", "적당량", "소스", "큰술", "작은술", "적당히", "컵"}

# ==========================================
# [함수] 재료 전처리 로직
# ==========================================
def extract_pure_ingredients(text):
    """
    레시피 재료 텍스트에서 단위와 불용어를 제거하고 순수 재료명만 추출
    """
    if pd.isna(text):
        return ""

    # 1. [재료], [양념] 등 대괄호 및 특수문자 제거
    cleaned = re.sub(r"\[.*?\]", "", text)

    # 2. '|' 구분자로 나누어 각 재료 가져오기
    items = cleaned.split("|")

    pure_ingredients = []
    for item in items:
        item = item.strip()
        if not item:
            continue

        # 3. 뒤에 붙은 숫자 및 단위 제거 (예: "계란 4개" -> "계란")
        match = re.match(r"^([가-힣a-zA-Z\s]+)", item)
        if match:
            ingredient = match.group(1).strip()
            # 불용어 제외 처리
            if ingredient not in STOPWORDS:
                pure_ingredients.append(ingredient)

    # 4. 콤마(,)로 연결된 문자열로 반환
    return ", ".join(pure_ingredients)

# ==========================================
# [메인 실행] 데이터 처리 및 저장 프로세스
# ==========================================
def main():
    # 1. 원본 파일 로드
    if not os.path.exists(RAW_FILE_PATH):
        print(f" 에러: 원본 파일이 경로에 존재하지 않음: {RAW_FILE_PATH}")
        return

    print(f" 파일을 읽는 중... ({RAW_FILE_PATH})")
    with open(RAW_FILE_PATH, "r", encoding="cp949", errors="ignore") as f:
        df = pd.read_csv(f)

    # 2. 필요한 컬럼 필터링 및 이름 변경
    df = df[REQUIRED_COLUMNS]
    df = df.rename(columns=RENAME_MAP)

    # 3. 필수 결측치 제거
    # (레시피 이름과 재료가 비어 있는 행 위주로 제거, 작성자명이나 난이도가 비어 있어도 행이 삭제되지 않도록 방지함)
    df = df.dropna(subset=['recipe_name', 'recipe_materials'])

    # 4. 재료 파싱 작업 수행
    print(" 재료 데이터 전처리 중...")
    df["parsed_ingredients"] = df["recipe_materials"].apply(extract_pure_ingredients)

    # 5. 기존의 상세 재료 원본 컬럼 제거
    df = df.drop(columns=['recipe_materials'])

    # 6. 결과 저장 경로 설정 및 디렉토리 생성
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    file_name = os.path.basename(RAW_FILE_PATH)
    output_path = os.path.join(OUTPUT_DIR, file_name)

    # 7. UTF-8-BOM(utf-8-sig) 인코딩으로 저장하여 한글 깨짐 방지
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"🎉 전처리 완료! (저장 완료: {output_path})")


if __name__ == "__main__":
    main()