#!/usr/bin/env python3
"""Unit checks for api/_store.py pure helpers (offline, temp local store)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["SPEAR_TEST_DIR"] = tempfile.mkdtemp(prefix="spear-unit-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
import _store as S  # noqa: E402

# clamp / clean helpers
assert S.clamp_int("abc", 0, 5) == 0
assert S.clamp_int(99, 0, 5) == 5
assert S.clamp_int("3", 0, 5) == 3
assert S.clean_str("<b>x</b>", 80) == "<b>x</b>"  # escaping is the client's job
assert S.clean_str("a\x00b", 80) == "ab"

# score cap must comfortably exceed legit play but bound spoofing
# legit score = lvl*100 + kills  →  level-25 run ≈ 2500-3000
assert S.score_cap(25, 40) > 3000, S.score_cap(25, 40)
assert S.score_cap(1, 0) > 100
assert S.score_cap(1, 0) < 100000

# sessions round-trip without any store read
tok = S.mint_token("probe_user", 0)
assert tok.startswith("sp1.")
sess = S.read_session(tok)
assert sess and sess["user"] == "probe_user"
assert S.read_session("bogus") is None
assert S.read_session(tok + "tampered") is None

# profiles never leak hashes
acct = {"hash": "SECRET", "salt": "SECRET", "runs": 3, "best": 99}
prof = S.public_profile("u", acct)
assert "hash" not in prof and "salt" not in prof
assert prof["best"] == 99 and prof["runs"] == 3

# local save/load round trip
assert S.save_json("probe.json", {"a": [1, 2, 3]}) is True
assert S.load_json("probe.json", None) == {"a": [1, 2, 3]}

print("store-unit OK")
