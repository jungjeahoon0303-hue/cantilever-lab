# 검사 요청 #07 — review_06 반영

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 99bbe2a543450840c6bc844f0d47b31a61081371e7f31f784634d00048755397  (검사 중 수정하지 않음)
테스트(이 해시 기준): run_e2e_test.py 31개 시나리오 ALL PASSED / test_mechanics.py 6 PASS / qa/viewports.py 4해상도 넘침 없음

## review_06 조치
- P1 section 파괴 BMD 한계선: failSnap 에 임계 순간 단면(H, S) 저장, drawBMD 는 파괴 후 failSnap.S 로 My/Mu 계산.
  E2E 30 추가 assert: BMD Mu = 3.67875, Mcr = 3.3634 (review_06 손계산 일치), 동시에 전역 BEAM_S 는 최종 15cm 값으로 복원 확인.
- P2-2 전역 단면 임시 변경: calculateBeamPhysics() 를 try/finally 래퍼로 바꾸고 본문은 calculateBeamPhysicsInner(). 예외가 나도 BEAM_H/I/S 복원 보장.
  (명시적 중간 복원 제거 → triggerFailure/HUD 는 임계 단면을 보고, 함수 종료 시 최종 단면 복원)
- P2-3 section 임계 시 보 블록 scale.y 와 bracket 도 h_cr 로, 파편 geometry 도 h_cr (triggerFailure 가 래퍼 안에서 실행). resetExperiment 에서 현재 두께로 외형 복원. E2E 30: scale.y = h_cr/0.28 확인.
- P2-1 바닥 chord 근사: 알려진 한계로 유지.

## 검사 부탁 (코드 수정 금지)
1. 조치 확인 + 래퍼 도입으로 인한 회귀(특히 재진입: triggerFailure → updateHUD → checkMissions 가 래퍼 내부에서 실행되는 점, 슬라이더/재료 전환 중 중첩 호출)
2. 최종 배포 판정 5줄
P0/P1/P2 로 검사기 폴더 review_07.md 에 저장.
