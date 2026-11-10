"""Shared backend logic for Spear Upgrade serverless functions.

Storage: Vercel Blob (BLOB_READ_WRITE_TOKEN) with an instance-memory cache.
Local fallback: ./data/*.json (used when env var is absent, or when
SPEAR_TEST_STORE / SPEAR_TEST_DIR is set).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.request


def _from_tests():
    if os.environ.get("SPEAR_TEST_STORE") or os.environ.get("SPEAR_TEST_DIR"):
        return True
    try:
        entry = os.path.abspath(sys.argv[0])
    except (IndexError, TypeError, ValueError):
        return False
    return os.path.basename(os.path.dirname(entry)) == "tests"


TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
if _from_tests() and not os.environ.get("SPEAR_LIVE_STORE"):
    TOKEN = ""
BASE = "https://vercel.com/api/blob"
PREFIX = "spearupgrade/"
DATA_DIR = os.environ.get("SPEAR_TEST_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
SESSION_PREFIX = "sp1"

_cache = {}
_url_cache = {}
CACHE_TTL = 20


class StoreBusy(Exception):
    """The shared store could not be read. Callers must not write blind."""


TOKEN_DAYS = 30


def _req(method, url, body=None, extra=None):
    import uuid
    headers = {"Authorization": "Bearer " + TOKEN,
               "Content-Type": "application/json",
               "x-api-version": "13",
               "x-api-blob-request-id": f"{int(time.time())}:{uuid.uuid4().hex[:8]}",
               "x-api-blob-request-attempt": "0"}
    headers.update(extra or {})
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def _blob_url(name):
    """Returns (found, url). found=False with url None means the list API
    worked but the blob simply does not exist yet (use the default)."""
    if name in _url_cache:
        return True, _url_cache[name]
    import urllib.parse
    listed_ok = False
    for _ in range(4):
        q = urllib.parse.urlencode({"prefix": PREFIX + name, "limit": 10})
        try:
            data = json.loads(_req("GET", BASE + "/?" + q))
            listed_ok = True
        except Exception:
            data = {}
        for b in data.get("blobs", []):
            if b.get("pathname") == PREFIX + name:
                _url_cache[name] = b.get("downloadUrl") or b.get("url")
                return True, _url_cache[name]
        time.sleep(0.4)
    return listed_ok, None


def _local(name):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise StoreBusy(name) from e


def load_json(name, default, fresh=False, strict=False):
    hit = _cache.get(name)
    if not fresh and hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    if TOKEN:
        failed = False
        try:
            if fresh:
                _url_cache.pop(name, None)
            found, url = _blob_url(name)
            if url:
                sep = "&" if "?" in url else "?"
                val = json.loads(_req("GET", f"{url}{sep}cb={int(time.time() * 1000)}"))
                _cache[name] = (time.time(), val)
                return val
            if found:
                val = default
                _cache[name] = (time.time(), val)
                return val
            failed = True
        except Exception:
            failed = True
        if hit:
            return hit[1]
        if strict and failed:
            raise StoreBusy(name)
        return default
    try:
        val = _local(name)
    except StoreBusy:
        if hit:
            return hit[1]
        if strict:
            raise
        return default
    if val is None:
        return default
    _cache[name] = (time.time(), val)
    return val


def save_json(name, obj):
    body = json.dumps(obj).encode()
    if TOKEN:
        ok = False
        try:
            import urllib.parse
            q = urllib.parse.urlencode({"pathname": PREFIX + name})
            resp = json.loads(_req("PUT", BASE + "/?" + q, body, {
                "x-vercel-blob-access": "private",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-content-type": "application/json"}))
            if resp.get("downloadUrl") or resp.get("url"):
                _url_cache[name] = resp.get("downloadUrl") or resp.get("url")
                ok = True
        except Exception:
            ok = False
        if ok:
            _cache[name] = (time.time(), obj)
        return ok
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = os.path.join(DATA_DIR, name + ".tmp")
        with open(tmp, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, os.path.join(DATA_DIR, name))
    except OSError:
        return False
    _cache[name] = (time.time(), obj)
    return True


def clean_str(v, limit):
    v = str(v or "")[:limit]
    return "".join(c for c in v if c.isprintable())


def clamp_int(v, lo, hi, default=0):
    try:
        return min(hi, max(lo, int(v)))
    except (TypeError, ValueError):
        return default


def score_cap(lvl, kills):
    """Generous anti-spoof ceiling for a client-reported spear score."""
    return lvl * 500 + kills * 50 + 20000


def hash_pw(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"),
                               bytes.fromhex(salt_hex), 200_000).hex()


_skey = None


def _session_key():
    global _skey
    if _skey is None:
        raw = SESSION_SECRET
        if not raw and TOKEN:
            raw = TOKEN + "|spearupgrade.session.v1"
        if not raw:
            raw = _key_file()
        _skey = hashlib.sha256(raw.encode("utf-8")).digest()
    return _skey


def _key_file():
    path = os.path.join(DATA_DIR, "session.key")
    try:
        with open(path) as f:
            val = f.read().strip()
        if val:
            return val
    except OSError:
        pass
    val = secrets.token_hex(32)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(val)
    except OSError:
        pass
    return val


def _b64(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def public_profile(user, acct):
    return {"user": user,
            "runs": acct.get("runs", 0), "best": acct.get("best", 0)}


def mint_token(user, tv=0):
    payload = {"u": str(user), "tv": int(tv or 0),
               "e": int(time.time()) + TOKEN_DAYS * 86400}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_session_key(), f"{SESSION_PREFIX}.{body}".encode(),
                   hashlib.sha256).hexdigest()
    return f"{SESSION_PREFIX}.{body}.{sig}"


def read_session(token):
    if not token:
        return None
    if not token.startswith(SESSION_PREFIX + "."):
        return None
    try:
        _, body, sig = token.split(".")
        want = hmac.new(_session_key(), f"{SESSION_PREFIX}.{body}".encode(),
                        hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, want):
            return None
        p = json.loads(_b64d(body))
        if int(p.get("e") or 0) < time.time():
            return None
        user = str(p.get("u") or "")
        if not user:
            return None
        return {"user": user, "tv": int(p.get("tv") or 0)}
    except (ValueError, TypeError):
        return None


def auth_user(headers):
    auth = headers.get("authorization", "") or headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    sess = read_session(auth[7:].strip())
    return sess["user"] if sess else None


def token_current(headers, acct):
    auth = headers.get("authorization", "") or headers.get("Authorization", "")
    sess = read_session(auth[7:].strip()) if auth.startswith("Bearer ") else None
    if not sess:
        return False
    return sess["tv"] == int(acct.get("tokv", 0))


def load_account(user, strict=False):
    acct = load_json("accounts.json", {}, strict=strict).get(user)
    if acct is not None:
        return acct
    for delay in (0.3, 0.7, 1.2):
        time.sleep(delay)
        acct = load_json("accounts.json", {}, fresh=True, strict=strict).get(user)
        if acct is not None:
            return acct
    return None


def auth_account(headers, user, strict=False):
    acct = load_account(user, strict=strict)
    if acct is None:
        return None
    if token_current(headers, acct):
        return acct
    for delay in (0.3, 0.7, 1.2):
        time.sleep(delay)
        acct = load_json("accounts.json", {}, fresh=True, strict=strict).get(user)
        if acct is not None and token_current(headers, acct):
            return acct
    return None
