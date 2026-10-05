---
type: source
doc_id: operations:ext-reservation-ledger
title: 주문별 재고 확보 상태 장부
dataset: main
collection: operations
family: ext-reservation-ledger
active: true
updated: '2026-09-01'
version: v1
owner: 운영팀
doc_type: 업무가이드
edited: '2026-10-02'
raw_paths:
- 본실습/knowledge/operations/raw/ext-reservation-ledger.md
related:
- operations:production-schedule
fictional: true
document_path: 본실습/knowledge/operations/documents/ext-reservation-ledger.md
---

# 주문별 재고 확보 상태 장부

운영팀 · 업무가이드 · v1 · 검색 사용

## 업무 지식

재고 확보 장부에는 품목, 요청 수량, 연결 주문, 확보 확인 여부와 남은 확인 조건을 기록합니다. 상담에서 제시한 예상 수량과 이미 다른 주문에 배정된 수량을 구분해야 같은 물품을 두 주문에 약속하지 않습니다. 입고 예정 물품은 현재 창고 수량과 별도 표시합니다. 이 문서는 장부 작성 방법이며 현재 잔여 재고나 확보 가능 수량을 제공하지 않습니다. 주문 변경이나 취소가 확인되면 관련 배정 기록도 대조하고, 담당자 확인 없이 확보 상태를 유지하거나 해제하지 않습니다.

## 원자료

- [업무 배경·작업 내역·확인 사항](../raw/ext-reservation-ledger.md)

## 관련 문서

- [신입사원 선물 세트 제작 일정과 시작 조건](production-schedule.md)
