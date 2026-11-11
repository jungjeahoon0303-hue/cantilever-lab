# qa/viewports.py — 여러 화면 크기에서 스크린샷을 찍어 레이아웃을 점검한다.
# 사용: python qa/viewports.py [출력폴더]
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
import http.server

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "qa", "shots")
PAGE = os.environ.get("E2E_PAGE", "index.html")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DBG, HTTP = 9334, 8091
SIZES = [("1920x1080", 1920, 1080, False), ("1280x720", 1280, 720, False),
         ("tablet_820x1180", 820, 1180, True), ("small_540x900", 540, 900, True), ("phone_390x844", 390, 844, True)]


def serve():
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=ROOT, **k)
    http.server.ThreadingHTTPServer(("127.0.0.1", HTTP), handler).serve_forever()


async def main():
    os.makedirs(OUT, exist_ok=True)
    threading.Thread(target=serve, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="cantilever_vp_")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={DBG}", f"--user-data-dir={prof}",
                             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1440,900", "about:blank"])
    try:
        ws_url = None
        for _ in range(40):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DBG}/json").read())
                pages = [t for t in tabs if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            n = 0

            async def cmd(method, params=None):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
                while True:
                    d = json.loads(await ws.recv())
                    if d.get("id") == n:
                        return d

            errors = []
            await cmd("Runtime.enable")
            for name, w, h, mobile in SIZES:
                await cmd("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile})
                await cmd("Page.navigate", {"url": f"http://127.0.0.1:{HTTP}/{PAGE}"})
                await asyncio.sleep(2.5)
                await cmd("Runtime.evaluate", {"expression": "const b = document.getElementById('btnStart'); if (b) b.click(); 0", "returnByValue": True})   # 표지 넘기기
                await asyncio.sleep(0.8)
                hint = await cmd("Runtime.evaluate", {"expression": "(() => { const r = document.getElementById('firstHint').getBoundingClientRect(); return JSON.stringify({l: r.left, r: r.right, w: innerWidth}); })()", "returnByValue": True})
                hb = json.loads(hint["result"]["result"]["value"])
                shot0 = await cmd("Page.captureScreenshot", {"format": "png"})
                with open(os.path.join(OUT, f"vp_{name}_first.png"), "wb") as f:
                    f.write(base64.b64decode(shot0["result"]["data"]))
                if hb["l"] < 0 or hb["r"] > hb["w"]:
                    errors.append(f"{name}: first hint clipped {hb}")
                r = await cmd("Runtime.evaluate", {"expression": "spawnCharacterAt('excavator', 5.5); spawnCharacterAt('tractor', 3.5); JSON.stringify({sw: document.documentElement.scrollWidth, iw: innerWidth})", "returnByValue": True})
                dims = json.loads(r["result"]["result"]["value"])
                await asyncio.sleep(0.8)
                shot = await cmd("Page.captureScreenshot", {"format": "png"})
                path = os.path.join(OUT, f"vp_{name}.png")
                with open(path, "wb") as f:
                    f.write(base64.b64decode(shot["result"]["data"]))
                # 보의 고정단·끝단·수면이 HUD/패널에 가려지지 않고 3D 화면 위에 보여야 함
                vis = await cmd("Runtime.evaluate", {"expression": """(() => {
                    const pts = {root: [0.4, 0], tip: [visPts[visPts.length-1].x - 0.1, visPts[visPts.length-1].y], water: [3, WATER_Y - 0.2]};
                    const out = {};
                    for (const [k, [x, y]] of Object.entries(pts)) {
                      const v = new THREE.Vector3(x, y, 0).project(camera);
                      const sx = (v.x + 1) / 2 * innerWidth, sy = (1 - v.y) / 2 * innerHeight;
                      const el = document.elementFromPoint(sx, sy);
                      out[k] = el && el.id === 'canvas3d' ? 'ok' : ('covered by ' + (el ? (el.id || el.className) : 'nothing') + ` @${sx.toFixed(0)},${sy.toFixed(0)}`);
                    }
                    return JSON.stringify(out); })()""", "returnByValue": True})
                vis = json.loads(vis["result"]["result"]["value"])
                print(f"  {name}: beam/water visibility {vis}")
                for k, v in vis.items():
                    if v != "ok":
                        errors.append(f"{name}: {k} {v}")
                # 표지를 넘기고 시작 (표지가 화면을 덮고 있으면 조작부가 가려진 것으로 잘못 나온다)
                await cmd("Runtime.evaluate", {"expression": "const b = document.getElementById('btnStart'); if (b) b.click(); 0", "returnByValue": True})
                await asyncio.sleep(0.8)
                # 하단 부재 설정·도크·종료 버튼·재료 칩·두께 슬라이더가 화면 안에 다 보이고 그 자리에서 눌리는지 (review_15 P1-1)
                ctl = await cmd("Runtime.evaluate", {"expression": """(() => {
                    const out = {};
                    const ids = ['setupBar', 'dockBar', 'btnEnd', 'btnUnload', 'btnReset', 'beamHSlider', 'spawnExcavator', 'matGrid'];
                    if (document.getElementById('statRow')) ids.push('statRow', 'tileS');   // 번외 파일: 핵심 수치 타일 (패널 안에서 스크롤해 닿을 수 있어야 함)
                    for (const id of ids) {
                      const el = document.getElementById(id);
                      if (id === 'statRow' || id === 'tileS') el.scrollIntoView({block: 'nearest'});
                      const r = el.getBoundingClientRect();
                      if (id === 'spawnExcavator' && dockBar.scrollWidth > dockBar.clientWidth + 1) { out[id] = 'ok'; continue; }   // 도크 가로 스크롤은 허용
                      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
                      const hit = document.elementFromPoint(cx, cy);
                      const inside = r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth + 1 && r.height >= 12;
                      out[id] = inside && hit && (el === hit || el.contains(hit)) ? 'ok' : `rect=${r.left.toFixed(0)},${r.top.toFixed(0)}-${r.right.toFixed(0)},${r.bottom.toFixed(0)} hit=${hit ? (hit.id || hit.className) : 'none'}`;
                    }
                    const ps = document.getElementById('panelScroll'); if (ps) ps.scrollTop = 0;
                    return JSON.stringify(out); })()""", "returnByValue": True})
                ctl = json.loads(ctl["result"]["result"]["value"])
                bad = {k: v for k, v in ctl.items() if v != "ok"}
                print(f"  {name}: controls {'all visible' if not bad else bad}")
                for k, v in bad.items():
                    errors.append(f"{name}: control {k} not fully visible ({v})")
                overflow = dims["sw"] > dims["iw"]
                print(f"{name}: scrollWidth={dims['sw']} innerWidth={dims['iw']} {'HORIZONTAL OVERFLOW' if overflow else 'ok'} -> {path}")
                if overflow:
                    errors.append(f"{name}: horizontal overflow")
            if errors:
                sys.exit(f"layout problems: {errors}")
    finally:
        proc.terminate()


asyncio.run(main())
