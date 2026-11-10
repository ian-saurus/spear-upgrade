import json
import os
import re
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler

import _store as S

USER_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


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
        pw = str(body.get("pass", ""))
        if not USER_RE.match(user):
            return self._send({"ok": False, "err": "name: 3-16 letters/digits/_"}, 400)
        if not 4 <= len(pw) <= 72:
            return self._send({"ok": False, "err": "password: 4+ chars"}, 400)
        accounts = S.load_json("accounts.json", {}, strict=True)
        if user in accounts:
            return self._send({"ok": False, "err": "name taken"}, 409)
        salt = secrets.token_hex(16)
        accounts[user] = {"salt": salt, "hash": S.hash_pw(pw, salt),
                          "runs": 0, "best": 0,
                          "created": int(time.time()), "tokv": 0}
        if not S.save_json("accounts.json", accounts):
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)
        tok = S.mint_token(user, 0)
        return self._send({"ok": True, "token": tok,
                           "me": S.public_profile(user, accounts[user])})

    def log_message(self, *a):
        pass
