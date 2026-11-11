# 검사 요청 #19 — review_18 잔여 P2 1건(동시 점수 팝업 화면 밖 잘림) 수정 (번외 index_plus.html, 새 고정 해시)

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index_plus.html  (index.html 은 #16 통과본 29bfc317… 그대로)
고정 SHA-256: 1ba8b7a3d7efe966273a386bf585e39d84efb2ecfa6ad23e1163a357d05b3da1
테스트: E2E_PAGE=index_plus.html run_e2e_test.py 45개 ALL PASSED / qa/viewports.py 5해상도 통과 / 스크린샷 qa/shots_plus/ 갱신
검사 중 파일을 바꾸지 않겠음.

## 수정 (scorePop 한 줄)
- 동시 완료 팝업을 위가 아니라 아래로 쌓음: `top = Math.max(8, r.top - 4 + stack * 28)` (이전 `r.top - 4 - stack * 26`). 데스크톱 점수 배지(top ≈ 18px) 기준 첫 팝업 ≈ 16px, 둘째 ≈ 44px 로 둘 다 화면 안에서 시작해 위로 떠오르며 사라짐.
- E2E 45 단언 보강: 두 팝업의 getBoundingClientRect().top 이 모두 0 이상·화면 안이고 둘째가 첫째보다 20px 이상 아래. (실측 16.4 / 44.4)

## 검사 부탁 (코드 수정 금지)
- review_18 잔여 P2 해소 여부, 회귀 여부, 본 파일 승격 가능 의견, 최종 판정 3줄. 검사기 폴더 review_19.md 에 저장.
