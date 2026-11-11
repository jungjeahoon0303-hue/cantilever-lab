# qa/cdp_eval.py — index.html 을 헤드리스 Chrome 에 띄우고 JS 식을 차례로 평가해 출력 (디버깅용)
# 사용: python qa/cdp_eval.py "식1" "식2" ...
import asyncio, json, os, subprocess, sys, tempfile, threading, urllib.request, http.server
import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DBG, HTTP = 9335, 8092


def serve():
    h = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=ROOT, **k)
    http.server.HTTPServer.log_message = lambda *a: None
    http.server.ThreadingHTTPServer(("127.0.0.1", HTTP), h).serve_forever()


async def main(exprs):
    threading.Thread(target=serve, daemon=True).start()
    prof = tempfile.mkdtemp(prefix="cantilever_cdp_")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={DBG}", f"--user-data-dir={prof}",
                             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1440,900",
                             f"http://127.0.0.1:{HTTP}/index.html"], stderr=subprocess.DEVNULL)
    try:
        url = None
        for _ in range(40):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{DBG}/json").read())
                pages = [t for t in tabs if t.get("type") == "page" and "index.html" in t.get("url", "")]
                if pages:
                    url = pages[0]["webSocketDebuggerUrl"]; break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        async with websockets.connect(url, max_size=50_000_000) as ws:
            await asyncio.sleep(2.0)
            for i, e in enumerate(exprs):
                await ws.send(json.dumps({"id": i + 1, "method": "Runtime.evaluate", "params": {"expression": e, "returnByValue": True}}))
                while True:
                    d = json.loads(await ws.recv())
                    if d.get("id") == i + 1:
                        r = d["result"]
                        if "exceptionDetails" in r:
                            print(f"[{i}] EXCEPTION:", r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
                        else:
                            res = r["result"]
                            print(f"[{i}]", res.get("value", res.get("unserializableValue", res.get("description"))))
                        break
    finally:
        proc.terminate()


asyncio.run(main(sys.argv[1:]))
