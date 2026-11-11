# 검사 요청 #18 — review_17 P1 1건·P2 3건 수정 (번외 index_plus.html, 새 고정 해시)

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index_plus.html  (index.html 은 #16 통과본 29bfc317… 그대로)
고정 SHA-256: e9906d0ceac04bac0de643c904a870bb841711d53a0bc57a8b6331b483cd8f83
테스트: E2E_PAGE=index_plus.html run_e2e_test.py 45개 ALL PASSED (45번은 번외 전용 신규) / index.html 44개 ALL PASSED / test_mechanics.py 7 PASS / qa/viewports.py 5해상도 통과(번외는 statRow·tileS 가시성 포함)
스크린샷: 번외 전용 qa/shots_plus/vp_*.png (5해상도, 타일 보임)
검사 중 파일을 바꾸지 않겠음.

## 수정
- P1 σ 타일 막대 분모: `ratio / (m.fu / m.fy) * 100` → `ratio * 100` (숫자와 같은 σ/σ_y 기준, 100% 넘으면 가득 찬 막대 + warn/danger 색). E2E 45: 연강 중장비 3개(5.52·4.62·3.72 m)에서 숫자 105% / 막대 100% / warn 단언.
- P2-1 연성 안내: MISSION_HOW.ductile → "연강 보에 중장비 3개를 올려 항복시킨 뒤(σ > σ_y), 두께 슬라이더를 23 cm 이하로 줄이면 크게 휘다 끊어집니다." 손계산: 3개 M = 679.8 kN·m, h = 23 cm 에서 S = 1,587 cm³ → M_u = 650.7 kN·m < M (24 cm 는 708.5 로 안 깨짐). E2E 45 에서 실제로 슬라이더 0.23 → isBroken, failureMode 'ductile', missions.ductile 완료 단언.
- P2-2 단축키: `e.repeat || isDragging || moveDrag || orbitDrag` 이면 무시. E2E 45: 각 상태에서 1·2·3 키와 repeat 키로 하중 수가 변하지 않음 단언.
- P2-3 점수 팝업: z-index 950 → 1150(모달 1000 위), 동시 완료 시 기존 팝업 수만큼 26px 씩 위로 층층이. E2E 45: openConcept 로 learn 완료 팝업 z 1150, 두 번째 팝업 top 이 26px 위, 모달 열린 동안 숫자 키 무시 단언.
- qa/viewports.py: 번외 파일이면 statRow·tileS 도 가시성 검사(패널 안에서 scrollIntoView 후 측정 — 휴대폰은 패널이 짧아 스크롤로 닿는 것을 허용).

## 검사 부탁 (코드 수정 금지)
- 위 4건 해소 여부, 연성 안내 손계산 재확인(기본 클릭 배치 5.52·4.62·3.72 m 기준), 회귀 여부, 본 파일 승격 가능 의견, 최종 판정 3줄. 검사기 폴더 review_18.md 에 저장.
