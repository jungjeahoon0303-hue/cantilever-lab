# 검사 요청 #17 — 번외 파일 index_plus.html (UX 추가 실험) 검사

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index_plus.html  (index.html 은 #16 통과본 그대로, 건드리지 않음)
고정 SHA-256: a7f02d2fee344cfd6180094421e7040109018e01ab4a95d0721d81ebe64462aa (MISSION_HOW 하중 예시를 손계산으로 보정: yield 중장비 3개, rubber 시험추, wood 중장비, ductile 중장비 5개 이상)
테스트: E2E_PAGE=index_plus.html run_e2e_test.py 44개 ALL PASSED / qa/viewports.py 5해상도 통과(조작부 가시성 포함)
기준: #16 통과본 index.html 과의 차이만 검사하면 됨 (`fc` 또는 diff). 역학 계산은 동일.

## 추가된 것 (사용자 허용: "번외 파일을 만들어 UX/UI 부족한 부분을 자체적으로 개선")
1. 핵심 수치 타일 `#statRow` (BMD 아래, 대사 위): M (M_u 대비 바), σ/σ_y % (σ_u 대비 바), 끝단 δ (L/10 대비 바). `updateStatTiles()` 가 updateHUD 끝에서 갱신. 파괴 후에는 failSnap.S 기준 M_u, 라벨 "임계 M = M_u". 색: ok/warn(≥80% 또는 연성 항복)/danger(취성 한계 초과·파괴).
2. 미션 열: 첫 미완료 미션에 `.next` 강조 + "다음" 배지, 각 항목 title 에 하는 법(MISSION_HOW), 항목 클릭 시 토스트로 하는 법 안내. completeMission 후 renderMissionList 재호출로 '다음' 이동.
3. 점수 팝업 `scorePop(pts)`: 점수 배지(휴대폰에서는 미션 머리글) 위에 "+N" 떠오름, 1.2 s 후 제거.
4. 재료 칩에 보 색 점(.sw, MATERIALS[key].color).
5. 키보드 단축키: 1~5 하중물(도크 클릭과 동일 경로), U 하중 제거, R 시편 교체, V 시점, G 가이드. 입력창·모달 열림·Ctrl/Alt/Meta 조합이면 무시. cam-hint 에 안내 추가.
6. 데스크톱(≥821px) 도크 `overflow: visible` (hover 들림이 잘리지 않게; 도크는 데스크톱에서 스크롤 없음).

## 검사 부탁 (코드 수정 금지)
- 타일 수치가 표·BMD 와 모든 상태(탄성/소성/파괴 4모드/고무)에서 일치하는지, 단축키가 드래그·모달·입력과 충돌하지 않는지, '다음' 강조와 MISSION_HOW 문구의 역학적 정확성(특히 lever·yield·ductile 안내의 하중 예시가 실제로 그 결과를 내는지), 5해상도 배치 회귀. 이 파일을 본 파일로 승격해도 되는지 의견. 최종 판정 3줄. 검사기 폴더 review_17.md 에 저장.
