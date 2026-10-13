# 본실습 매뉴얼 검색 DB

문서 적재와 임베딩을 마친 배포용 Chroma DB입니다. **이 폴더 전체를 그대로 열어** 사용하세요. `chroma.sqlite3`와 하위 인덱스 폴더가 모두 필요합니다.

- 컬렉션: `day59_manual`
- 저장 문서: 44개 (고용노동부 2024 유연근무 활용 매뉴얼 44절, 절 하나가 레코드 하나)
- 임베딩: **`text-embedding-3-large`, 768차원**
- 거리: cosine
- 메타데이터: `source_id`(= 문서 ID), `title`, `category`, `pdf_page`, `source`, `url`
- 제작 환경: `chromadb==1.5.9`, `langchain-chroma==1.1.0`

질문도 같은 모델·차원으로 임베딩합니다.
