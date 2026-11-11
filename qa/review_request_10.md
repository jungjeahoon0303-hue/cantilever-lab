# 검사 요청 #10 — 남은 P2(바닥 chord) 완화 + 소성 수치 정밀도

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 4724049b9b556eebb17e2daa7ecf18e0575fc577513a5a922684c8d9238d9d75
테스트: run_e2e_test.py 31개 ALL PASSED / test_mechanics.py 7 PASS / qa/viewports.py 5해상도 넘침·첫 안내 잘림 없음

## 변경
1. 화면 보 블록 NUM_SEGS 20 → 40 (블록 0.15 m). 바닥 꺾임 chord 근사 길이가 절반으로, 휨 곡선이 부드러워짐. 취성 파괴 파편 구간은 길이 기준(≈0.9 m)으로 유지.
2. 소성 계산 격자를 화면 블록과 분리: N_PL = 240 (plSeg = 0.025 m), 형상 적분 N_INT 120 → 240.
   - 이유: Python 재구현으로 수렴 확인 — 같은 모델의 잔류 끝단 처짐(연강, 중장비 3대 5.9/5.0/4.2 m 후 제거):
     노드 20개 13.224 cm / 40개 12.332 / 80개 12.108 / 160개 12.050 / 정밀 적분 δp=∫κp(ξ)(L−ξ)dξ = 12.030 cm.
     (JS 20·40노드 결과가 Python 재구현과 소수 3자리까지 일치 → 구현 독립 검증)
   - 현재 앱 값 12.038 cm (정밀해 대비 0.07%). test_mechanics.py 에 정밀해 12.030 기준 테스트, E2E 10번에 ±0.5% assert 추가.
   - 소성 흔적(윗면 주황) 판정은 블록 왼쪽 끝의 κp 보간값으로.
3. E2E 의 '끝 블록' 참조를 beamSegments[NUM_SEGS-1] 로 일반화.

## 검사 부탁 (코드 수정 금지)
- 위 변경의 회귀 여부(특히 plasticKappa 인덱싱/보간이 바뀐 모든 소비처, section 임계·파괴 파편·heatmap)와 최종 판정 3줄. 검사기 폴더 review_10.md 에 저장.
