# run_e2e_test.py
import asyncio
import http.server
import json
import os
import subprocess
import threading
import time
import urllib.request
import websockets

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9333
HTTP_PORT = 8089
TEMP_PROFILE = os.environ.get("E2E_PROFILE", os.path.abspath(".chrome_test_profile"))
SHOT_DIR = os.environ.get("E2E_SHOTS", os.path.abspath("e2e_shots"))
PAGE = os.environ.get("E2E_PAGE", "index.html")   # 번외 파일 검사: E2E_PAGE=index_plus.html
os.makedirs(SHOT_DIR, exist_ok=True)

def run_http_server():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(("127.0.0.1", HTTP_PORT), handler)
    httpd.serve_forever()

EVENTS = []

async def send_cmd(ws, msg_id, method, params=None):
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        resp = await ws.recv()
        data = json.loads(resp)
        if data.get("id") == msg_id:
            return data
        if data.get("method") in ("Runtime.exceptionThrown", "Runtime.consoleAPICalled", "Log.entryAdded"):
            EVENTS.append(data)

async def ev(ws, msg_id, expr):
    res = await send_cmd(ws, msg_id, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
    r = res["result"]
    if "exceptionDetails" in r:
        raise AssertionError(f"JS error evaluating {expr!r}: {r['exceptionDetails']}")
    return r["result"].get("value")

async def shot(ws, msg_id, name):
    import base64
    res = await send_cmd(ws, msg_id, "Page.captureScreenshot", {"format": "png"})
    out = os.path.join(SHOT_DIR, name)
    with open(out, "wb") as f:
        f.write(base64.b64decode(res["result"]["data"]))
    print(f"  screenshot -> {out}")


DRAG_POS_JS = """(() => {
    const r = document.getElementById('spawnCow').getBoundingClientRect();
    const v = new THREE.Vector3(3.0, 0.15, 0).project(camera);
    return JSON.stringify({sx: r.left + r.width/2, sy: r.top + r.height/2,
        tx: (v.x + 1) / 2 * innerWidth, ty: (1 - v.y) / 2 * innerHeight});
})()"""

LOAD_POS_JS = """(() => {
    const c = loadsOnBeam()[0]; const b = new THREE.Box3().setFromObject(c.mesh);
    const v = b.getCenter(new THREE.Vector3()).project(camera);
    return JSON.stringify({x: (v.x + 1) / 2 * innerWidth, y: (1 - v.y) / 2 * innerHeight});
})()"""

async def click_mat(ws, msg_id, mat):
    await ev(ws, msg_id, "document.querySelector('button[data-mat=\"" + mat + "\"]').click(); 0")
    await asyncio.sleep(0.2)

async def main():
    # Start HTTP server in a thread
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()
    print(f"HTTP server started at http://127.0.0.1:{HTTP_PORT}")

    print(f"Starting Chrome headless on port {PORT}...")
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={TEMP_PROFILE}",
        "--window-size=1440,900",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--no-sandbox",
        f"http://127.0.0.1:{HTTP_PORT}/{PAGE}"
    ])

    try:
        # Wait for Chrome debug endpoint
        ws_url = None
        for _ in range(20):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as resp:
                    tabs = json.loads(resp.read().decode())
                    print("Chrome targets:", [(t.get('title'), t.get('url')) for t in tabs])
                    # find the target that has index.html or is a page
                    page_tabs = [t for t in tabs if t.get("type") == "page" and PAGE in t.get("url", "")]
                    if not page_tabs:
                        page_tabs = [t for t in tabs if t.get("type") == "page"]
                    if page_tabs:
                        ws_url = page_tabs[0]["webSocketDebuggerUrl"]
                        break
            except Exception:
                await asyncio.sleep(0.5)

        assert ws_url, "Could not obtain WebSocket debugger URL"
        print(f"Connected to Chrome: {ws_url}")

        async with websockets.connect(ws_url) as ws:
            await send_cmd(ws, 1, "Runtime.enable")
            await send_cmd(ws, 2, "Page.enable")
            await send_cmd(ws, 3, "Log.enable")
            # 이벤트 수신을 켠 상태에서 다시 로드해 초기화 단계 오류까지 잡는다
            await send_cmd(ws, 4, "Page.reload", {"ignoreCache": True})
            await asyncio.sleep(3.0)

            title = await ev(ws, 5, "document.title")
            print(f"Page title: {title}")
            assert "버텨라" in title, f"Unexpected title: {title}"
            assert "길건너" not in await ev(ws, 6, "document.body.innerText"), "길건너 문구가 남아있음"

            # 0. 이전 실행에서 저장된 미션·점수·랭킹 지우고 깨끗한 상태로
            await ev(ws, 6, "localStorage.clear(); resetMissions(); 0")
            await ev(ws, 7, "document.getElementById('btnStart').click(); 0")   # 표지 → 게임 시작
            await asyncio.sleep(0.7)
            assert await ev(ws, 6001, "score") == 0

            # 1. 보가 실제로 씬에 있고 보이는지 (가장 큰 문제였던 항목)
            info = await ev(ws, 7, "JSON.stringify({vis: beamGroup.visible, n: beamSegments.length, inScene: scene.children.includes(beamGroup), x0: beamSegments[0].position.x, xN: beamSegments[beamSegments.length-1].position.x})")
            info = json.loads(info)
            print(f"Beam: {info}")
            assert info["vis"] and info["inScene"] and info["n"] == await ev(ws, 7001, "NUM_SEGS")
            assert info["xN"] > 5.5, "세그먼트가 배치되지 않음 (초기화 실패)"
            await shot(ws, 8, "01_initial.png")

            # 1-b. 가이드 모달 열기/닫기 (사용자 보고: 가이드가 안 열림)
            await ev(ws, 9, "document.getElementById('btnHelp').click()")
            await asyncio.sleep(0.4)
            assert await ev(ws, 9001, "helpModal.classList.contains('open') && getComputedStyle(helpModal).display === 'flex'") is True, "가이드가 열리지 않음"
            await shot(ws, 9002, "01b_guide.png")
            await ev(ws, 9003, "document.getElementById('btnCloseHelp').click()")
            await asyncio.sleep(0.2)
            assert await ev(ws, 9004, "!helpModal.classList.contains('open')") is True, "가이드가 닫히지 않음"
            print("Guide modal open/close OK")
            assert await ev(ws, 9005, "!document.getElementById('firstHint').classList.contains('hidden')") is True, "첫 사용 안내가 보여야 함"

            # 2. 재료를 바꿔도 보가 계속 보이는지
            for i, mat in enumerate(["high_steel", "concrete", "wood", "rubber", "mild_steel"]):
                await ev(ws, 10 + i, f"document.querySelector('button[data-mat=\"{mat}\"]').click()")
                await asyncio.sleep(0.2)
                vis = await ev(ws, 20 + i, "beamGroup.visible && beamSegments[NUM_SEGS - 1].position.x > 5.5")
                col = await ev(ws, 30 + i, "beamSegments[0].material[0].color.getHex() === currentMat.color")
                print(f"  material {mat}: visible={vis}, colorApplied={col}")
                assert vis and col, f"{mat} 선택 후 보가 보이지 않음"
                if mat == "concrete":
                    await shot(ws, 40, "02_concrete.png")

            # 3. 하중물 스폰 (돼지 150, 소 500, 작업자 75, 트랙터 1500)
            for i, sid in enumerate(["spawnPig", "spawnCow", "spawnWorker", "spawnTractor"]):
                await ev(ws, 50 + i, f"document.getElementById('{sid}').click()")
                await asyncio.sleep(0.2)
            st = json.loads(await ev(ws, 60, "JSON.stringify({people: valPeople.textContent, score: scoreBadge.textContent, first: missions.first, defl: valDeflection.textContent, stress: valStress.textContent})"))
            print(f"After 4 loads: {st}")
            assert await ev(ws, 61001, "document.getElementById('firstHint').classList.contains('hidden')") is True, "첫 하중 후 안내가 사라져야 함"
            assert "4 개" in st["people"] and "2,225 kg" in st["people"], st
            assert st["first"] and "50 점" in st["score"], st

            # 4. 중장비 5,000 kg
            await ev(ws, 61, "document.getElementById('spawnExcavator').click()")
            await asyncio.sleep(1.0)
            st = json.loads(await ev(ws, 62, "JSON.stringify({people: valPeople.textContent, defl: valDeflection.textContent, stress: valStress.textContent, badge: statusBadge.textContent})"))
            print(f"After excavator: {st}")
            assert "7,225 kg" in st["people"]
            assert float(st["defl"].replace(" cm", "")) > 1.0
            await shot(ws, 63, "03_loaded_steel.png")

            # 5. 전부 제거
            await ev(ws, 70, "document.getElementById('btnUnload').click()")
            await asyncio.sleep(0.3)
            st = json.loads(await ev(ws, 71, "JSON.stringify({people: valPeople.textContent, defl: valDeflection.textContent})"))
            print(f"After unload: {st}")
            assert "0 개" in st["people"]

            # 6. 콘크리트 취성 파괴 (적재블록 500 kg 하나면 인장강도 초과)
            await ev(ws, 80, "document.querySelector('button[data-mat=\"concrete\"]').click()")
            await asyncio.sleep(0.2)
            await ev(ws, 81, "document.getElementById('spawnCow').click()")
            await asyncio.sleep(0.8)
            st = json.loads(await ev(ws, 82, "JSON.stringify({badge: statusBadge.textContent, isBroken, people: valPeople.textContent, defl: currentDeflection, lbl: lblYield.textContent})"))
            print(f"Concrete: {st}")
            assert st["isBroken"] is True and ("파괴" in st["badge"] or "붕괴" in st["badge"])
            # 파괴 순간의 하중/처짐이 HUD에 남아 있어야 함 (review_01 P1-7)
            assert "1 개" in st["people"] and "임계" in st["people"] and st["defl"] > 0, st
            assert "균열" in st["lbl"], "콘크리트는 '항복강도'가 아니라 균열강도로 표기"
            await shot(ws, 83, "04_concrete_broken.png")

            # 7. 시편 교체
            await ev(ws, 90, "document.getElementById('btnReset').click()")
            await asyncio.sleep(0.3)
            assert await ev(ws, 91, "!isBroken && beamGroup.visible") is True
            print("Reset OK")

            # 8. 두께 슬라이더: 물리값 + 3D 스케일
            await ev(ws, 100, "const sl=document.getElementById('beamHSlider'); sl.value='0.20'; sl.dispatchEvent(new Event('input')); 0")
            st = json.loads(await ev(ws, 101, "JSON.stringify({h: BEAM_H, sy: beamSegments[0].scale.y, by: bracket.scale.y})"))
            print(f"Slider: {st}")
            assert st["h"] == 0.20 and abs(st["sy"] - 0.20 / 0.28) < 1e-6 and abs(st["by"] - 0.20 / 0.28) < 1e-6
            await ev(ws, 102, "const sl2=document.getElementById('beamHSlider'); sl2.value='0.28'; sl2.dispatchEvent(new Event('input')); 0")

            # 9. 수치 정확도: 연강, 적재블록 500kg @ x=3.0m → M = 4905*3 = 14.715 kN·m, σ = M/S
            await click_mat(ws, 110, "mild_steel")
            await ev(ws, 111, "spawnCharacterAt('cow', 3.0); 0")
            st = json.loads(await ev(ws, 112, "JSON.stringify({M: currentMaxMoment, s: currentMaxStress, d: currentDeflection})"))
            b, h, L = 0.18, 0.28, 6.0
            S = b * h * h / 6; I = b * h ** 3 / 12; P = 500 * 9.81; E = 200e9
            M_exp = P * 3.0 / 1000
            s_exp = P * 3.0 / S / 1e6
            d_exp = (P * 3.0 ** 2 * (3 * L - 3.0) / (6 * E * I)) * 100
            print(f"Numeric: got {st}, expected M={M_exp:.3f} s={s_exp:.3f} d={d_exp:.4f}cm")
            assert abs(st["M"] - M_exp) < 1e-6 and abs(st["s"] - s_exp) < 1e-6
            assert abs(st["d"] - d_exp) / d_exp < 0.01, "tip deflection differs from theory by >1%"

            # 10. 소성 이력: 재계산을 반복해도 영구처짐이 늘지 않아야 함
            await ev(ws, 120, "resetExperiment(); spawnCharacterAt('excavator', 5.9); spawnCharacterAt('excavator', 5.0); spawnCharacterAt('excavator', 4.2); 0")
            st = json.loads(await ev(ws, 121, "JSON.stringify({s: currentMaxStress, p: currentPermanent, broken: isBroken, badge: statusBadge.textContent})"))
            print(f"Plastic state: {st}")
            assert not st["broken"] and st["s"] > 275 and st["p"] > 0, st
            p_before = st["p"]
            p_after = await ev(ws, 122, "for (let i=0;i<50;i++) calculateBeamPhysics(); currentPermanent")
            print(f"  permanent before={p_before:.3f}cm after 50 recalcs={p_after:.3f}cm")
            assert abs(p_after - p_before) < 1e-9, "permanent deflection grows on recalculation (ratchet bug)"
            await shot(ws, 123, "05_plastic_loaded.png")
            await ev(ws, 124, "document.getElementById('btnUnload').click()")
            await asyncio.sleep(0.4)
            st = json.loads(await ev(ws, 125, "JSON.stringify({p: currentPermanent, d: currentDeflection, badge: statusBadge.textContent, cls: statusBadge.className})"))
            print(f"After unload (plastic): {st}")
            assert st["p"] > 0 and abs(st["d"] - st["p"]) < 1e-6 and "residual" in st["cls"], st
            # 잔류 처짐을 test_mechanics.py 의 정밀 적분 기준값(12.030 cm)과 비교
            assert abs(st["p"] - 12.030) / 12.030 < 0.005, f"잔류 처짐 {st['p']:.3f} cm 가 정밀해 12.030 cm 와 0.5% 이상 차이"
            # 정면 시점에서도 보이도록 앞면 윗부분 주황 띠로 소성 흔적 표시 (고정단 쪽만)
            sc = json.loads(await ev(ws, 1251, "JSON.stringify([beamSegments[0].userData.scar.visible, beamSegments[NUM_SEGS - 1].userData.scar.visible])"))
            assert sc == [True, False], sc
            await shot(ws, 126, "06_plastic_residual.png")

            # 11. 고무: 크게 휘지만 하중 제거 시 완전 복원
            await click_mat(ws, 130, "rubber")
            await ev(ws, 131, "document.getElementById('spawnWorker').click(); document.getElementById('spawnWorker').click(); 0")
            await asyncio.sleep(0.3)
            st = json.loads(await ev(ws, 132, "JSON.stringify({d: currentDeflection, broken: isBroken, scale: scaleBadge.textContent})"))
            print(f"Rubber loaded: {st}")
            assert st["d"] > 30 and not st["broken"] and "×1" in st["scale"], st
            await shot(ws, 133, "07_rubber.png")
            await ev(ws, 134, "document.getElementById('btnUnload').click()")
            st = json.loads(await ev(ws, 135, "JSON.stringify({d: currentDeflection, p: currentPermanent})"))
            print(f"Rubber unloaded: {st}")
            assert st["d"] < 1e-9 and st["p"] < 1e-9

            # 12. 실제 마우스 드래그&드롭 (도크 → 보 x≈3m 지점)
            await click_mat(ws, 140, "mild_steel")
            pos = json.loads(await ev(ws, 141, DRAG_POS_JS))

            async def mouse(i, typ, x, y, buttons=1):
                await send_cmd(ws, i, "Input.dispatchMouseEvent", {"type": typ, "x": x, "y": y, "button": "left", "buttons": buttons, "clickCount": 1})

            await mouse(150, "mouseMoved", pos["sx"], pos["sy"], 0)
            await mouse(151, "mousePressed", pos["sx"], pos["sy"])
            for k in range(1, 11):
                fx = pos["sx"] + (pos["tx"] - pos["sx"]) * k / 10
                fy = pos["sy"] + (pos["ty"] - pos["sy"]) * k / 10
                await mouse(160 + k, "mouseMoved", fx, fy)
                await asyncio.sleep(0.03)
            cap = await ev(ws, 175, "document.querySelector('#dragGhost .cap').textContent + ' | preview=' + previewMarker.visible")
            print(f"  drag caption: {cap}")
            await shot(ws, 176, "08_dragging.png")
            await mouse(177, "mouseReleased", pos["tx"], pos["ty"], 0)
            await asyncio.sleep(0.3)
            st = json.loads(await ev(ws, 178, "JSON.stringify(loadsOnBeam().map(c => [c.type, c.xPos]))"))
            print(f"  after drop: {st}")
            assert len(st) == 1 and st[0][0] == "cow" and abs(st[0][1] - 3.0) < 0.35, st
            assert "x = " in cap and "preview=true" in cap

            # 13. 3D 화면에서 하중물 클릭 → 제거
            tp = json.loads(await ev(ws, 180, LOAD_POS_JS))
            await mouse(181, "mouseMoved", tp["x"], tp["y"], 0)
            await mouse(182, "mousePressed", tp["x"], tp["y"])
            await mouse(183, "mouseReleased", tp["x"], tp["y"], 0)
            await asyncio.sleep(0.3)
            n = await ev(ws, 184, "loadsOnBeam().length")
            sel = await ev(ws, 1840, "selectedLoadId !== null")
            print(f"  loads after clicking it in 3D: {n}, selected={sel}")
            assert n == 1 and sel is True, "3D click should select the load, not remove it"
            await send_cmd(ws, 185, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Delete", "code": "Delete", "windowsVirtualKeyCode": 46})
            await send_cmd(ws, 186, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Delete", "code": "Delete", "windowsVirtualKeyCode": 46})
            n = await ev(ws, 187, "loadsOnBeam().length")
            assert n == 0, "Delete should remove the selected load"

            # 14. 변형 확대 배율 버튼
            await ev(ws, 190, "spawnCharacterAt('excavator', 5.5); document.querySelector('#scaleControl button[data-scale=\"1\"]').click(); 0")
            y1 = await ev(ws, 191, "beamSegments[NUM_SEGS - 1].position.y")
            await ev(ws, 192, "document.querySelector('#scaleControl button[data-scale=\"50\"]').click(); 0")
            y50 = await ev(ws, 193, "beamSegments[NUM_SEGS - 1].position.y")
            sb = await ev(ws, 194, "scaleBadge.textContent")
            print(f"  tip y x1={y1:.4f}, x50={y50:.4f}, badge='{sb}'")
            assert y50 < y1 * 10 and "×50" in sb
            await ev(ws, 195, "document.querySelector('#scaleControl button[data-scale=\"auto\"]').click(); 0")
            await shot(ws, 196, "09_final.png")

            # 15. 재료 전환 시 같은 하중 유지 (재료 비교 실험)
            await ev(ws, 200, "resetExperiment(); spawnCharacterAt('worker', 5.0); spawnCharacterAt('pig', 4.0); 0")
            await click_mat(ws, 201, "wood")
            st = json.loads(await ev(ws, 202, "JSON.stringify({mat: currentMatKey, loads: loadsOnBeam().map(c => [c.type, c.xPos]), M: currentMaxMoment})"))
            print(f"Material switch keeps loads: {st}")
            assert st["mat"] == "wood" and sorted(st["loads"]) == [["pig", 4.0], ["worker", 5.0]], st
            assert abs(st["M"] - (75 * 9.81 * 5.0 + 150 * 9.81 * 4.0) / 1000) < 1e-9

            # 16. 반복 실험 후 GPU 리소스 누수 점검 (geometry 수가 계속 늘지 않아야 함)
            g0 = await ev(ws, 210, "renderer.info.memory.geometries")
            for k in range(3):
                await ev(ws, 211 + k, "for (const t of ['excavator','tractor','cow','worker','pig']) document.getElementById({excavator:'spawnExcavator',tractor:'spawnTractor',cow:'spawnCow',worker:'spawnWorker',pig:'spawnPig'}[t]).click(); document.getElementById('btnReset').click(); 0")
                await asyncio.sleep(0.4)
            g1 = await ev(ws, 220, "renderer.info.memory.geometries")
            print(f"  geometries before={g0} after 3 cycles={g1}")
            assert g1 <= g0 + 5, "geometry leak"

            # 17. 미션: 앞선 시나리오로 brittle/residual/rubber 완료, 여기서 lever/thick 완료
            await click_mat(ws, 230, "mild_steel")
            await ev(ws, 231, "resetExperiment(); spawnCharacterAt('excavator', 1.5); spawnCharacterAt('excavator', 5.5); 0")
            await ev(ws, 232, "resetExperiment(); spawnCharacterAt('excavator', 5.9); spawnCharacterAt('excavator', 5.0); spawnCharacterAt('excavator', 4.2); 0")
            await ev(ws, 233, "const s3=document.getElementById('beamHSlider'); s3.value='0.32'; s3.dispatchEvent(new Event('input')); 0")
            st = json.loads(await ev(ws, 234, "JSON.stringify({m: missions, cnt: missionCnt.textContent, s: currentMaxStress, score, pts: MISSIONS.filter(x => missions[x.key]).reduce((a, x) => a + x.pts, 0), badge: scoreBadge.textContent})"))
            print(f"Missions: {st}")
            assert all(st["m"][k] for k in ("brittle", "residual", "rubber", "lever", "thick", "first", "yield")), st
            n_done = sum(1 for v in st["m"].values() if v)
            assert st["cnt"] == f"{n_done} / 12" and st["score"] == st["pts"] > 0 and f"{st['score']:,} 점" in st["badge"], st
            await asyncio.sleep(1.2)
            await shot(ws, 235, "10_missions_done.png")
            await ev(ws, 236, "const s4=document.getElementById('beamHSlider'); s4.value='0.28'; s4.dispatchEvent(new Event('input')); 0")

            # 18. σ-ε 곡선 함수: 연속성/역함수 (review_02 P2-9)
            st = json.loads(await ev(ws, 240, """JSON.stringify(Object.entries(MATERIALS).map(([k, m]) => {
                const e1 = m.ey * (1 - 1e-9), e2 = m.ey * (1 + 1e-9);
                const jumpY = Math.abs(stressAtStrain(m, e2) - stressAtStrain(m, e1));
                let invErr = 0;
                for (let i = 1; i < 20; i++) { const s = m.fu * i / 20; invErr = Math.max(invErr, Math.abs(stressAtStrain(m, strainAtStress(m, s)) - s)); }
                return [k, jumpY, invErr, stressAtStrain(m, m.eu)];
            }))"""))
            print(f"Curve checks [mat, jump@ey, inverse err, σ(εu)]: {st}")
            for k, jump, inv, s_eu in st:
                assert jump < 1e-3 and inv < 1e-6, (k, jump, inv)
            fu_map = {"mild_steel": 410, "high_steel": 620, "concrete": 3.5, "wood": 42, "rubber": 60}
            for k, jump, inv, s_eu in st:
                assert abs(s_eu - fu_map[k]) < 1e-9, (k, s_eu)

            # 19. 실제 처짐은 각도 상한과 무관 (review_02 P1-1): 고무 + 500kg @ 5.69m 를 선형 이론과 비교
            await click_mat(ws, 250, "rubber")
            await ev(ws, 251, "resetExperiment(); spawnCharacterAt('cow', 5.69); 0")
            d = await ev(ws, 252, "currentDeflection")
            P, a = 500 * 9.81, 5.69
            d_lin = P * a ** 2 * (3 * L - a) / (6 * 150e6 * I) * 100
            badge = await ev(ws, 253, "valDeflection.textContent + ' | ' + scaleBadge.textContent")
            print(f"Rubber 500kg: got {d:.1f} cm, linear theory {d_lin:.1f} cm | {badge}")
            assert abs(d - d_lin) / d_lin < 0.01 and "⚠" in badge and "근사" in badge

            # 20. 연성 파괴: 최종 형상 후 파단 + BMD/목록 스냅샷 (review_02 P1-2,3,5)
            await click_mat(ws, 260, "mild_steel")
            await ev(ws, 261, "resetExperiment(); for (let i=0;i<5;i++) spawnCharacterAt('excavator', 5.9 - i*0.9); 0")
            st = json.loads(await ev(ws, 262, "JSON.stringify({broken: isBroken, mode: failureMode, snap: failSnap && failSnap.loads.length, list: loadList.innerText, eps: rootStrainNow, eu: currentMat.eu, perm: currentPermanent})"))
            print(f"Ductile failure: broken={st['broken']} mode={st['mode']} snapLoads={st['snap']} eps={st['eps']} perm={st['perm']:.1f}")
            assert st["broken"] and st["mode"] == "ductile" and st["snap"] == 5
            assert "임계 순간" in st["list"] and abs(st["eps"] - st["eu"]) < 1e-12 and st["perm"] > 0
            await asyncio.sleep(0.6)
            await shot(ws, 263, "11_ductile_failure.png")

            # 21. 재료 전환 중 조기 파괴 → 안내가 실제 적용 개수와 일치 (review_02 P1-6)
            await ev(ws, 270, "resetExperiment(); spawnCharacterAt('excavator', 5.5); spawnCharacterAt('excavator', 4.5); 0")
            await click_mat(ws, 271, "concrete")
            st = json.loads(await ev(ws, 272, "JSON.stringify({broken: isBroken, toast: document.getElementById('toast').textContent, snap: failSnap && failSnap.count})"))
            print(f"Switch to concrete with 2 heavies: {st}")
            assert st["broken"] and st["snap"] == 1 and "1번째" in st["toast"], st
            await click_mat(ws, 273, "mild_steel")
            n2 = await ev(ws, 274, "loadsOnBeam().length")
            print(f"  back to mild steel: loads restored = {n2}")
            assert n2 == 2, "중간 파괴로 못 올린 하중이 재료 복귀 시 유실됨"

            # 22. 두께 변경 = 새 시편 (소성 이력이 새 두께와 일관) (review_02 P1-4)
            await click_mat(ws, 280, "mild_steel")
            await ev(ws, 281, "resetExperiment(); spawnCharacterAt('excavator', 5.9); spawnCharacterAt('excavator', 5.0); spawnCharacterAt('excavator', 4.2); 0")
            await ev(ws, 282, "const s5=document.getElementById('beamHSlider'); s5.value='0.27'; s5.dispatchEvent(new Event('input')); 0")
            p_slider = await ev(ws, 283, "currentPermanent")
            p_fresh = await ev(ws, 284, "resetExperiment(); spawnCharacterAt('excavator', 5.9); spawnCharacterAt('excavator', 5.0); spawnCharacterAt('excavator', 4.2); currentPermanent")
            print(f"Thickness change: after slider {p_slider:.4f} cm vs fresh specimen {p_fresh:.4f} cm")
            assert abs(p_slider - p_fresh) < 1e-9
            await ev(ws, 285, "const s8=document.getElementById('beamHSlider'); s8.value='0.28'; s8.dispatchEvent(new Event('input')); 0")

            # 23. 파괴 임계점 일치 (review_03 P1-1): 콘크리트 500kg@5.69 → σ=σ_u, ε=ε_u, 처짐 = λ × 전체하중 처짐
            await click_mat(ws, 300, "concrete")
            await ev(ws, 301, "resetExperiment(); spawnCharacterAt('cow', 5.69); 0")
            st = json.loads(await ev(ws, 302, "JSON.stringify({b: isBroken, s: currentMaxStress, e: rootStrainNow, eu: currentMat.eu, d: currentDeflection, lam: failSnap.crit.alpha, M: currentMaxMoment, note: critNote.textContent, vis: critNote.style.display})"))
            S_ = 0.18 * 0.28 ** 2 / 6; I_ = 0.18 * 0.28 ** 3 / 12
            Pc = 500 * 9.81
            lam = 3.5e6 * S_ / (Pc * 5.69)
            d_crit = lam * Pc * 5.69 ** 2 * (3 * 6.0 - 5.69) / (6 * 25e9 * I_) * 100
            print(f"Concrete critical: {st} | expected lambda={lam:.4f} d={d_crit:.5f}cm")
            assert st["b"] and abs(st["s"] - 3.5) < 1e-9 and abs(st["e"] - st["eu"]) < 1e-12
            assert abs(st["lam"] - lam) < 1e-9 and abs(st["d"] - d_crit) / d_crit < 0.01 and st["vis"] == "block" and "%" in st["note"]

            # 24. 두께 슬라이더 연속 조작 중 중간 파괴 → 하중 유실 없음 (review_03 P1-2)
            await click_mat(ws, 310, "mild_steel")
            await ev(ws, 311, "const a1=document.getElementById('beamHSlider'); a1.value='0.15'; a1.dispatchEvent(new Event('input')); a1.dispatchEvent(new Event('change')); 0")
            await ev(ws, 312, "resetExperiment(); spawnCharacterAt('cow', 2.6); spawnCharacterAt('tractor', 3.6); spawnCharacterAt('tractor', 4.6); spawnCharacterAt('tractor', 5.6); spawnCharacterAt('excavator', 5.0); 0")
            st0 = json.loads(await ev(ws, 313, "JSON.stringify({b: isBroken, n: failSnap ? failSnap.count : loadsOnBeam().length})"))
            for i, hv in enumerate([0.16, 0.17, 0.19, 0.22, 0.26, 0.30, 0.35]):
                await ev(ws, 314 + i, f"(() => {{ const a2=document.getElementById('beamHSlider'); a2.value='{hv}'; a2.dispatchEvent(new Event('input')); }})(); 0")
            await ev(ws, 322, "document.getElementById('beamHSlider').dispatchEvent(new Event('change')); 0")
            st = json.loads(await ev(ws, 323, "JSON.stringify({b: isBroken, loads: loadsOnBeam().map(c => c.type).sort()})"))
            print(f"Slider sweep: start={st0} end={st}")
            assert st0["b"] is True, "시작 상태에서 파괴되어야 중간 파괴 경로를 검증할 수 있음"
            assert not st["b"] and st["loads"] == ["cow", "excavator", "tractor", "tractor", "tractor"], st
            await ev(ws, 324, "const a3=document.getElementById('beamHSlider'); a3.value='0.28'; a3.dispatchEvent(new Event('input')); a3.dispatchEvent(new Event('change')); 0")

            # 25. 고무 미션: 다른 재료를 거쳐 오면 인정 안 됨 (review_03 P1-3)
            await ev(ws, 330, "missions.rubber = false; 0")
            await click_mat(ws, 331, "rubber")
            await ev(ws, 332, "resetExperiment(); spawnCharacterAt('cow', 5.5); 0")
            await click_mat(ws, 333, "mild_steel")
            await ev(ws, 334, "document.getElementById('btnUnload').click(); 0")
            await click_mat(ws, 335, "rubber")
            st = json.loads(await ev(ws, 336, "JSON.stringify({done: missions.rubber, flag: missionFlags.rubberBig})"))
            print(f"Rubber mission after detour: {st}")
            assert st["done"] is False and st["flag"] is False
            await ev(ws, 337, "spawnCharacterAt('cow', 5.5); document.getElementById('btnUnload').click(); 0")
            st = json.loads(await ev(ws, 338, "JSON.stringify({done: missions.rubber, note: missionNote.textContent, toast: document.getElementById('toast').textContent})"))
            print(f"Rubber mission proper: {st}")
            assert st["done"] is True and "탄성" in st["note"] and "미션 완료" not in st["toast"]   # (review_03 P1-4) 카드 안 안내

            # 26. 목재 용어 (review_03 P1-5): σ_pl 초과·σ_u 미만
            await click_mat(ws, 340, "wood")
            await ev(ws, 341, "resetExperiment(); spawnCharacterAt('tractor', 5.0); 0")
            st = json.loads(await ev(ws, 342, "JSON.stringify({s: currentMaxStress, badge: statusBadge.textContent, bar: stressBarText.textContent, gauge: gaugeTitle.textContent, hl: rowPlastic.classList.contains('highlight')})"))
            print(f"Wood terms: {st}")
            assert 30 < st["s"] < 42 and "비례한도" in st["badge"] and "비례한도" in st["bar"] and "σ_pl" in st["gauge"] and not st["hl"], st
            await shot(ws, 343, "12_wood_terms.png")

            # 27. 순차 재하 임계 보간 (review_04 P1-1,2): 작업자 75kg@5.0 버팀 → 적재블록 500kg@5.69 추가 시 파괴
            await click_mat(ws, 350, "concrete")
            await ev(ws, 351, "resetExperiment(); spawnCharacterAt('worker', 5.0); spawnCharacterAt('cow', 5.69); 0")
            st = json.loads(await ev(ws, 352, """JSON.stringify({b: isBroken, crit: failSnap.crit, loads: failSnap.loads.map(c => [c.type, c.weight, c.xPos]),
                M: currentMaxMoment, d: currentDeflection, people: valPeople.textContent, sumList: loadList.querySelector('.load-sum span:last-child').textContent,
                note: critNote.textContent})"""))
            Mu = 3.5e6 * S_
            alpha = (Mu - 75 * 9.81 * 5.0) / (500 * 9.81 * 5.69)
            w = {t_: w_ for t_, w_, x_ in st["loads"]}
            # 기대 처짐: 작업자 75kg 전부 + 블록 α×500kg 의 선형 끝단 처짐
            def tipd(P, a, E, I): return P * a ** 2 * (3 * 6.0 - a) / (6 * E * I)
            d_exp = (tipd(75 * 9.81, 5.0, 25e9, I_) + tipd(alpha * 500 * 9.81, 5.69, 25e9, I_)) * 100
            print(f"Sequential critical: alpha={st['crit']['alpha']:.4f} (exp {alpha:.4f}) loads={st['loads']} M={st['M']:.3f} d={st['d']:.4f} (exp {d_exp:.4f})")
            print(f"  people='{st['people']}' listSum={st['sumList']} note='{st['note'][:60]}...'")
            assert st["b"] and st["crit"]["mode"] == "increment" and abs(st["crit"]["alpha"] - alpha) < 1e-9
            assert abs(w["worker"] - 75) < 1e-9 and abs(w["cow"] - 500 * alpha) < 1e-6
            assert abs(st["M"] - Mu / 1000) < 1e-9 and abs(float(st["sumList"]) - Mu / 1000) < 0.05
            assert abs(st["d"] - d_exp) / d_exp < 0.01
            await shot(ws, 353, "13_sequential_critical.png")

            # 28. 바닥 접촉 구간도 화면 길이 보존 (review_04 P2-1)
            await click_mat(ws, 360, "rubber")
            await ev(ws, 361, "resetExperiment(); spawnCharacterAt('cow', 3.0); spawnCharacterAt('cow', 5.5); 0")
            st = json.loads(await ev(ws, 362, """(() => { let worst = 0, touch = 0;
                for (let i = 1; i < visPts.length; i++) {
                  const a = visPts[i-1], b = visPts[i];
                  const len = Math.hypot(b.x - a.x, b.y - a.y), ds = b.s - a.s;
                  if (b.y <= GROUND_Y + 1e-9) touch++;
                  worst = Math.max(worst, Math.abs(len - ds) / (BEAM_L / N_INT));
                }
                return JSON.stringify({worst, touch, total: visPts[visPts.length-1].s}); })()"""))
            print(f"Ground contact polyline: {st}")
            assert st["touch"] > 0 and st["worst"] < 0.02 and abs(st["total"] - 6.0) < 1e-9, st

            # 29. 미션 카드 키보드 접근 + 안내문 수명주기 (review_04 P2-2,3)
            ae0 = await ev(ws, 370, "missionHead.getAttribute('aria-expanded')")
            await ev(ws, 371, "window.__mc = 0; missionHead.addEventListener('click', () => window.__mc++); missionHead.focus(); 0")
            for i_, typ in enumerate(["keyDown", "keyUp"]):
                await send_cmd(ws, 372 + i_, "Input.dispatchKeyEvent", dict({"type": typ, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, **({"text": chr(13)} if typ == "keyDown" else {})))
            await asyncio.sleep(0.2)
            ae1 = await ev(ws, 374, "missionHead.getAttribute('aria-expanded')")
            print("  activeElement:", await ev(ws, 3741, "document.activeElement && document.activeElement.id"), "clicks:", await ev(ws, 3742, "window.__mc"))
            print(f"Mission head via keyboard: aria-expanded {ae0} -> {ae1}")
            assert ae0 != ae1
            await ev(ws, 375, "document.getElementById('missionNote').style.display='block'; 0")
            await click_mat(ws, 376, "mild_steel")
            assert await ev(ws, 377, "document.getElementById('missionNote').style.display") == "none"

            # 30. 단면 감소 파괴 → 하중 100% + 임계 두께 h_cr (review_05 P1)
            await click_mat(ws, 380, "concrete")
            await ev(ws, 381, "resetExperiment(); spawnCharacterAt('worker', 5.0); 0")
            await ev(ws, 382, "(() => { const q=document.getElementById('beamHSlider'); q.value='0.15'; q.dispatchEvent(new Event('input')); q.dispatchEvent(new Event('change')); })(); 0")
            st = json.loads(await ev(ws, 383, "JSON.stringify({b: isBroken, crit: failSnap.crit, d: currentDeflection, s: currentMaxStress, H: BEAM_H, badge: statusBadge.textContent, w: failSnap.loads.map(c => c.weight)})"))
            Mw = 75 * 9.81 * 5.0
            hcr = (6 * Mw / (0.18 * 3.5e6)) ** 0.5
            Icr = 0.18 * hcr ** 3 / 12
            dcr = 75 * 9.81 * 25.0 * (18.0 - 5.0) / (6 * 25e9 * Icr) * 100
            print(f"Section failure: {st} | expected hcr={hcr:.5f} d={dcr:.4f}")
            assert st["b"] and st["crit"]["mode"] == "section" and abs(st["crit"]["hCr"] - hcr) < 1e-9
            assert abs(st["d"] - dcr) / dcr < 0.01 and abs(st["s"] - 3.5) < 1e-9 and st["H"] == 0.15 and st["w"] == [75]
            assert "h=18.7cm" in st["badge"]
            bmd = json.loads(await ev(ws, 3831, "JSON.stringify({bmd: lastBMD, H: BEAM_H, S: BEAM_S, sy: beamSegments[0].scale.y})"))
            Mu_cr = 3.5e6 * 0.18 * hcr ** 2 / 6 / 1000
            print(f"  section BMD limits: {bmd} | expected Mu(hcr)={Mu_cr:.5f}")
            assert abs(bmd["bmd"]["Mu"] - Mu_cr) < 1e-9 and abs(bmd["S"] - 0.18 * 0.15 ** 2 / 6) < 1e-12   # 전역 단면은 최종값으로 복원
            My_cr = 3.2e6 * 0.18 * hcr ** 2 / 6 / 1000
            assert abs(bmd["bmd"]["My"] - My_cr) < 1e-9, (bmd, My_cr)   # 균열모멘트선도 임계 단면 기준
            assert abs(bmd["sy"] - hcr / 0.28) < 1e-9   # 보 외형도 임계 두께
            await ev(ws, 384, "(() => { const q=document.getElementById('beamHSlider'); q.value='0.28'; q.dispatchEvent(new Event('input')); q.dispatchEvent(new Event('change')); })(); document.getElementById('btnReset').click(); 0")

            # 31. 실제 도크 클릭 경로 + 개별 제거 후 추가에서도 '새 하중' 판별 (review_05 P2-3) — 목재 M_u = 98.8 kN·m
            await click_mat(ws, 390, "wood")
            await ev(ws, 391, "resetExperiment(); document.getElementById('spawnWorker').click(); document.getElementById('spawnPig').click(); 0")
            n_before = await ev(ws, 392, "loadsOnBeam().length")
            await ev(ws, 393, "removeLoadById(loadsOnBeam().find(c => c.type === 'pig').id); document.getElementById('spawnTractor').click(); 0")
            mid = json.loads(await ev(ws, 394, "JSON.stringify({b: isBroken, n: loadsOnBeam().length})"))
            await ev(ws, 395, "document.getElementById('spawnExcavator').click(); 0")
            st = json.loads(await ev(ws, 396, "JSON.stringify({b: isBroken, crit: failSnap && failSnap.crit, loads: failSnap && failSnap.loads.map(c => [c.type, Math.round(c.frac*1e4)/1e4]), M: currentMaxMoment})"))
            print(f"Dock path after removal: before={n_before} mid={mid} -> {st}")
            fr = dict((k, v) for k, v in st["loads"])
            assert n_before == 2 and not mid["b"] and mid["n"] == 2
            assert st["b"] and st["crit"]["mode"] == "increment" and st["crit"]["added"] == ["excavator"]
            assert fr["worker"] == 1.0 and fr["tractor"] == 1.0 and 0 < fr["excavator"] < 1 and abs(st["M"] - 42 * 0.18 * 0.28 ** 2 / 6 * 1000) < 1e-6

            # 32. 장면 구성: 도로·차 없음, 호수·낭떠러지 있음. 배치: 왼쪽 미션 열 / 오른쪽 그래프·상태 열 / 아래 도크+부재 설정 / 종료 버튼은 오른쪽 맨 아래
            st = json.loads(await ev(ws, 400, """(() => { const R = id => document.getElementById(id).getBoundingClientRect().toJSON();
                return JSON.stringify({road: typeof roadCars !== 'undefined', water: scene.children.includes(water), face: cliffFaceX(0),
                curveInPanel: !!curveCanvas.closest('#sidePanel'), bmdInPanel: !!bmdCanvas.closest('#sidePanel'), readoutInPanel: !!document.getElementById('valMoment').closest('#sidePanel'),
                commentaryInPanel: !!document.getElementById('commentaryText').closest('#sidePanel'), matInBottom: !!document.getElementById('matGrid').closest('#bottomBar'),
                sliderInBottom: !!document.getElementById('beamHSlider').closest('#bottomBar'), dockInBottom: !!document.getElementById('spawnExcavator').closest('#bottomBar'),
                endInFoot: !!document.getElementById('btnEnd').closest('#panelFoot'), actionsInFoot: !!document.getElementById('btnUnload').closest('#panelFoot'),
                mission: R('missionPanel'), panel: R('sidePanel'), bottom: R('bottomBar'), dock: R('dockBar'), setup: R('setupBar'), end: R('btnEnd'), curve: R('curveCanvas'), bmd: R('bmdCanvas'),
                chartH: getComputedStyle(curveCanvas).height, W: innerWidth, H: innerHeight, scene: sceneRect()}); })()"""))
            print(f"Scene/layout: road={st['road']} water={st['water']} mission={st['mission']['left']:.0f}-{st['mission']['right']:.0f}x{st['mission']['top']:.0f}-{st['mission']['bottom']:.0f} panel.left={st['panel']['left']:.0f} bottom.top={st['bottom']['top']:.0f} scene={st['scene']}")
            assert not st["road"] and st["water"] and st["face"] == 0
            assert st["curveInPanel"] and st["bmdInPanel"] and st["readoutInPanel"] and st["commentaryInPanel"], st
            assert st["matInBottom"] and st["sliderInBottom"] and st["dockInBottom"] and st["endInFoot"] and st["actionsInFoot"], st
            m, p, b, d, s_, e = st["mission"], st["panel"], st["bottom"], st["dock"], st["setup"], st["end"]
            assert m["left"] < 40 and m["right"] < 320 and m["bottom"] - m["top"] > st["H"] * 0.5 and m["bottom"] < b["top"], (m, b)      # 왼쪽에 세로로 길게, 하단 바 위에서 끝남
            assert p["right"] > st["W"] - 40 and p["bottom"] > st["H"] - 40 and p["left"] > st["W"] * 0.6, p                          # 오른쪽 열, 바닥까지
            assert d["left"] < s_["left"] and d["right"] <= s_["left"] + 1 and d["left"] < st["W"] * 0.3 and b["right"] <= p["left"], (d, s_, p)  # 도크 왼쪽, 그 오른쪽에 부재 설정, 오른쪽 열과 안 겹침
            assert e["bottom"] > st["H"] - 40 and e["left"] >= p["left"] and e["bottom"] - e["top"] > 30, e                             # 종료 버튼은 오른쪽 맨 아래
            assert st["curve"]["bottom"] - st["curve"]["top"] >= 150 and st["curve"]["right"] - st["curve"]["left"] >= 300, st["curve"]  # 그래프 비중 크게
            assert st["bmd"]["top"] > st["curve"]["bottom"] and st["scene"]["l"] >= m["right"] and st["scene"]["r"] <= p["left"] and st["scene"]["b"] <= b["top"], st["scene"]

            # 33. 시점: 기본 단면 → 빈 곳 끌기로 회전 → [단면뷰] 복귀 → [아이소뷰] 에서도 끌어 놓기 동작
            async def wait_view(i):
                for _ in range(60):
                    if await ev(ws, i, "camTween === null"):
                        return
                    await asyncio.sleep(0.1)
                raise AssertionError("시점 전환이 끝나지 않음")
            await click_mat(ws, 402, "mild_steel")
            await ev(ws, 403, "resetExperiment(); 0")
            v0 = json.loads(await ev(ws, 401, "JSON.stringify({sec: isSectionView(), btn: btnView.textContent, cam: camera.position.toArray().map(v => v.toFixed(6)).join(','), bd: backdrop.visible})"))
            assert v0["sec"] and "아이소" in v0["btn"] and v0["bd"], v0
            sky = json.loads(await ev(ws, 404, "(() => { const v = new THREE.Vector3(3, 1.3, 0).project(camera); return JSON.stringify({x: (v.x + 1) / 2 * innerWidth, y: (1 - v.y) / 2 * innerHeight}); })()"))
            await mouse(405, "mouseMoved", sky["x"], sky["y"], 0)
            await mouse(406, "mousePressed", sky["x"], sky["y"])
            for k in range(1, 8):
                await mouse(406 + k, "mouseMoved", sky["x"] + 30 * k, sky["y"] + 12 * k)
            await mouse(415, "mouseReleased", sky["x"] + 210, sky["y"] + 84, 0)
            v1 = json.loads(await ev(ws, 416, "JSON.stringify({az: camAz, el: camEl, btn: btnView.textContent, n: loadsOnBeam().length})"))
            print(f"Orbit by empty drag: {v1}")
            assert abs(v1["az"]) > 0.5 and v1["el"] > 0.2 and "단면" in v1["btn"] and v1["n"] == 0, v1
            await ev(ws, 417, "btnView.click(); 0")
            await wait_view(418)
            v2 = json.loads(await ev(ws, 419, "JSON.stringify({sec: isSectionView(), cam: camera.position.toArray().map(v => v.toFixed(6)).join(','), btn: btnView.textContent})"))
            print(f"Back to section: {v2}")
            assert v2["sec"] and v2["cam"] == v0["cam"] and "아이소" in v2["btn"], (v0, v2)
            await ev(ws, 4191, "btnView.click(); 0")
            await wait_view(4192)
            iso = json.loads(await ev(ws, 4193, """(() => { const out = {az: camAz, el: camEl, bd: backdrop.visible, btn: btnView.textContent};
                for (const [k, x, y] of [['root', 0.4, 0], ['tip', 5.9, 0]]) {
                  const v = new THREE.Vector3(x, y, 0).project(camera);
                  const el = document.elementFromPoint((v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight);
                  out[k] = el && el.id; }
                return JSON.stringify(out); })()"""))
            print(f"Iso view: {iso}")
            assert abs(iso["az"] - 0.785398) < 1e-4 and abs(iso["el"] - 0.62) < 1e-9 and not iso["bd"] and "단면" in iso["btn"]
            assert iso["root"] == "canvas3d" and iso["tip"] == "canvas3d", iso
            # 아이소 시점에서 도크 → 보 x≈4 m 로 실제 드래그
            pos = json.loads(await ev(ws, 4194, DRAG_POS_JS.replace("3.0, 0.15", "4.0, 0.15")))
            await mouse(4195, "mouseMoved", pos["sx"], pos["sy"], 0)
            await mouse(4196, "mousePressed", pos["sx"], pos["sy"])
            for k in range(1, 11):
                await mouse(4196 + k * 10, "mouseMoved", pos["sx"] + (pos["tx"] - pos["sx"]) * k / 10, pos["sy"] + (pos["ty"] - pos["sy"]) * k / 10)
                await asyncio.sleep(0.03)
            await mouse(4310, "mouseReleased", pos["tx"], pos["ty"], 0)
            await asyncio.sleep(0.3)
            st = json.loads(await ev(ws, 4311, "JSON.stringify(loadsOnBeam().map(c => [c.type, c.xPos]))"))
            print(f"  iso drop: {st}")
            assert len(st) == 1 and st[0][0] == "cow" and abs(st[0][1] - 4.0) < 0.35, st
            await shot(ws, 4312, "16_iso_view.png")
            await ev(ws, 4313, "btnView.click(); resetExperiment(); 0")
            await wait_view(4314)
            assert await ev(ws, 4315, "isSectionView()") is True

            # 34. 보 위 하중물을 실제 마우스로 끌어 옮기기 (x=2.0 → 5.5), M 실시간 갱신
            await ev(ws, 420, "missionFlags.leverNear = false; missionFlags.leverFar = false; spawnCharacterAt('excavator', 2.0); 0")
            src = json.loads(await ev(ws, 421, LOAD_POS_JS))
            dst = json.loads(await ev(ws, 422, "(() => { const p = samplePts(visPts, 5.5); const v = new THREE.Vector3(p.x, p.y + 0.5, 0).project(camera); return JSON.stringify({x: (v.x + 1) / 2 * innerWidth, y: (1 - v.y) / 2 * innerHeight}); })()"))
            await mouse(423, "mouseMoved", src["x"], src["y"], 0)
            await mouse(424, "mousePressed", src["x"], src["y"])
            caps = []
            for k in range(1, 13):
                await mouse(424 + k, "mouseMoved", src["x"] + (dst["x"] - src["x"]) * k / 12, src["y"] + (dst["y"] - src["y"]) * k / 12)
                await asyncio.sleep(0.02)
                if k in (4, 12):
                    caps.append(await ev(ws, 440 + k, "document.querySelector('#dragGhost .cap').textContent + ' | M=' + currentMaxMoment.toFixed(2)"))
            await shot(ws, 437, "14_moving_load.png")
            await mouse(438, "mouseReleased", dst["x"], dst["y"], 0)
            await asyncio.sleep(0.3)
            st = json.loads(await ev(ws, 439, "JSON.stringify({loads: loadsOnBeam().map(c => [c.type, c.xPos]), M: currentMaxMoment, near: missionFlags.leverNear, far: missionFlags.leverFar, ghost: dragGhost.style.display})"))
            print(f"Move drag: captions={caps} -> {st}")
            assert len(st["loads"]) == 1 and st["loads"][0][0] == "excavator" and abs(st["loads"][0][1] - 5.5) < 0.3, st
            assert abs(st["M"] - 5000 * 9.81 * st["loads"][0][1] / 1000) < 1e-6
            assert st["near"] and st["far"] and st["ghost"] == "none"
            assert all("x = " in c and "kN·m" in c for c in caps), caps

            # 35. 옮기다 파괴: 콘크리트, 적재블록 x=1.0 → 3.0 으로 옮기면 x_cr = M_u / P 에서 파괴
            await click_mat(ws, 450, "concrete")
            await ev(ws, 451, "resetExperiment(); spawnCharacterAt('cow', 1.0); setLoadX(loadsOnBeam()[0].id, 3.0); 0")
            st = json.loads(await ev(ws, 452, """JSON.stringify({b: isBroken, crit: failSnap && failSnap.crit, M: currentMaxMoment, x: characters[0].xPos,
                listX: failSnap && failSnap.loads[0].xPos, badge: statusBadge.textContent, note: critNote.textContent, Min: failSnap && failSnap.Min})"""))
            Mu_c = 3.5e6 * S_
            xcr = Mu_c / (500 * 9.81)
            print(f"Move failure: {st['crit']} M={st['M']:.4f} x={st['x']:.4f} (exp xcr={xcr:.4f}) badge='{st['badge']}'")
            assert st["b"] and st["crit"]["mode"] == "move" and abs(st["crit"]["xCr"] - xcr) < 1e-9
            assert abs(st["M"] - Mu_c / 1000) < 1e-9 and abs(st["x"] - xcr) < 1e-9 and abs(st["listX"] - xcr) < 1e-9
            assert abs(st["Min"] - Mu_c / 1000) < 1e-9 and "x=1.68m" in st["badge"] and "끌어 옮기다가" in st["note"]

            # 36. 파괴 후 보 파편·하중물이 호수에 빠져 가라앉음 (첨벙)
            for _k in range(60):   # 헤드리스 브라우저는 실제 시간보다 느리게 돌 수 있으니, 가라앉을 때까지 기다린다
                await asyncio.sleep(0.5)
                if await ev(ws, 4590, "characters.every(c => c.mesh.position.y < WATER_Y + 0.01) && debrisGroup.children.every(d => d.position.y < WATER_Y + 0.01)") is True:
                    break
            st = json.loads(await ev(ws, 460, """JSON.stringify({splash: splashCount, debrisMaxY: Math.max(...debrisGroup.children.map(d => d.position.y)),
                debrisMinY: Math.min(...debrisGroup.children.map(d => d.position.y)), loadY: characters.map(c => c.mesh.position.y), W: WATER_Y, bed: LAKE_BED})"""))
            print(f"Sinking: {st}")
            assert st["splash"] > 0 and st["debrisMaxY"] < st["W"] and st["debrisMinY"] >= st["bed"] - 1e-9
            assert all(st["bed"] - 1e-9 <= y < st["W"] for y in st["loadY"])
            await shot(ws, 461, "15_sunk_in_lake.png")

            # 37. 옮길 때 다른 하중을 통과하지 못하고 닿는 곳에서 멈춤 (review_11 P2-2, review_12 P1)
            await click_mat(ws, 470, "mild_steel")
            st = json.loads(await ev(ws, 471, """(() => { resetExperiment(); spawnCharacterAt('excavator', 3.0); spawnCharacterAt('worker', 5.0);
                const w = loadsOnBeam().find(c => c.type === 'worker'); const r = setLoadX(w.id, 1.0);
                return JSON.stringify({wx: w.xPos, r, M: currentMaxMoment, phone: getComputedStyle(valPeople.closest('tr')).display}); })()"""))
            gap = 0.86 / 2 + 0.32 / 2 + 0.02
            print(f"Move blocked by neighbour: {st} (contact gap {gap:.2f} m)")
            assert st["r"] == "blocked" and abs(st["wx"] - (3.0 + gap)) < 0.011, st
            assert abs(st["M"] - (5000 * 9.81 * 3.0 + 75 * 9.81 * st["wx"]) / 1000) < 1e-9

            # 38. review_12 P1 재현 상태: 콘크리트, 작업자 1.50 · 블록 1.06 → 블록을 오른쪽으로 끌어도 건너뛰지 않음 (파괴·겹침 없음)
            await click_mat(ws, 480, "concrete")
            st = json.loads(await ev(ws, 481, """(() => { resetExperiment(); spawnCharacterAt('worker', 1.50); spawnCharacterAt('cow', 1.06);
                const b = loadsOnBeam().find(c => c.type === 'cow'); const r1 = setLoadX(b.id, 1.55); const r2 = setLoadX(b.id, 2.2);
                return JSON.stringify({bx: b.xPos, r1, r2, broken: isBroken}); })()"""))
            print(f"No jump over neighbour: {st}")
            assert st["bx"] == 1.06 and st["r1"] == "blocked" and st["r2"] == "blocked" and not st["broken"], st
            # 빈 구간 안에서 옮기다 파괴 → 임계 위치도 겹치지 않음: 작업자 3.0, 블록 1.0 → 2.5
            st = json.loads(await ev(ws, 482, """(() => { resetExperiment(); spawnCharacterAt('worker', 3.0); spawnCharacterAt('cow', 1.0);
                const b = loadsOnBeam().find(c => c.type === 'cow'); setLoadX(b.id, 2.5);
                const L = failSnap.loads; const wk = L.find(c => c.type === 'worker'), bl = L.find(c => c.type === 'cow');
                return JSON.stringify({broken: isBroken, mode: failSnap.crit.mode, xcr: bl.xPos, gap: wk.xPos - bl.xPos, M: currentMaxMoment}); })()"""))
            xcr2 = (3.5e6 * S_ - 75 * 9.81 * 3.0) / (500 * 9.81)
            print(f"Move failure inside gap: {st} (exp xcr={xcr2:.4f})")
            assert st["broken"] and st["mode"] == "move" and abs(st["xcr"] - xcr2) < 1e-9 and st["gap"] >= 0.44 - 1e-9
            assert abs(st["M"] - 3.5e6 * S_ / 1000) < 1e-9

            # 39. 실시간 대사: 상태에 따라 말이 바뀜 (빈 보 / 탄성 / 소성 / 파괴)
            await click_mat(ws, 490, "mild_steel")
            lines = {}
            await ev(ws, 491, "resetExperiment(); 0")
            lines["empty"] = json.loads(await ev(ws, 492, "JSON.stringify({t: commentaryText.textContent, c: commentaryText.className, f: commentaryAvatar.textContent})"))
            await ev(ws, 493, "spawnCharacterAt('tractor', 3.0); 0")
            lines["elastic"] = json.loads(await ev(ws, 494, "JSON.stringify({t: commentaryText.textContent, c: commentaryText.className, pct: Math.round(currentMaxStress / currentMat.fy * 100)})"))
            await ev(ws, 495, "spawnCharacterAt('excavator', 5.5); spawnCharacterAt('excavator', 4.5); spawnCharacterAt('excavator', 3.5); spawnCharacterAt('excavator', 2.5); 0")
            lines["plastic"] = json.loads(await ev(ws, 496, "JSON.stringify({t: commentaryText.textContent, c: commentaryText.className, over: currentMaxStress > currentMat.fy, b: isBroken})"))
            await ev(ws, 497, "btnUnload.click(); 0")
            lines["residual"] = json.loads(await ev(ws, 498, "JSON.stringify({t: commentaryText.textContent, c: commentaryText.className, dp: currentPermanent})"))
            await click_mat(ws, 499, "concrete")
            await ev(ws, 500, "resetExperiment(); spawnCharacterAt('excavator', 5.5); 0")
            lines["broken"] = json.loads(await ev(ws, 501, "JSON.stringify({t: commentaryText.textContent, c: commentaryText.className, f: commentaryAvatar.textContent, b: isBroken})"))
            for k, v in lines.items():
                print(f"  commentary[{k}]: ({v['c']}) {v['t'][:70]}…")
            assert "하중물" in lines["empty"]["t"] and "연강" in lines["empty"]["t"] and lines["empty"]["c"] == "info"
            assert lines["elastic"]["c"] == "good" and f"{lines['elastic']['pct']}%" in lines["elastic"]["t"]
            assert lines["plastic"]["over"] and not lines["plastic"]["b"] and lines["plastic"]["c"] == "warn" and "영구 처짐" in lines["plastic"]["t"]
            assert lines["residual"]["dp"] > 0.05 and lines["residual"]["c"] == "warn" and "소성" in lines["residual"]["t"]
            assert lines["broken"]["b"] and lines["broken"]["c"] == "danger" and "시편 교체" in lines["broken"]["t"] and lines["broken"]["f"] == "😱"
            assert len({v["t"] for v in lines.values()}) == 5, "대사가 상태마다 달라야 함"

            # 40. σ-ε 선도 클릭 → 단면계수 개념 페이지 (현재 b·h·S 값 표시) + 'learn' 미션, Esc 로 닫힘
            await click_mat(ws, 505, "mild_steel")
            await ev(ws, 506, "resetExperiment(); spawnCharacterAt('tractor', 4.0); 0")
            learn0 = await ev(ws, 507, "missions.learn")
            await ev(ws, 508, "document.getElementById('curveCard').click(); 0")
            await asyncio.sleep(0.4)
            await shot(ws, 5081, "19_concept_page.png")
            st = json.loads(await ev(ws, 509, """JSON.stringify({open: conceptModal.classList.contains('open'), learn: missions.learn, live: conceptLive.textContent,
                strip: formulaStrip.textContent, valS: valS.textContent, title: document.querySelector('#conceptModal h2').textContent, Smm: Math.round(BEAM_S * 1e6)})"""))
            print(f"Concept page: open={st['open']} learn={learn0}->{st['learn']} S={st['Smm']} live='{st['live'][:80]}…'")
            assert st["open"] and st["learn"] and not learn0
            assert "2,352" in st["valS"] and "2,352" in st["live"] and "M / S" in st["strip"] and "bh²/6" in st["title"]
            sig = 1500 * 9.81 * 4.0 / (st["Smm"] * 1e-6) / 1e6
            assert f"{sig:.1f} MPa" in st["live"], (sig, st["live"])
            await send_cmd(ws, 510, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            await send_cmd(ws, 511, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            assert await ev(ws, 512, "conceptModal.classList.contains('open')") is False
            # 두께를 바꾸면 S 표시도 바뀜
            await ev(ws, 513, "const s7=document.getElementById('beamHSlider'); s7.value='0.40'; s7.dispatchEvent(new Event('input')); 0")
            st = json.loads(await ev(ws, 514, "JSON.stringify({valS: valS.textContent, S: Math.round(BEAM_S * 1e6)})"))
            assert st["S"] == 4800 and "4,800" in st["valS"], st
            await ev(ws, 515, "const s9=document.getElementById('beamHSlider'); s9.value='0.28'; s9.dispatchEvent(new Event('input')); 0")

            # 41. 점수·종료·랭킹: 점수 = 완료 미션 점수 합, 종료 모달, 랭킹 등록(localStorage), 처음부터
            st = json.loads(await ev(ws, 520, "JSON.stringify({score, done: Object.values(missions).filter(Boolean).length, pts: MISSIONS.filter(x => missions[x.key]).reduce((a, x) => a + x.pts, 0), move: missions.move, iso: missions.iso, total: MISSION_TOTAL, bar: missionBar.style.width})"))
            print(f"Score: {st}")
            assert st["score"] == st["pts"] > 0 and st["move"] and st["iso"] and st["total"] == 1330, st
            assert abs(float(st["bar"].rstrip("%")) - st["score"] / st["total"] * 100) < 0.01, st
            await ev(ws, 521, "localStorage.removeItem('cantilever.ranking'); btnEnd.click(); 0")
            st = json.loads(await ev(ws, 522, "JSON.stringify({open: endModal.classList.contains('open'), s: endScore.textContent, sub: endSub.textContent, grade: endGrade.textContent, rows: document.querySelectorAll('#rankBox tr').length})"))
            print(f"End modal: {st}")
            assert st["open"] and st["s"] == f"{(await ev(ws, 523, 'score')):,}" and "/ 12" in st["sub"] and "엔지니어" in st["grade"] and st["rows"] == 0, st
            await ev(ws, 524, "rankName.value = '테스터'; btnRankSave.click(); 0")
            st = json.loads(await ev(ws, 525, "JSON.stringify({rows: document.querySelectorAll('#rankBox tr').length, me: document.querySelector('#rankBox tr.me td:nth-child(2)').textContent, saved: JSON.parse(localStorage.getItem('cantilever.ranking')), toast: toast.textContent})"))
            print(f"Ranking saved: rows={st['rows']} me={st['me']} saved={st['saved']} toast='{st['toast']}'")
            assert st["rows"] == 2 and st["me"] == "테스터" and len(st["saved"]) == 1 and st["saved"][0]["name"] == "테스터" and st["saved"][0]["score"] == (await ev(ws, 526, "score")) and "1위" in st["toast"]
            await ev(ws, 527, "rankName.value = '<b>x</b>'; btnRankSave.click(); 0")
            st = json.loads(await ev(ws, 528, "JSON.stringify({rows: document.querySelectorAll('#rankBox tr').length, bold: !!document.querySelector('#rankBox b'), txt: document.querySelector('#rankBox tr.me td:nth-child(2)').textContent})"))
            assert st["rows"] == 3 and not st["bold"] and st["txt"] == "<b>x</b>", st     # 이름은 HTML 로 해석되지 않음
            await shot(ws, 529, "17_end_ranking.png")
            await ev(ws, 530, "btnEndRestart.click(); 0")
            st = json.loads(await ev(ws, 531, "JSON.stringify({open: endModal.classList.contains('open'), score, cnt: missionCnt.textContent, n: loadsOnBeam().length, badge: scoreBadge.textContent, ls: localStorage.getItem('cantilever.missions')})"))
            print(f"Restart: {st}")
            assert not st["open"] and st["score"] == 0 and st["cnt"] == "0 / 12" and st["n"] == 0 and "0 점" in st["badge"] and st["ls"] is None, st
            await ev(ws, 532, "localStorage.removeItem('cantilever.ranking'); localStorage.removeItem('cantilever.playerName'); 0")

            # 42. 좁은 화면(휴대폰)에서는 하중 제거·시편 교체 버튼이 하단 부재 바로 옮겨지고, 미션 카드가 접힌 채 보 고정단을 가리지 않음
            await send_cmd(ws, 540, "Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            await asyncio.sleep(0.6)
            st = json.loads(await ev(ws, 541, """(() => { spawnCharacterAt('excavator', 5.5); const v = new THREE.Vector3(0.4, 0, 0).project(camera);
                const el = document.elementFromPoint((v.x + 1) / 2 * innerWidth, (1 - v.y) / 2 * innerHeight);
                return JSON.stringify({w: innerWidth, inSetup: !!btnUnload.closest('#setupRow'), collapsed: missionPanel.classList.contains('collapsed'), rootEl: el && el.id,
                    mini: getComputedStyle(scoreMini).display, sw: document.documentElement.scrollWidth}); })()"""))
            print(f"Phone layout: {st}")
            assert st["w"] == 390 and st["inSetup"] and st["collapsed"] and st["rootEl"] == "canvas3d" and st["mini"] != "none" and st["sw"] <= 390, st
            await send_cmd(ws, 542, "Emulation.clearDeviceMetricsOverride")
            await asyncio.sleep(0.6)
            st = json.loads(await ev(ws, 543, "JSON.stringify({w: innerWidth, inFoot: !!btnUnload.closest('#panelFoot'), collapsed: missionPanel.classList.contains('collapsed')})"))
            assert st["w"] > 820 and st["inFoot"] and not st["collapsed"], st
            await ev(ws, 544, "resetExperiment(); 0")

            # 43. review_14 P1: 순차 재하 파괴 대사의 M 은 임계 순간 M (= M_u), 고무 파괴는 취성이 아님, 두께 감소 파괴 후 개념 페이지는 임계 단면
            await click_mat(ws, 550, "concrete")
            st = json.loads(await ev(ws, 551, """(() => { resetExperiment(); spawnCharacterAt('worker', 5.0); spawnCharacterAt('cow', 5.69);
                return JSON.stringify({b: isBroken, mode: failSnap.crit.mode, M: currentMaxMoment, Min: failSnap.Min, t: commentaryText.textContent}); })()"""))
            print(f"Sequential failure commentary: M={st['M']:.3f} Min={st['Min']:.3f} '{st['t'][:60]}…'")
            assert st["b"] and st["mode"] == "increment" and abs(st["M"] - 3.5e6 * S_ / 1000) < 1e-9 and st["Min"] > 30
            assert f"임계 M = {st['M']:.1f} kN·m" in st["t"] and f"{st['Min']:.1f}" not in st["t"], st["t"]
            await click_mat(ws, 552, "rubber")
            st = json.loads(await ev(ws, 553, "(() => { resetExperiment(); for (let i = 0; i < 6; i++) spawnCharacterAt('excavator', 5.8 - i * 0.9); return JSON.stringify({b: isBroken, t: commentaryText.textContent, badge: statusBadge.textContent, toast: toast.textContent}); })()"))
            print(f"Rubber failure commentary: broken={st['b']} badge='{st['badge']}' '{st['t'][:70]}…'")
            assert st["b"] and "취성 파괴예요" not in st["t"] and "고무" in st["t"] and "극한강도" in st["t"], st["t"]
            assert "취성" not in st["badge"] and "초탄성" in st["badge"] and "취성" not in st["toast"] and "초탄성" in st["toast"], (st["badge"], st["toast"])   # review_15 P1-2
            await click_mat(ws, 554, "concrete")
            st = json.loads(await ev(ws, 555, """(() => { resetExperiment(); spawnCharacterAt('worker', 5.0);
                const sl = document.getElementById('beamHSlider'); sl.value = '0.15'; sl.dispatchEvent(new Event('input'));
                openConcept(); const live = conceptLive.textContent; conceptModal.classList.remove('open');
                return JSON.stringify({b: isBroken, mode: failSnap.crit.mode, hCr: failSnap.crit.hCr, S: failSnap.S, valS: valS.textContent, live, sigma: currentMaxStress}); })()"""))
            print(f"Thickness failure concept page: hCr={st['hCr']:.4f} S={st['S'] * 1e6:.1f} live='{st['live'][:120]}…'")
            Scr = round(st["S"] * 1e6)
            assert st["b"] and st["mode"] == "section" and f"{Scr:,}" in st["valS"] and f"{Scr:,} cm³" in st["live"] and "675" not in st["live"]
            assert f"h = {st['hCr'] * 100:.1f} cm" in st["live"] and "3.5 MPa" in st["live"] and "5.4" not in st["live"], st["live"]
            await ev(ws, 556, "const sA=document.getElementById('beamHSlider'); sA.value='0.28'; sA.dispatchEvent(new Event('input')); 0")

            # 44. review_14 P2: 첫 하중이 바로 파괴해도 first 미션 완료 / 랭킹 11위 밖 등록 행 표시 / 50위 밖은 저장 안 됨
            st = json.loads(await ev(ws, 560, "(() => { resetMissions(); resetExperiment(); spawnCharacterAt('excavator', 5.5); return JSON.stringify({b: isBroken, first: missions.first, brittle: missions.brittle, n: loadsOnBeam().length}); })()"))
            print(f"First load breaks beam: {st}")
            assert st["b"] and st["first"] and st["brittle"] and st["n"] == 0, st
            st = json.loads(await ev(ws, 561, """(() => { localStorage.removeItem('cantilever.ranking');
                const base = Date.now() - 1e6; const list = []; for (let i = 0; i < 50; i++) list.push({id: 'x' + i, name: 'P' + i, score: 1330 - i, done: 12, t: base + i, date: '2026-01-01'});
                saveRanking(list); openEnd(); rankName.value = '나'; const e = submitRanking();
                const rows = [...document.querySelectorAll('#rankBox tr')]; const me = document.querySelector('#rankBox tr.me');
                const tr = toast.getBoundingClientRect(); const hit = document.elementFromPoint(tr.left + tr.width / 2, tr.top + tr.height / 2);
                return JSON.stringify({score, rows: rows.length, hasMe: !!me, meRank: me && me.querySelector('td').textContent, saved: loadRanking().length, savedMe: loadRanking().some(r => r.id === e.id), toast: toast.textContent,
                    over: toast.classList.contains('over-modal'), z: getComputedStyle(toast).zIndex, hit: hit && hit.id, top: tr.top}); })()"""))
            print(f"Ranking beyond top 50: {st}")
            assert st["score"] == 200 and st["rows"] == 11 and not st["hasMe"] and st["saved"] == 50 and not st["savedMe"] and "들지 못해" in st["toast"] and "51위" in st["toast"], st
            assert st["over"] and int(st["z"]) > 1000 and st["top"] < 60, st   # review_15 P2-1: 모달(1000) 위에 보임 (토스트는 pointer-events:none 이라 elementFromPoint 로는 못 잡음)
            st = json.loads(await ev(ws, 562, """(() => { localStorage.removeItem('cantilever.ranking');
                const base = Date.now() - 1e6; const list = []; for (let i = 0; i < 20; i++) list.push({id: 'y' + i, name: 'P' + i, score: 1330 - i, done: 12, t: base + i, date: '2026-01-01'});
                saveRanking(list); rankName.value = '나'; const e = submitRanking();
                const me = document.querySelector('#rankBox tr.me');
                return JSON.stringify({rows: document.querySelectorAll('#rankBox tr').length, meRank: me && me.querySelector('td').textContent, saved: loadRanking().length, toast: toast.textContent}); })()"""))
            print(f"Ranking rank 21: {st}")
            assert st["rows"] == 13 and st["meRank"] == "21" and st["saved"] == 21 and "21위" in st["toast"], st
            await ev(ws, 563, "endModal.classList.remove('open'); localStorage.clear(); resetMissions(); resetExperiment(); 0")

            # 45. (번외 index_plus.html 전용) review_17: σ 타일 막대 = 숫자와 같은 σ_y 기준 / 단축키가 드래그·자동 반복 중 무시 / 점수 팝업이 모달 위·층층이 / 연성 안내(중장비 3개 + 23 cm) 재현
            if await ev(ws, 570, "typeof updateStatTiles === 'function'") is True:
                st = json.loads(await ev(ws, 571, """(() => { resetMissions(); document.querySelector('.mat-btn[data-mat="mild_steel"]').click(); resetExperiment(); spawnCharacterAt('excavator', 5.52); spawnCharacterAt('excavator', 4.62); spawnCharacterAt('excavator', 3.72);
                    const num = +document.getElementById('tileSv').firstChild.nodeValue, bar = parseFloat(document.getElementById('tileSb').style.width);
                    const key = (t, k) => window.dispatchEvent(new KeyboardEvent('keydown', Object.assign({key: k, bubbles: true}, t)));
                    const n0 = loadsOnBeam().length; isDragging = true; key({}, '1'); isDragging = false; const n1 = loadsOnBeam().length;
                    moveDrag = {id: 0}; key({}, '2'); moveDrag = null; const n2 = loadsOnBeam().length;
                    orbitDrag = {x: 0, y: 0}; key({}, '3'); orbitDrag = null; const n3 = loadsOnBeam().length;
                    key({repeat: true}, '1'); const n4 = loadsOnBeam().length;
                    return JSON.stringify({num, bar, yielded: currentMaxStress > currentMat.fy, M: currentMaxMoment, n0, n1, n2, n3, n4, tileCls: document.getElementById('tileS').className}); })()"""))
                print(f"Plus tile/shortcut guard: {st}")
                assert abs(min(st["num"], 100) - st["bar"]) <= 1 and st["num"] > 100 and st["yielded"] and "warn" in st["tileCls"], st   # 숫자(σ/σ_y)와 막대가 같은 기준, 100% 넘으면 가득 참
                assert st["n0"] == 3 and st["n1"] == 3 and st["n2"] == 3 and st["n3"] == 3 and st["n4"] == 3, st
                st = json.loads(await ev(ws, 572, """(() => { const sB = document.getElementById('beamHSlider'); sB.value = '0.23'; sB.dispatchEvent(new Event('input')); sB.dispatchEvent(new Event('change'));
                    return JSON.stringify({b: isBroken, mode: failureMode, ductile: missions.ductile, bar: parseFloat(document.getElementById('tileSb').style.width), num: +document.getElementById('tileSv').firstChild.nodeValue, cls: document.getElementById('tileS').className}); })()"""))
                print(f"Plus ductile hint reproduces: {st}")
                assert st["b"] and st["mode"] == "ductile" and st["ductile"] and st["bar"] == 100 and st["num"] >= 100 and "danger" in st["cls"], st
                st = json.loads(await ev(ws, 573, """(() => { const sB = document.getElementById('beamHSlider'); sB.value = '0.28'; sB.dispatchEvent(new Event('input')); sB.dispatchEvent(new Event('change')); resetExperiment();
                    document.querySelectorAll('.score-pop').forEach(e => e.remove()); openConcept();
                    const pops = [...document.querySelectorAll('.score-pop')]; const z = pops.map(e => +getComputedStyle(e).zIndex);
                    scorePop(50); const tops = [...document.querySelectorAll('.score-pop')].map(e => e.getBoundingClientRect().top);
                    const n0 = loadsOnBeam().length; window.dispatchEvent(new KeyboardEvent('keydown', {key: '1', bubbles: true})); const n1 = loadsOnBeam().length;
                    conceptModal.classList.remove('open'); return JSON.stringify({pops: pops.length, z, tops, learn: missions.learn, n0, n1}); })()"""))
                print(f"Plus score popup: {st}")
                assert st["pops"] == 1 and st["learn"] and all(v > 1000 for v in st["z"]) and len(st["tops"]) == 2 and st["tops"][1] - st["tops"][0] >= 20 and all(0 <= t < 900 for t in st["tops"]) and st["n0"] == st["n1"] == 0, st   # 두 팝업 모두 화면 안, 아래로 층층이
                await ev(ws, 574, "document.querySelectorAll('.score-pop').forEach(e => e.remove()); localStorage.clear(); resetMissions(); resetExperiment(); 0")

            # 46. (번외) 보가 부러져도 점수는 남고, 실패 카드에서 새 시편을 받으면 0점에서 다시 시작
            if await ev(ws, 580, "typeof openWhy === 'function'") is True:
                await click_mat(ws, 581, "concrete")
                await ev(ws, 582, "resetMissions(); resetExperiment(); spawnCharacterAt('excavator', 5.5); 0")
                await asyncio.sleep(2.2)
                fc = json.loads(await ev(ws, 583, "JSON.stringify({b: isBroken, show: whyModal.classList.contains('open'), sub: whyText.textContent, score, pts: MISSIONS.filter(x => missions[x.key]).reduce((a, x) => a + x.pts, 0), cnt: missionCnt.textContent})"))
                print(f"Failure card keeps score: {fc}")
                assert fc["b"] and fc["show"] and "σ = M / S" in fc["sub"] and fc["score"] == fc["pts"] == 200 and fc["cnt"] == "2 / 12", fc
                assert await ev(ws, 584, "(() => { const r = btnWhyRetry.getBoundingClientRect(); const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!h && (h === btnWhyRetry || btnWhyRetry.contains(h)); })()") is True, "retry button must be clickable"
                await shot(ws, 585, "18_why_window.png")
                await ev(ws, 586, "btnWhyRetry.click(); 0")
                re = json.loads(await ev(ws, 587, "JSON.stringify({show: whyModal.classList.contains('open'), broken: isBroken, loads: loadsOnBeam().length, score})"))
                print(f"After retry: {re}")
                assert not re["show"] and not re["broken"] and re["loads"] == 0 and re["score"] == 200, re   # 점수는 적립 유지
                await ev(ws, 588, "spawnCharacterAt('cow', 1.0); 0")
                assert await ev(ws, 589, "missions.first") is True, "new run can earn points again"
                await ev(ws, 590, "resetMissions(); resetExperiment(); 0")

            # 47. 모바일(터치): 도크에서 끌어 보에 놓기, 보 위 하중을 손가락으로 옮기기, 재료 버튼 탭
            if await ev(ws, 600, "typeof updateStatTiles === 'function'") is True:
                await send_cmd(ws, 601, "Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
                await send_cmd(ws, 602, "Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
                await asyncio.sleep(0.8)
                await ev(ws, 603, "hideWhy(); resetMissions(); resetExperiment(); 0")
                await ev(ws, 604, "document.querySelector('.mat-btn[data-mat=\"mild_steel\"]').click(); 0")
                tid = [6100]
                async def touch_path(pts):
                    tid[0] += 1
                    await send_cmd(ws, tid[0], "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": pts[0][0], "y": pts[0][1]}]})
                    for x, y in pts[1:]:
                        tid[0] += 1
                        await send_cmd(ws, tid[0], "Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y}]})
                        await asyncio.sleep(0.02)
                    tid[0] += 1
                    await send_cmd(ws, tid[0], "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                    await asyncio.sleep(0.3)
                async def tap(x, y):
                    await touch_path([(x, y)])
                def line(a, b, n=14):
                    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
                # 보 위 점(화면 좌표) 계산: 보의 s 위치 기준
                BEAM_SCREEN = "(s) => { const pt = visPts.reduce((best, p) => Math.abs(p.s - s) < Math.abs(best.s - s) ? p : best); const cr = canvas.getBoundingClientRect(); const v = new THREE.Vector3(pt.x, pt.y + BEAM_H / 2, 0).project(camera); return [cr.left + (v.x + 1) / 2 * cr.width, cr.top + (1 - v.y) / 2 * cr.height]; }"
                dock = json.loads(await ev(ws, 605, "JSON.stringify((() => { const r = document.getElementById('spawnExcavator').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"))
                target = json.loads(await ev(ws, 606, f"JSON.stringify(({BEAM_SCREEN})(3.0))"))
                await touch_path(line(dock, target))
                st = json.loads(await ev(ws, 607, "JSON.stringify({n: loadsOnBeam().length, x: loadsOnBeam().length ? loadsOnBeam()[0].xPos : null, b: isBroken})"))
                print(f"Touch drop from dock: {st}")
                assert st["n"] == 1 and not st["b"] and st["x"] is not None and abs(st["x"] - 3.0) < 0.2, st
                # 보 위 하중을 손가락으로 끌어 옮기기 (x 3.0 → 1.5)
                goal = json.loads(await ev(ws, 609, f"JSON.stringify(({BEAM_SCREEN})(1.5))"))
                for _try in range(3):   # 떠 있는 하중물은 매 순간 조금씩 튀므로, 잡히지 않으면 다시 잡아 끈다
                    cen = json.loads(await ev(ws, 608, "JSON.stringify((() => { const c = loadsOnBeam()[0]; const cr = canvas.getBoundingClientRect(); const v = new THREE.Box3().setFromObject(c.mesh).getCenter(new THREE.Vector3()).project(camera); return [cr.left + (v.x + 1) / 2 * cr.width, cr.top + (1 - v.y) / 2 * cr.height]; })())"))
                    await touch_path(line(cen, goal))
                    if abs(json.loads(await ev(ws, 6095, "JSON.stringify(loadsOnBeam()[0].xPos)")) - 1.5) < 0.2:
                        break
                st = json.loads(await ev(ws, 610, "JSON.stringify({x: loadsOnBeam()[0].xPos, move: missions.move})"))
                print(f"Touch move on beam: {st}")
                assert abs(st["x"] - 1.5) < 0.2 and st["move"], st
                # 재료 버튼 탭 (콘크리트)
                cr = json.loads(await ev(ws, 611, "JSON.stringify((() => { const r = document.querySelector('.mat-btn[data-mat=\"concrete\"]').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"))
                await tap(cr[0], cr[1])
                mk = await ev(ws, 612, "currentMatKey")
                print(f"Tap material: {mk}")
                assert mk == "concrete", mk
                await shot(ws, 613, "20_mobile_touch.png")
                await asyncio.sleep(2.2)   # 콘크리트를 누르면 보가 깨져 설명 창이 뜨므로 닫고 진행
                await ev(ws, 6131, "hideWhy(); 0")
                # 휴대폰에서 개념 페이지·종료 모달도 탭으로 열리고, 닫는 버튼이 화면 안에 있어야 함
                cc = json.loads(await ev(ws, 617, "JSON.stringify((() => { const r = curveCard.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"))
                await tap(cc[0], cc[1])
                await asyncio.sleep(0.4)
                mv = json.loads(await ev(ws, 618, "JSON.stringify((() => { const r = btnConceptOk.getBoundingClientRect(); const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return {open: conceptModal.classList.contains('open'), inside: r.top >= 0 && r.bottom <= innerHeight, hit: !!h && (h === btnConceptOk || btnConceptOk.contains(h))}; })())"))
                print(f"Phone concept modal: {mv}")
                assert mv["open"] and mv["inside"] and mv["hit"], mv
                await shot(ws, 619, "21_mobile_concept.png")
                await ev(ws, 620, "conceptModal.classList.remove('open'); 0")
                ec = json.loads(await ev(ws, 621, "JSON.stringify((() => { const r = btnEnd.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })())"))
                await tap(ec[0], ec[1])
                await asyncio.sleep(0.4)
                mv = json.loads(await ev(ws, 622, "JSON.stringify((() => { const r = btnCloseEnd.getBoundingClientRect(); return {open: endModal.classList.contains('open'), inside: r.top >= 0 && r.bottom <= innerHeight && r.right <= innerWidth}; })())"))
                print(f"Phone end modal: {mv}")
                assert mv["open"] and mv["inside"], mv
                await shot(ws, 623, "22_mobile_end.png")
                await ev(ws, 624, "endModal.classList.remove('open'); 0")
                await send_cmd(ws, 614, "Emulation.setTouchEmulationEnabled", {"enabled": False})
                await send_cmd(ws, 615, "Emulation.clearDeviceMetricsOverride")
                await asyncio.sleep(0.6)
                await ev(ws, 616, "resetMissions(); resetExperiment(); document.querySelector('.mat-btn[data-mat=\"mild_steel\"]').click(); 0")

            # 48. (번외) 표지 · 도크 순서 · 통통 튐 · 선택 후 ← → 이동 · Delete 제거 · 다시하기 · 설명 창 · 표 글자 · 배경음악
            if await ev(ws, 650, "typeof selectLoad === 'function' && typeof openWhy === 'function'") is True:
                order = await ev(ws, 651, "JSON.stringify([...document.querySelectorAll('#dockBar .spawner-card')].map(b => b.querySelector('.spawner-name').textContent + ' ' + b.querySelector('.spawner-weight').textContent))")
                print(f"Dock order: {order}")
                assert order == '["농부 75 kg","돼지 150 kg","소 500 kg","트랙터 1,500 kg","포크레인 5,000 kg"]', order
                fs = await ev(ws, 652, "parseFloat(getComputedStyle(document.querySelector('.readout-table td.val')).fontSize)")
                assert fs >= 16, f"readout value font {fs}px"
                await ev(ws, 653, "resetMissions(); resetExperiment(); spawnCharacterAt('pig', 3.0); 0")
                y0 = await ev(ws, 654, "characters[characters.length - 1].mesh.position.y")
                await asyncio.sleep(0.13)
                y1 = await ev(ws, 655, "characters[characters.length - 1].mesh.position.y")
                await asyncio.sleep(0.13)
                y2 = await ev(ws, 656, "characters[characters.length - 1].mesh.position.y")
                print(f"Bounce y samples: {y0:.4f} {y1:.4f} {y2:.4f}")
                assert max(y0, y1, y2) - min(y0, y1, y2) > 0.005, "load should keep bouncing"
                # 클릭으로 선택 → ← 로 옮기기 → Delete 로 제거
                cid = await ev(ws, 657, "loadsOnBeam()[0].id")
                await ev(ws, 658, f"selectLoad({cid}); 0")
                x0 = await ev(ws, 659, "loadsOnBeam()[0].xPos")
                await send_cmd(ws, 660, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowLeft", "code": "ArrowLeft", "windowsVirtualKeyCode": 37})
                await send_cmd(ws, 661, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowLeft", "code": "ArrowLeft", "windowsVirtualKeyCode": 37})
                x1 = await ev(ws, 662, "loadsOnBeam()[0].xPos")
                print(f"Arrow move: {x0:.2f} -> {x1:.2f}, marker={await ev(ws, 663, 'selMarker.visible')}")
                assert abs((x0 - x1) - 0.05) < 1e-6, (x0, x1)
                await send_cmd(ws, 664, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "Delete", "code": "Delete", "windowsVirtualKeyCode": 46})
                await send_cmd(ws, 665, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "Delete", "code": "Delete", "windowsVirtualKeyCode": 46})
                n_after = await ev(ws, 666, "loadsOnBeam().length")
                assert n_after == 0, n_after
                # 설명 창: 보를 부러뜨리고 2.2 초 뒤 열리는지, 내용과 빨간 점
                await click_mat(ws, 670, "concrete")
                await ev(ws, 671, "resetMissions(); resetExperiment(); spawnCharacterAt('excavator', 5.5); 0")
                await asyncio.sleep(2.2)
                wy = json.loads(await ev(ws, 672, "JSON.stringify({open: whyModal.classList.contains('open'), text: whyText.textContent, cw: whyCanvas.width, fail: !!failMarker, card: !!document.getElementById('failCard')})"))
                print(f"Why window: open={wy['open']} text='{wy['text'][:60]}…'")
                assert wy["open"] and "σ = M / S" in wy["text"] and "왜 부러졌나요" in wy["text"], wy
                await shot(ws, 673, "23_why_window.png")
                await ev(ws, 674, "btnWhyOk.click(); 0")
                # 다시하기 (오른쪽 아래 버튼): 하중·파괴·점수 모두 처음으로
                rr = json.loads(await ev(ws, 675, "JSON.stringify((() => { const r = btnRestart.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, inside: r.bottom <= innerHeight && r.right <= innerWidth}; })())"))
                assert rr["inside"], rr
                await ev(ws, 676, "btnRestart.click(); 0")
                st = json.loads(await ev(ws, 677, "JSON.stringify({b: isBroken, n: loadsOnBeam().length, score, open: whyModal.classList.contains('open')})"))
                assert not st["b"] and st["n"] == 0 and st["score"] > 0 and not st["open"], st   # 다시하기: 점수 적립 유지
                # 배경음악: 표지를 넘기면 재생 시작
                bg = await ev(ws, 678, "bgmTimer !== null && bgmGain !== null")
                assert bg is True, "background music should start with the game"
                print("Restart, why window, music, dock order: ok")
                await ev(ws, 679, "resetMissions(); resetExperiment(); 0")

            # 49. (번외) 쉬프트+방향키는 빠르게 (0.2 m), 더블클릭은 하중물 삭제
            if await ev(ws, 700, "typeof selectLoad === 'function'") is True:
                await ev(ws, 701, "hideWhy(); resetMissions(); resetExperiment(); spawnCharacterAt('worker', 3.0); 0")
                cid = await ev(ws, 702, "loadsOnBeam()[0].id")
                await ev(ws, 703, f"selectLoad({cid}); 0")
                x0 = await ev(ws, 704, "loadsOnBeam()[0].xPos")
                await send_cmd(ws, 705, "Input.dispatchKeyEvent", {"type": "keyDown", "key": "ArrowLeft", "code": "ArrowLeft", "windowsVirtualKeyCode": 37, "modifiers": 8})
                await send_cmd(ws, 706, "Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowLeft", "code": "ArrowLeft", "windowsVirtualKeyCode": 37, "modifiers": 8})
                x1 = await ev(ws, 707, "loadsOnBeam()[0].xPos")
                print(f"Shift arrow: {x0:.2f} -> {x1:.2f}")
                assert abs((x0 - x1) - 0.2) < 1e-6, (x0, x1)
                # 앞모습: 모든 하중물의 자기 방향 회전이 관객(+z) 쪽을 향하는지
                fr = json.loads(await ev(ws, 708, "JSON.stringify(['worker','pig','cow','tractor','excavator'].map(t => { const g = LOAD_TYPES[t].make(); const r = Math.abs(((g.rotation.y % (2*Math.PI)) + 2*Math.PI) % (2*Math.PI) - 3*Math.PI/2) < 1e-6 || Math.abs(g.rotation.y + Math.PI/2) < 1e-6 || g.rotation.y === 0; return [t, +g.rotation.y.toFixed(3), r]; }))"))
                print(f"Facing: {fr}")
                # 더블클릭: 가운데 하중물 위에서 두 번 클릭 → 삭제
                cc = json.loads(await ev(ws, 709, "JSON.stringify((() => { const c = loadsOnBeam()[0]; const cr = canvas.getBoundingClientRect(); const v = new THREE.Box3().setFromObject(c.mesh).getCenter(new THREE.Vector3()).project(camera); return [cr.left + (v.x + 1) / 2 * cr.width, cr.top + (1 - v.y) / 2 * cr.height]; })())"))
                for k, typ in enumerate(["mousePressed", "mouseReleased", "mousePressed", "mouseReleased"]):
                    await send_cmd(ws, 710 + k, "Input.dispatchMouseEvent", {"type": typ, "x": cc[0], "y": cc[1], "button": "left", "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1 if k < 2 else 2})
                    await asyncio.sleep(0.08)
                await asyncio.sleep(0.3)
                n = await ev(ws, 720, "loadsOnBeam().length")
                print(f"After double click: {n} loads")
                assert n == 0, n
                await ev(ws, 721, "resetMissions(); resetExperiment(); 0")

            errors = [e for e in EVENTS if e["method"] == "Runtime.exceptionThrown"
                      or (e["method"] == "Runtime.consoleAPICalled" and e["params"]["type"] in ("error", "warning"))
                      or (e["method"] == "Log.entryAdded" and e["params"]["entry"]["level"] == "error")]
            for e in errors:
                print("  JS ERROR/WARN:", json.dumps(e["params"], ensure_ascii=False)[:300])
            assert not errors, f"{len(errors)} console errors/warnings"

            print()
            print("ALL E2E BROWSER TESTS PASSED")

    finally:
        chrome_proc.terminate()

if __name__ == "__main__":
    asyncio.run(main())
