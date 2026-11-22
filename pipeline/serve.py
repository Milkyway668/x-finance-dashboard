"""
本地更新服务：让页面上的「抓取最新」按钮真正跑起来
启动：python pipeline/serve.py
页面通过 http://127.0.0.1:8787 调用
"""
import json, os, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
PORT = 8787

state = {"running": False, "code": None, "tail": "", "started": None, "finished": None, "new": None}


def run_pipeline():
    state.update(running=True, code=None, tail="", started=time.time(), finished=None, new=None)
    log_path = os.path.join(ROOT, "data", "refresh.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            p = subprocess.Popen([PY, "-I", os.path.join(ROOT, "pipeline", "update_all.py")],
                                 cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
            state["pid"] = p.pid
            code = p.wait()
    except Exception as e:
        code = -1
        state["tail"] = str(e)[:300]
    state["running"] = False
    state["code"] = code
    state["finished"] = time.time()
    try:
        state["tail"] = open(log_path, encoding="utf-8", errors="replace").read()[-1500:]
    except Exception:
        pass


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self._cors()
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path != "/refresh":
            return self._json({"error": "not found"}, 404)
        if state["running"]:
            return self._json({"status": "running"})
        threading.Thread(target=run_pipeline, daemon=True).start()
        self._json({"status": "started"})

    def do_GET(self):
        if self.path == "/status":
            return self._json({
                "running": state["running"], "code": state["code"],
                "seconds": round((state["finished"] or time.time()) - (state["started"] or time.time()), 1)
                if state["started"] else 0,
                "tail": state["tail"][-600:],
            })
        self._json({"ok": True, "hint": "POST /refresh 触发抓取，GET /status 查询进度"})


if __name__ == "__main__":
    print(f"本地更新服务已启动：http://127.0.0.1:{PORT}")
    print("保持这个窗口开着，页面上的「抓取最新」才可用。Ctrl+C 退出。")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
