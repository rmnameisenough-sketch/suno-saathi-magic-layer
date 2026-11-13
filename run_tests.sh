#!/bin/sh
# Runs every test that works with what you have installed. From the project root:  sh tools/run_tests.sh
set -e
cd "$(dirname "$0")/.."
echo "== backend unit + HTTP tests (standard library only) =="
( cd backend && python3 -m unittest discover -s tests -t . )
if command -v node >/dev/null 2>&1; then
  echo "== JavaScript engine vs Python rules (needs Node) =="
  python3 - <<'PY'
import json, sys
sys.path.insert(0, "backend")
from app.registry import Registry
from app.rules import RuleEngine
E = RuleEngine(Registry.load("backend/app/data/registry.json"))
out = []
for q in json.load(open("tests_frontend/questions.json", encoding="utf-8")):
    rr = E.route(q); r = rr.route
    out.append({"q": q, "conf": rr.confidence, "short": rr.shortlist,
                "route": None if not r else {"tool": r.tool_id, "mode": r.mode, "inputs": r.inputs, "selects": r.selects, "missing": r.missing, "query": r.query},
                "formulas": [f["tool_id"] + "|" + f["formula"][:40] for f in E.find_formulas(q, 6)]})
json.dump(out, open("/tmp/py_expected.json", "w"), ensure_ascii=False)
PY
  node tests_frontend/crosscheck.js /tmp/py_expected.json
fi
if python3 -c "import playwright" >/dev/null 2>&1; then
  echo "== browser end-to-end tests (needs playwright + chromium) =="
  python3 tests_frontend/e2e_browser.py
else
  echo "(skipping browser tests: playwright not installed)"
fi
