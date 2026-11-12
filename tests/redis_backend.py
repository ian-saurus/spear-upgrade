#!/usr/bin/env python3
"""Upstash Redis backend: protocol mapping, failure semantics, isolation.

_rreq is stubbed with an in-memory dict, so every assertion runs offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import _store as S  # noqa: E402

# captured before the stub below overrides them: the test-run guard must
# have blanked any ambient Redis credentials
_RURL_AT_IMPORT, _RTOK_AT_IMPORT = S.RURL, S.RTOK

FAILS = []
STORE = {}
FAIL_MODE = {"get": False, "set": False}


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else " :: " + str(extra)))
    if not cond:
        FAILS.append(name)


def fake_rreq(command, *args, body=None):
    if FAIL_MODE.get(command.lower(), False):
        raise IOError("simulated outage")
    if command == "GET":
        return STORE.get(args[0])
    if command == "SET":
        STORE[args[0]] = body.decode() if isinstance(body, bytes) else body
        return "OK"
    raise IOError("unexpected command " + command)


S._rreq = fake_rreq
S.RURL = "https://stub.upstash.io"
S.RTOK = "stub-token"
import json as _json
import time as _time

# 1. read-your-write round trip, keys reuse blob pathnames
S.save_json("scores.json", [{"name": "a", "score": 10}])
ok("round-trip", S.load_json("scores.json", []) == [{"name": "a", "score": 10}])
ok("key-shape", "spearupgrade/scores.json" in STORE, list(STORE))

# 2. missing key serves the default (first registration must not 503)
ok("miss-default", S.load_json("nope.json", {"d": 1}) == {"d": 1})
ok("miss-strict-default", S.load_json("nope.json", {"d": 1}, strict=True) == {"d": 1})

# 3. outage: stale cache served, then default/strict
S._cache.clear()
S.load_json("scores.json", [])
FAIL_MODE["get"] = True
ok("outage-stale", S.load_json("scores.json", [], fresh=True) == [{"name": "a", "score": 10}])
S._cache.clear()
ok("outage-default", S.load_json("scores.json", [1]) == [1])
try:
    S.load_json("scores.json", [], fresh=True, strict=True)
    ok("outage-strict", False, "no raise")
except S.StoreBusy:
    ok("outage-strict", True)
FAIL_MODE["get"] = False

# 4. write failure is reported, cache not poisoned
FAIL_MODE["set"] = True
S._cache.clear()
ok("write-fail", S.save_json("scores.json", [9]) is False)
ok("cache-clean", "scores.json" not in S._cache)
FAIL_MODE["set"] = False

# 5. payloads ride POST bodies, never URLs (values with &?= stay intact)
S.save_json("accounts.json", {"u": "a&b?c=d/e"})
ok("body-not-url", _json.loads(STORE["spearupgrade/accounts.json"]) == {"u": "a&b?c=d/e"})

# 6. no blob remnants: the suspended store must be unreachable from code
ok("no-blob", not hasattr(S, "TOKEN") and not hasattr(S, "_blob_url") and not hasattr(S, "_req") and not hasattr(S, "BASE"))
# 7. suite isolation: ambient Redis creds are blanked for tests
ok("no-ambient-redis", _RURL_AT_IMPORT == "" and _RTOK_AT_IMPORT == "", repr(_RURL_AT_IMPORT)[:40])

print("FAILURES:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
