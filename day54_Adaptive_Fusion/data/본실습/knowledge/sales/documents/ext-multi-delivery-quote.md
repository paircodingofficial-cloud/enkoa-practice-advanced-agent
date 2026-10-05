---
type: source
doc_id: sales:ext-multi-delivery-quote
title: 한 주문을 여러 차례 발송할 때의 견적 분리
dataset: main
collection: sales
family: ext-multi-delivery-quote
active: true
updated: '2026-09-01'
version: v1
owner: 영업팀
doc_type: 업무가이드
edited: '2026-10-02'
raw_paths:
- 본실습/knowledge/sales/raw/ext-multi-delivery-quote.md
related:
- operations:split-shipping
- sales:welcome-order-v2
fictional: true
document_path: 본실습/knowledge/sales/documents/ext-multi-delivery-quote.md
---

# 한 주문을 여러 차례 발송할 때의 견적 분리

영업팀 · 업무가이드 · v1 · 검색 사용

## 업무 지식

한 주문을 입사 일정에 맞춰 나눠 보내려면 총 주문 수량과 회차별 발송 수량을 별도로 받습니다. 각 회차의 목적지, 예상 발송 요청 시점, 보관 요청 여부를 견적 범위에 표시합니다. 여러 번 출고하는 안은 한 번에 전량 배송하는 안과 작업량이 다르므로 이전 배송비를 그대로 적용하지 않습니다. 영업팀은 운영팀이 확인한 가능 범위만 고객에게 안내합니다. 전체 주문이 확정되어도 개별 회차의 주소와 출고 지시는 지정 절차로 확인해야 하며 미정 명단을 임의로 채우지 않습니다. 개별 배송 명단의 제출 시점은 operations:split-shipping 기준을 따르며, 변경이 필요하면 운영팀에 별도 확인합니다.

## 원자료

- [업무 배경·작업 내역·확인 사항](../raw/ext-multi-delivery-quote.md)

## 관련 문서

- [직원별 개별 배송 명단과 예상 이동 기간](../../operations/documents/split-shipping.md)
- [고객사 신입사원 선물 세트 주문 조건과 접수 자료](welcome-order-v2.md)
