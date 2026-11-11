# 검사 요청 #16 — review_15 P1 2건·P2-1 수정 (새 고정 해시)

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 29bfc3173cbdeb50402fb43483782b87bc51d091234b6664936da6b65151235e
테스트: run_e2e_test.py 44개 ALL PASSED / test_mechanics.py 7 PASS / qa/viewports.py 5해상도 넘침·가림 없음 + 조작부 가시성 검사(신규) 통과
스크린샷: qa/shots/vp_*.png 갱신 (휴대폰·태블릿 하단 부재 설정 바 정상 높이)
검사 중 파일을 바꾸지 않겠음.

## 수정
- P1-1 좁은 화면 부재 설정 바 납작해짐: `@media (max-width:820px) .setup-bar { flex: 0 0 auto; }` (세로 flex 에서 flex-basis 0 + overflow hidden 으로 0 높이가 되던 것). qa/viewports.py 에 setupBar·dockBar·btnEnd·btnUnload·btnReset·beamHSlider·spawnHeavy·matGrid 가 화면 안에 다 보이고 그 중심점에서 elementFromPoint 가 자기 자신인지 검사하는 항목 추가(도크 가로 스크롤만 허용). 5해상도 모두 "controls all visible".
- P1-2 고무 파괴 용어: triggerFailure 토스트에 `currentMat.isRubber` 분기("극한강도 도달! 고무는 소성 없이 탄성으로 늘어나다가 한 번에 찢어져 … (초탄성 파단)"), 상태 배지 `m.isRubber ? '💥 초탄성 파단 (극한강도 도달)'`. E2E 43 에 statusBadge·toast 에 "취성" 없음·"초탄성" 있음 단언 추가.
- P2-1 랭킹 안내 토스트 가림: showToast 가 모달 열림을 감지하면 `.over-modal` 클래스(z-index 1100, 화면 위쪽 top 18px — 모달 버튼을 가리지 않음). 토스트 transition 을 `all` → opacity·transform 으로 한정(z-index 가 900→1100 으로 서서히 전환되던 문제). E2E 44 에 over-modal·z-index>1000·top<60 단언 추가.
- 번외 파일 index_plus.html(사용자 허용 하에 UX 추가 실험: 핵심 수치 타일·다음 미션 강조·점수 팝업·단축키)은 검사 대상 아님. 남은 P2(이미 겹친 하중 예외, chord 근사)는 그대로.

## 검사 부탁 (코드 수정 금지)
- 위 3건 해소 여부(특히 5해상도 스크린샷의 하단 부재 설정 바·버튼 접근성, 고무 파괴 시 배지·토스트·대사 일관성, 모달 위 토스트), 회귀 여부, 최종 판정 3줄. 검사기 폴더 review_16.md 에 저장.
