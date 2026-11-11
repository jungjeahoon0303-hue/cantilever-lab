# 검사 요청 #09 — review_08 P2-2 반영 (반응형 CSS)

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 2557b124f6cb28cf71403dbc111254c161d017f81e5ae967ad21d8d4e4af3beb
테스트: run_e2e_test.py 31개 ALL PASSED / test_mechanics.py 6 PASS / qa/viewports.py 5해상도(540x900 추가) 넘침 없음 + 첫 안내 화면 밖 잘림 검사 통과
스크린샷: qa/shots/vp_*_first.png (첫 안내가 보이는 초기 상태), vp_*.png

## 변경
- review_08 P2-2 원인: 이전 패치에서 '@media (max-width: 480px)' 블록이 820px 블록 중간에 끼어들어, .scale-badge/.cam-hint 숨김, .mission-card 모바일 배치, .first-hint 중앙 정렬, .toast-box 위치가 ≤480px 에서만 적용되고 481~820px 에서는 빠져 있었음.
  → 위 규칙들을 820px 블록으로 되돌리고, 480px 블록에는 도크 카드 세로형과 안내 보조문구 숨김만 남김.
- qa/viewports.py: 540x900 추가, 하중 생성 전 첫 안내 상태 스크린샷(_first) + 안내 박스가 화면 밖으로 나가면 실패.

## 검사 부탁 (코드 수정 금지)
- CSS 변경 회귀만 확인하고 최종 판정 3줄. 검사기 폴더 review_09.md 에 저장.
