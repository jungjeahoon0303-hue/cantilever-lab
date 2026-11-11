# 검사 요청 #08 (최종 확인) — review_07 P2 반영 + 첫 사용 안내

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 85c6245be8f77d7b1f29695c60b116787a14fd296936c3b2977bd28f5e96fa15  (검사 중 수정하지 않음)
테스트(이 해시 기준): run_e2e_test.py 31개 시나리오 ALL PASSED / test_mechanics.py 6 PASS / qa/viewports.py 4해상도 넘침 없음
실제 링크 확인: http://localhost:8000/index.html 응답 해시 = 위 해시, Cache-Control: no-store (qa/shots/link_localhost_8000.png 는 직전 빌드 화면)

## 변경
- review_07 P2-2: 래퍼 finally 에서 예외(ok=false)일 때 보 블록/브래킷 scale 도 현재 두께로 복원 (정상 파괴 시에는 임계 외형 유지).
- review_07 P2-3: E2E 30 에 My(=Mcr)=3.36343 assert 추가.
- 첫 사용 안내 말풍선(firstHint): 도크 위 '하중물을 끌어서 보 위에 놓아 보세요 (클릭하면 끝단에 자동 배치)', 첫 사용자 하중 배치 시(quiet 재하 제외) 또는 × 로 닫힘. E2E: 시작 시 보임 → 첫 하중 후 숨김.
- σ-ε 차트: '탄성구간 확대' 설명을 위쪽으로 옮기고 경계에 옅은 세로 점선 (아래 εy/εu/εf 눈금과 겹침 해소).
- review_07 P2-1(바닥 chord) 알려진 한계 유지.

## 검사 부탁 (코드 수정 금지)
- 위 변경의 회귀 여부만 빠르게 확인하고, 최종 배포 판정 5줄. P0/P1/P2 로 검사기 폴더 review_08.md 에 저장.
