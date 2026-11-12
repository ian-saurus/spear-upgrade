#!/bin/bash
# Run all spear-upgrade checks: API compile, store units, API roundtrip, game JS syntax.
set -e
cd "$(dirname "$0")/.."
python3 -m py_compile api/*.py tests/*.py && echo "api-compile OK"
python3 tests/store_unit.py
python3 tests/api_roundtrip.py
python3 tests/redis_backend.py
python3 -c "import re; html=open('index.html').read(); m=re.search(r'<script>(.*)</script>', html, re.S); open('/tmp/opencode/spear-check.js','w').write(m.group(1))"
node --check /tmp/opencode/spear-check.js && echo "game-js OK"
