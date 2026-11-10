#!/usr/bin/env python3
"""End-to-end checks for the spear-upgrade API over real HTTP (temp local store)."""
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

os.environ["SPEAR_TEST_DIR"] = tempfile.mkdtemp(prefix="spear-roundtrip-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import hunt_end
import login
import me
import register
import scores

ROUTES = {
    ("POST", "/api/register"): register.handler,
    ("POST", "/api/login"): login.handler,
    ("GET", "/api/me"): me.handler,
    ("GET", "/api/scores"): scores.handler,
    ("POST", "/api/hunt_end"): hunt_end.handler,
}


class App(BaseHTTPRequestHandler):
    def _route(self):
        H = ROUTES.get((self.command, self.path.split("?", 1)[0]))
        if H is None:
            body = b'{"ok":false,"err":"no route"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        h = H.__new__(H)
        h.command = self.command
        h.request_version = "HTTP/1.0"
        h.requestline = self.requestline
        h.headers = self.headers
        h.rfile = self.rfile
        h.wfile = self.wfile
        h._headers_buffer = []
        h.close_connection = True
        if self.command == "POST":
            h.do_POST()
        else:
            h.do_GET()

    def do_POST(self):
        self._route()

    def do_GET(self):
        self._route()

    def log_message(self, *a):
        pass


def call(method, path, body=None, token=None):
    data = json.dumps(body or {}).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data, method=method,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


srv = HTTPServer(("127.0.0.1", 0), App)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

# register
s, r = call("POST", "/api/register", {"user": "TestKid", "pass": "secret1"})
assert s == 200 and r["ok"] and r["me"]["user"] == "TestKid", (s, r)
tok = r["token"]
s, r = call("POST", "/api/register", {"user": "TestKid", "pass": "secret1"})
assert s == 409 and not r["ok"], (s, r)
s, r = call("POST", "/api/register", {"user": "ab", "pass": "secret1"})
assert s == 400, (s, r)

# login
s, r = call("POST", "/api/login", {"user": "TestKid", "pass": "nope"})
assert s == 401, (s, r)
s, r = call("POST", "/api/login", {"user": "TestKid", "pass": "secret1"})
assert s == 200 and r["ok"], (s, r)
tok = r["token"]

# me
s, r = call("GET", "/api/me", token=tok)
assert s == 200 and r["me"]["user"] == "TestKid", (s, r)
s, r = call("GET", "/api/me", token="sp1.bogus.sig")
assert s == 401, (s, r)

# hunt end (run post)
s, r = call("POST", "/api/hunt_end",
            {"lvl": 30, "kills": 120, "bosses": 1, "score": 30 * 100 + 120},
            token=tok)
assert s == 200 and r["ok"] and r["me"]["runs"] == 1, (s, r)
s, rows = call("GET", "/api/scores")
mine = [x for x in rows if x.get("name") == "TestKid"]
assert len(mine) == 1 and mine[0]["score"] == 3120, rows
# spoofed giant score gets capped, not stored raw
s, r = call("POST", "/api/hunt_end",
            {"lvl": 30, "kills": 120, "bosses": 1, "score": 10 ** 9},
            token=tok)
assert s == 200 and r["ok"], (s, r)
# unauth post rejected
s, r = call("POST", "/api/hunt_end", {"lvl": 5, "kills": 1, "score": 501})
assert s == 401, (s, r)

# board shows best-per-hunter, capped score
s, rows = call("GET", "/api/scores")
assert s == 200 and isinstance(rows, list), (s, rows)
mine = [x for x in rows if x.get("name") == "TestKid"]
assert len(mine) == 1, rows
assert mine[0]["lvl"] == 30 and mine[0]["bosses"] == 1, mine
assert mine[0]["score"] == 30 * 500 + 120 * 50 + 20000, mine  # spoof capped at ceiling
assert "hash" not in json.dumps(rows) and "salt" not in json.dumps(rows)

srv.shutdown()
print("api-roundtrip OK")
