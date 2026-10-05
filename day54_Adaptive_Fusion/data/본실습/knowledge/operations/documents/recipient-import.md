---
type: source
doc_id: operations:recipient-import
title: 고객 배송 명단 접수 파일 점검
dataset: main
collection: operations
family: recipient-import
active: true
updated: '2026-09-01'
version: v1
owner: 운영팀
doc_type: 업무가이드
edited: '2026-10-02'
raw_paths:
- 본실습/knowledge/operations/raw/recipient-import.md
related:
- operations:split-shipping
- operations:production-schedule
fictional: true
document_path: 본실습/knowledge/operations/documents/recipient-import.md
---

# 고객 배송 명단 접수 파일 점검

운영팀 · 업무가이드 · v1 · 검색 사용

## 업무 지식

운영팀은 직원별 배송 명단을 받으면 필수 열이 있는지, 총 수량이 주문서와 맞는지, 주소나 연락처가 비어 있는 행이 있는지 확인합니다. 빈칸을 다른 직원의 값으로 채우거나 이름이 같다는 이유로 행을 자동 삭제하지 않습니다. 확인이 필요한 행 번호와 항목만 고객 담당자에게 전달해 수정본을 받습니다. 고객의 실제 주소를 팀 전체 공유 문서에 복사하지 않고 주문별 지정 전달 경로를 사용합니다. 명단의 필수 항목과 전달 시점은 split-shipping을 기준으로 합니다.

## 원자료

- [업무 배경·작업 내역·확인 사항](../raw/recipient-import.md)

## 관련 문서

- [직원별 개별 배송 명단과 예상 이동 기간](split-shipping.md)
- [신입사원 선물 세트 제작 일정과 시작 조건](production-schedule.md)
