#!/usr/bin/env python3
"""End-to-end checks for the spear-upgrade hub SSO endpoint.

Spins up the real HTTP handlers with a temp local store and a stubbed hub
verifier, so no network or real hub account is needed.
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ["SPEAR_TEST_DIR"] = tempfile.mkdtemp(prefix="spear-sso-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import sso as sso_mod


def fake_hub_ok(token):
    if token == "good-premium-token":
        return {"ok": True, "user": {"name": "Hub Hero", "email": "hubhero@example.com"}, "premium": True}
    if token == "good-basic-token":
        return {"ok": True, "user": {"name": "Hub Kid", "email": "hubkid@example.com"}, "premium": False}
    if token == "flaky-token":
        raise IOError("hub down")
    return {"ok": False, "err": "bad sso token"}


sso_mod.hub_check = fake_hub_ok


class App(BaseHTTPRequestHandler):
    def _route(self):
        if self.command == "POST" and self.path.split("?", 1)[0] == "/api/sso":
            h = sso_mod.handler.__new__(sso_mod.handler)
            h.command = self.command
            h.request_version = "HTTP/1.0"
            h.requestline = self.requestline
            h.headers = self.headers
            h.rfile = self.rfile
            h.wfile = self.wfile
            h._headers_buffer = []
            h.close_connection = True
            h.do_POST()
            return
        body = b'{"ok":false,"err":"no route"}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._route()

    def do_GET(self):
        self._route()

    def log_message(self, *a):
        pass


def call(body):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/sso" % PORT, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


srv = HTTPServer(("127.0.0.1", 0), App)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# 1. premium hub user gets linked account with premium flag
s, r = call({"token": "good-premium-token"})
assert s == 200 and r.get("ok"), (s, r)
assert r["me"]["user"] == "HubHero", r
assert r["me"].get("premium") == 1, r
first_tok = r["token"]

# 2. same hub user again links the SAME account (no duplicate), stays premium
s, r = call({"token": "good-premium-token"})
assert s == 200 and r["ok"] and r["me"]["user"] == "HubHero", (s, r)

# 3. premium flag syncs from hub (hub says not premium anymore)
def fake_hub_demoted(token):
    d = {"ok": True, "user": {"name": "Hub Hero", "email": "hubhero@example.com"}, "premium": False}
    return d
orig = sso_mod.hub_check
sso_mod.hub_check = lambda t: fake_hub_demoted(t)
try:
    s, r = call({"token": "good-premium-token"})
finally:
    sso_mod.hub_check = fake_hub_ok
assert s == 200 and r["ok"] and r["me"].get("premium") == 0, (s, r)

# 4. basic (non-premium) hub user gets plain account, no premium
s, r = call({"token": "good-basic-token"})
assert s == 200 and r["ok"] and r["me"].get("premium") == 0, (s, r)

# 5. bad token rejected
s, r = call({"token": "nope"})
assert s == 401 and not r.get("ok"), (s, r)
s, r = call({})
assert s == 401, (s, r)

# 6. hub outage -> 503, not logged in
def fake_hub_down(token):
    raise IOError("boom")
sso_mod.hub_check = fake_hub_down
try:
    s, r = call({"token": "good-premium-token"})
finally:
    sso_mod.hub_check = fake_hub_ok
assert s == 503, (s, r)

# 7. local token from SSO verifies like a normal login
import me as me_mod  # noqa: E402

class MeApp(App):
    def _route(self):
        from http.server import BaseHTTPRequestHandler as B
        if self.path.split("?", 1)[0] == "/api/sso":
            return super()._route()
        h = me_mod.handler.__new__(me_mod.handler)
        h.command = self.command
        h.request_version = "HTTP/1.0"
        h.requestline = self.requestline
        h.headers = self.headers
        h.rfile = self.rfile
        h.wfile = self.wfile
        h._headers_buffer = []
        h.close_connection = True
        h.do_GET()

srv2 = HTTPServer(("127.0.0.1", 0), MeApp)
PORT2 = srv2.server_address[1]
threading.Thread(target=srv2.serve_forever, daemon=True).start()


def call_me(token):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/api/me" % PORT2,
        headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


s, r = call_me(first_tok)
assert s == 200 and r["me"]["user"] == "HubHero", (s, r)

# 8. Godskin data present and premium-gated
import re
src = Path(__file__).resolve().parent.parent.joinpath("index.html").read_text()
assert '"👑 Golden Godskin' in src, "godskin missing from shop"
assert "TUNIC" in src and "#eab308" in src, "godskin tunic color missing"
assert src.count("premium") >= 3, "premium gating missing"

print("sso OK")
