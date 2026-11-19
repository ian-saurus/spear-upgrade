import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler

import _store as S

# XtremeGaming hub single sign-on: the game posts the hub token here,
# we verify it server-side against the hub, then hand out a normal
# local session keyed to the hub account (email-linked, unique-ified).
HUB = os.environ.get("HUB_ORIGIN", "https://xtremegaming.vercel.app").rstrip("/")


def hub_check(token):
    import urllib.error
    url = HUB + "/api/sso/session?token=" + urllib.parse.quote(token, safe="")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        # Hub answered but rejected the token (e.g. 401) — still a usable
        # verdict, not a transport failure. Parse the body if we can.
        try:
            return json.loads(e.read() or b"null")
        except (ValueError, OSError):
            return {"ok": False, "err": "bad sso token"}
    except Exception:
        return None


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
        token = S.clean_str(self._body().get("token", ""), 500)
        if not token:
            return self._send({"ok": False, "err": "missing sso token"}, 401)
        try:
            sess = hub_check(token)
        except Exception:
            return self._send({"ok": False, "err": "hub unreachable — retry"}, 503)
        if not isinstance(sess, dict) or not sess.get("ok"):
            return self._send({"ok": False, "err": "bad sso token"}, 401)
        u = sess.get("user") or {}
        email = S.clean_str(u.get("email", ""), 80).lower()
        name = S.clean_str(u.get("name", ""), 40)
        premium = 1 if sess.get("premium") else 0
        accounts = S.load_json("accounts.json", {}, strict=True)
        user = None
        if email:
            for k, a in accounts.items():
                if isinstance(a, dict) and (a.get("hub_email") or "").lower() == email:
                    user = k
                    break
        if user is None:
            base = re.sub(r"[^A-Za-z0-9_]", "", name)[:16] or \
                re.sub(r"[^A-Za-z0-9_]", "", email.split("@")[0])[:16] or "Hunter"
            if len(base) < 3:
                base = (base + "Hunter")[:16]
            user, i = base, 2
            while user in accounts:
                user = (base[:14] + str(i))[:16]
                i += 1
            salt = secrets.token_hex(16)
            accounts[user] = {"salt": salt, "hash": S.hash_pw(salt, salt),
                              "runs": 0, "best": 0,
                              "created": int(time.time()), "tokv": 0}
        acct = accounts[user]
        if email:
            acct["hub_email"] = email
        acct["premium"] = premium
        accounts[user] = acct
        if not S.save_json("accounts.json", accounts):
            return self._send({"ok": False, "err": "storage busy — retry"}, 503)
        return self._send({"ok": True,
                           "token": S.mint_token(user, acct.get("tokv", 0)),
                           "me": S.public_profile(user, acct)})

    def log_message(self, *a):
        pass
