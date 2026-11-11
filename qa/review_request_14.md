# 검사 요청 #14 — 화면 재배치(좌 미션 열 · 우 그래프 열 · 하단 도크+부재) · 점수/랭킹 · 대사 · 단면계수 개념 페이지

대상: C:\Users\USER\orca\workspaces\구조역학 과제\이어서\index.html
고정 SHA-256: 771a19d0c83ed75faa3d927caea519c69e5163b5cc992e0e7963375bfa3b3c29
테스트: run_e2e_test.py 42개 ALL PASSED / test_mechanics.py 7 PASS / qa/viewports.py 5해상도 넘침·가림 없음
스크린샷: qa/shots/vp_*.png (5해상도), 17_end_ranking.png, 01_initial.png, 10_missions_done.png
역학 계산(calculateBeamPhysics, 파괴 재구성, 이동 moveGap)은 이번에 손대지 않음.

## 사용자 요청 (원문 요지)
1. 하중물 선택창을 왼쪽으로 옮기고, 재료·단면두께 선택을 그 **오른쪽**에 같이 두어 **하단**에서 하중물과 부재를 고르게.
2. σ-ε 선도·BMD·실시간 역학 상태를 **오른쪽**에 몰아 배치. 두 그래프의 비중을 크게. 그래프 아래에 **실시간 상황을 반영하는 대사**.
3. 왼쪽 실험 미션을 **세로로 길게**, 미션 달성 시 **점수** 획득.
4. 오른쪽 **맨 아래 종료 버튼** → 내 점수와 **랭킹표** (나중에 배포용).
5. 응력 그래프에 **단면계수식** 추가. 응력 그래프를 **클릭**하면 개념 설명 페이지가 펼쳐지게.

## 변경 내용
### 배치 (데스크톱 > 820px)
- `.mission-panel`(왼쪽, `--col-l` 262px): 상단 HUD 아래 ~ 하단 바 위까지 세로 열. 점수/진행바/미션 12개(스크롤)/완료 메모.
- `.side-panel`(오른쪽, `--col-r` 400px): 바닥까지. `.panel-scroll`에 σ-ε 카드(높이 `--chart-h` 220px) → BMD 카드(150px) → 대사 말풍선 → critNote/linWarn → 실시간 역학 상태 표 → 응력 게이지 → 하중 목록.
  `.panel-foot`(고정): [❌ 하중 전부 제거][🔄 시편 교체] + [🏁 실험 종료 · 점수 확인].
- `.bottom-bar`(left 16px ~ 오른쪽 열 왼쪽): `.dock-bar`(하중물 5개, 세로형 카드) + 그 오른쪽 `.setup-bar`(재료 5칩, 두께 슬라이더, 화면 휨 배율).
- 화면 높이·폭에 따라 `--chart-h/--bmd-h`, `--col-l/--col-r`, 도크 카드 크기를 미디어쿼리로 축소(≤1400, ≤1120, 높이 ≤860/≤740).
- `sceneRect()`: 장면 영역 = 미션 열 오른쪽+14 ~ 오른쪽 열 왼쪽−12, HUD 아래 ~ 하단 바 위. CSS 변수 `--scene-top/--scene-left/--scene-cx/--bottom-h` 갱신(배율 배지·카메라 힌트·토스트·첫 안내 위치). ResizeObserver 는 hud-top/bottomBar/sidePanel/missionPanel 관찰.
- 좁은 화면(≤820): 미션은 장면 좌상단 접힌 카드(머리글에 점수 미니 배지), 오른쪽 열은 하단 시트(max-height 33vh, 그래프 2열), 하단 바는 도크 줄 + 부재 줄. `placeActionButtons()`가 [하중 제거][시편 교체] 버튼 DOM 을 좁으면 `#setupRow`, 넓으면 `#panelFoot` 로 옮김(ID 중복 없음). 넓↔좁 전환 때 미션 카드 접기/펼치기도 갱신.

### 점수·미션 (섹션 14)
- `MISSIONS` 배열 12개(점수 합 1,330): first 50 / move 50 / lever 150 / yield 100 / residual 150 / rubber 150 / brittle 150 / wood 100 / ductile 150 / thick 200 / iso 30 / learn 50.
- `missions[key]` 불리언 객체는 유지(기존 테스트 호환). `score = Σ 완료 점수`, `refreshScore()`가 상단 `#scoreBadge`, 열의 `#scoreVal`, 진행바, `#missionCnt` "n / 12" 갱신.
- 판정 추가: first(보 위 하중 ≥1), move(setLoadX 로 시작 위치 x0 에서 0.3 m 이상 이동), yield(연강 σ>σ_y, 파괴 전), wood(목재 파괴), ductile(연성 파괴·강재), iso(`noteIsoView`: |az|≥0.5 또는 el≥0.45 — 버튼 tween 도착·수동 회전), learn(개념 모달 열기).
- 완료 시 토스트 "+N점", 열 깜빡임, 점수 배지 bump. localStorage `cantilever.missions` 에 저장(새로고침 유지). `resetMissions()` 로 초기화.

