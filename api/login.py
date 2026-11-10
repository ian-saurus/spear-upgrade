import hmac
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
        body = self._body()
        user = S.clean_str(body.get("user", ""), 16)
        acct = S.load_account(user, strict=True)
        if not acct or not hmac.compare_digest(
                acct.get("hash", ""),
                S.hash_pw(str(body.get("pass", "")), acct.get("salt", "00"))):
            return self._send({"ok": False, "err": "bad login"}, 401)
        return self._send({"ok": True, "token": S.mint_token(user, acct.get("tokv", 0)),
                           "me": S.public_profile(user, acct)})

    def log_message(self, *a):
        pass
