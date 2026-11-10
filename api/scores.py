import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler

import _store as S


class handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            arr = S.load_json("scores.json", [])
            best = {}
            for s in arr:
                k = s.get("name") or ""
                try:
                    sc = int(s.get("score", 0))
                except (TypeError, ValueError):
                    sc = 0
                if k not in best or sc > int(best[k].get("score", 0) or 0):
                    best[k] = s
            arr = sorted(best.values(), key=lambda s: int(s.get("score", 0) or 0),
                         reverse=True)
            return self._send(arr[:50])
        except S.StoreBusy:
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)

    def log_message(self, *a):
        pass
