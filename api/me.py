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
            user = S.auth_user(self.headers)
            if not user:
                return self._send({"ok": False}, 401)
            acct = S.auth_account(self.headers, user, strict=True)
            if not acct:
                return self._send({"ok": False}, 401)
            return self._send({"ok": True, "me": S.public_profile(user, acct)})
        except S.StoreBusy:
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)

    def log_message(self, *a):
        pass
