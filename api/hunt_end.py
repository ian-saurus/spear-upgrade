import json
import os
import sys
import time

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

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(max(0, n)) or b"{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def do_POST(self):
        try:
            return self._handle()
        except S.StoreBusy:
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)

    def _handle(self):
        user = S.auth_user(self.headers)
        if not user:
            return self._send({"ok": False}, 401)
        body = self._body()
        accounts = S.load_json("accounts.json", {}, strict=True)
        acct = S.auth_account(self.headers, user, strict=True)
        if not acct:
            return self._send({"ok": False}, 401)
        accounts[user] = acct
        lvl = S.clamp_int(body.get("lvl"), 1, 100000, 1)
        kills = S.clamp_int(body.get("kills"), 0, 10**7)
        bosses = S.clamp_int(body.get("bosses"), 0, 10**6)
        score = min(S.clamp_int(body.get("score"), 0, 10**9),
                    S.score_cap(lvl, kills))
        acct["runs"] = S.clamp_int(acct.get("runs"), 0, 10**7, 0) + 1
        acct["best"] = max(S.clamp_int(acct.get("best"), 0, 10**9, 0), score)
        entry = {"name": user, "lvl": lvl, "kills": kills,
                 "bosses": bosses, "score": score,
                 "ts": int(time.time())}
        board = S.load_json("scores.json", [], strict=True)
        board.append(entry)
        board.sort(key=lambda s: int(s.get("score", 0) or 0), reverse=True)
        if not S.save_json("scores.json", board[:500]):
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)
        if not S.save_json("accounts.json", accounts):
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)
        return self._send({"ok": True, "posted": True,
                           "me": S.public_profile(user, acct)})

    def log_message(self, *a):
        pass