### 종료·랭킹 (섹션 15)
- `#btnEnd` → `#endModal`: 점수, 미션 n/12, 등급(견습/주니어/책임/수석/마스터), 미션별 획득 칩, 이름 입력(12자) + [랭킹 등록].
- 랭킹은 `localStorage['cantilever.ranking']`(최대 50건 보관, 상위 10 표시, 점수 내림차순·동점은 먼저 등록 우선). 등록한 행은 `tr.me` 로 강조, 토스트에 현재 순위. 이름은 `escapeHtml` 로 표시(HTML 주입 안 됨, E2E 41 검사).
- `RANKING_ENDPOINT`(기본 null)에 주소를 넣으면 등록 때 POST 도 보냄(배포 시 서버 랭킹 연결 지점). [🔄 처음부터] = 점수·미션 초기화 + 시편 교체. [계속 실험] = 닫기.

### 대사 (`updateCommentary`, updateHUD 끝에서 호출)
- 상태별 문장/색/아바타: 파괴(연성·취성·이동 중 파괴 구분, 임계 M 표시) / 빈 보(재료 설명 + 안내) / 빈 보+잔류 처짐 / 고무(대변형·탄성) / 취성 한계 초과 / 연성 항복 초과(δ_p, 극한까지 남은 %) / 80~100% / 40~80% / <40%. 처짐>L/10 이면 "(근사)" 꼬리.

### 단면계수
- σ-ε 카드 아래 `.formula-strip`: "σ = M / S   S = b·h²/6 = 2,352 cm³"(`#valS`, 두께 변경·파괴 임계 단면 반영). 선도 캔버스 폭 ≥300px 일 때 오른쪽 아래에 같은 식을 작은 박스로도 그림.
- 카드 클릭/Enter → `#conceptModal`: 휨응력 σ=My/I → σ_max=M/S, S=I/(h/2)=bh²/6 유도, 단면·응력분포 SVG, 현재 b·h·I·S 와 M→σ 실계산(`#conceptLive`), h²·h³ 설명, 선도 읽는 법. Esc/배경/확인으로 닫힘.
- 사용자가 붙여넣은 개념 본문(Pasted text #5)은 세션에 전달되지 않아 표준 내용으로 작성함(사용자에게 알릴 예정).

## E2E 추가/교체
- 3: coinBadge → scoreBadge, first 미션. 17: 미션 12개 기준(brittle/residual/rubber/lever/thick/first/yield 완료, cnt "n / 12", score = 점수합, 배지 "1,050 점").
- 32(교체): 배치 검사 — 미션 열(왼쪽, 높이>50vh, 하단 바 위), 오른쪽 열(바닥까지), 도크 왼쪽+부재 오른쪽, 종료 버튼 오른쪽 맨 아래, σ-ε 캔버스 ≥300×150, 장면 영역이 열·바와 안 겹침.
- 39(신규): 대사 5상태(빈/탄성/소성/잔류/파괴) 문장·클래스·아바타. 40: 개념 모달 열림·learn·S 값·σ=M/S 실계산·Esc·두께 40cm → S 4,800. 41: 점수=합, 진행바, 종료 모달, 랭킹 등록/순위/HTML 이스케이프, 처음부터. 42: 390px 에뮬레이션 — 버튼이 setupRow 로 이동, 미션 접힘, 고정단 안 가림, 가로 넘침 없음, 복귀.
- 0: 실행 시작 때 localStorage.clear()+resetMissions() (이전 실행 저장분 제거).

## 검사 부탁 (코드 수정 금지)
- 요청 1~5 충족 여부와 배치 겹침/가림(5해상도 스크린샷), 좁은 화면에서 버튼 DOM 이동의 부작용(이벤트 핸들러·ID), 점수/미션 판정의 오탐·누락(특히 move·iso·yield 조건, localStorage 복원), 랭킹 저장/정렬/이스케이프, 대사 문장의 역학적 정확성(용어·수치), 개념 페이지 식의 정확성, 기존 역학·이동·파괴 회귀. 최종 판정 3줄. 검사기 폴더 review_14.md 에 저장.
