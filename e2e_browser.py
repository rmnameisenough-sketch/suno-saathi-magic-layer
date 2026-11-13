"""End-to-end tests in a real (headless Chromium) browser.

    python3 tests_frontend/e2e_browser.py

Needs: python3, playwright (pip install playwright; playwright install chromium).
It starts the dev server (which serves ../website and the API) and a fake Gemini server, then drives
the Magic Layer page. Chromium here is a DESKTOP engine at phone-size screens: it is not Android Chrome,
and it is not Spck's preview.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from playwright.sync_api import sync_playwright          # noqa: E402

from app.providers.gemini import GeminiProvider           # noqa: E402
from tests.fake_servers import FakeAI                     # noqa: E402
from tests.test_dev_server import Server                  # noqa: E402

SITE = ROOT / "website"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (("  | " + detail) if detail and not ok else ""))


def new_page(browser, base, query="", width=390, lang_storage=None):
    ctx = browser.new_context(viewport={"width": width, "height": 800}, service_workers="block")
    if lang_storage:
        ctx.add_init_script(f"try{{localStorage.setItem('magicLang','{lang_storage}')}}catch(e){{}}")
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append("console: " + m.text) if m.type == "error" and "favicon" not in m.text else None)
    page.dialogs = []
    page.on("dialog", lambda d: (page.dialogs.append(d.message), d.dismiss()))
    page.goto(f"{base}/magic/{query}")
    page.wait_for_selector("#mgAsk")
    return ctx, page


def ask(page, text):
    page.fill("#mgQuestion", text)
    page.click("#mgAsk")
    page.wait_for_function("document.querySelector('#mgOut .mg-card') && !document.querySelector('#mgOut .mg-spin')", timeout=25000)


def out_text(page):
    return page.inner_text("#mgOut")


def run_calc(page):
    page.click("#mgRun")
    page.wait_for_selector("#mgResultCard", timeout=15000)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ============================================================ A. offline demo mode (no backend at all)
        off = Server(site=SITE, providers=[])
        ctx, p = new_page(browser, off.base)
        check("A1 offline banner shown", "Offline demo" in p.inner_text("#mgStatus"), p.inner_text("#mgStatus"))
        ask(p, "Find the force when mass is 5 kg and acceleration is 3 m/s2")
        txt = out_text(p)
        check("A2 routes to Force Calculator with values", "Force Calculator" in txt and "5" in txt and "3" in txt and "built-in rules" in txt, txt[:200])
        run_calc(p)
        res = p.inner_text("#mgResultCard pre")
        check("A3 real calculator ran in hidden frame (15 N)", "15" in res and "N" in res, res)
        check("A4 hidden frame removed afterwards", p.locator("iframe").count() == 0)
        p.click("#mgResultCard button:has-text('Explain result')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=8000)
        txt = out_text(p)
        check("A5 template explanation, no AI", "Standard explanation" in txt and "Formula" in txt and "Mass (kg) = 5" in txt, txt[-400:])
        check("A6 next steps: related calculators + chapter guide", "Related calculators" in txt and "Chapter guide" in txt)
        p.click("#mgResultCard button:has-text('Step-by-step')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=5 && !document.querySelector('#mgOut .mg-spin')", timeout=8000)
        check("A7 numbered steps", "1." in out_text(p) and "How the calculator worked it out" in out_text(p))

        # Hindi
        p.click("#mgLangHi")
        check("A8 UI switches to Hindi", p.inner_text("#mgAsk") == "पूछें" and "मैजिक लेयर" in p.inner_text("#mgTitle"))
        check("A9 Hindi persisted after reload", (p.reload(), p.wait_for_selector("#mgAsk"), p.inner_text("#mgAsk"))[2] == "पूछें")
        ask(p, "बल निकालो जब द्रव्यमान 5 kg और त्वरण 3 m/s2 है")
        txt = out_text(p)
        check("A10 Hindi question routes (Force Calculator, values 5 and 3)", "Force Calculator" in txt and "5" in txt and "3" in txt, txt[:200])
        run_calc(p)
        p.click("#mgResultCard button:has-text('उत्तर समझाएँ')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=8000)
        check("A11 Hindi template explanation", "सूत्र" in out_text(p) and "मानक व्याख्या" in out_text(p), out_text(p)[-300:])
        p.click("#mgLangEn")

        # no match, formula finder
        ask(p, "hello world")
        check("A12 unmatched question gives helpful message", "could not match" in out_text(p))
        p.click("#tabFormula")
        p.fill("#mgFormulaQ", "pressure from force and area")
        p.click("#mgFind")
        p.wait_for_selector("#mgOut .mg-formula", timeout=8000)
        check("A13 Formula Finder lists Pressure calculator first", "Pressure Calculator" in out_text(p).split("Use this calculator")[0], out_text(p)[:200])
        links = p.eval_on_selector_all("#mgOut a", "els=>els.map(a=>a.getAttribute('href'))")
        check("A14 all links are same-site calculator/chapter paths", links and all(l.startswith("../physics/") or l.startswith("../chemistry/") or l.startswith("../chapters/") for l in links), str(links))
        check("A15 AI checkbox hidden when offline", not p.is_visible("#mgAiRow"))
        check("A16 no JS errors (offline mode)", not p.errors, "; ".join(p.errors))
        ctx.close()

        # ============================================================ B. online mode through the real provider chain (fake Gemini)
        fake = FakeAI()
        gem = GeminiProvider("test-key", "gemini-test", fake.base, 4.0)
        on = Server(site=SITE, providers=[gem], anon_daily=6)
        ctx, p = new_page(browser, on.base, f"?api={on.base}")
        p.wait_for_function("document.querySelector('#mgStatus').innerText.includes('AI uses left')", timeout=8000)
        check("B1 online: usage meter shows AI uses left", "6" in p.inner_text("#mgStatus"), p.inner_text("#mgStatus"))
        n0 = len(fake.requests)
        ask(p, "Find the force when mass is 5 kg and acceleration is 3 m/s2")
        check("B2 confident rules question uses NO AI call", len(fake.requests) == n0 and "built-in rules" in out_text(p))
        run_calc(p)
        fake.text = "The calculator gave 15 N because 5 times 3 is 15. Check your units."
        p.click("#mgResultCard button:has-text('Explain result')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=10000)
        check("B3 AI explanation shown and labelled as AI", "Written by AI" in out_text(p) and "because 5 times 3" in out_text(p), out_text(p)[-300:])
        check("B4 credit deducted (6 -> 5)", "5" in p.inner_text("#mgStatus"), p.inner_text("#mgStatus"))
        fake.text = "The force is 15 N, which equals 1530 kgf on Jupiter."
        p.click("#mgResultCard button:has-text('Step-by-step')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=5 && !document.querySelector('#mgOut .mg-spin')", timeout=10000)
        txt = out_text(p)
        check("B5 AI text with invented numbers rejected, template shown with notice", "1530" not in txt and "number check" in txt and "Standard explanation" in txt, txt[-500:])
        check("B6 rejected AI call was refunded (still 5)", "5" in p.inner_text("#mgStatus"), p.inner_text("#mgStatus"))

        # AI routing for a question the rules cannot place
        fake.route_json = json.dumps({"tool_id": "force-calculator", "mode": "F", "inputs": {"x": 5, "y": 3}, "confidence": 0.9})
        ask(p, "a 5 kg block speeds up by 3 every second, how big is the push")
        txt = out_text(p)
        check("B7 AI routing for a hard question, validated", "Force Calculator" in txt and "Matched with AI help" in txt, txt[:300])
        fake.route_json = json.dumps({"tool_id": "force-calculator", "mode": "F", "inputs": {"x": 5, "y": 999}})
        ask(p, "a 5 kg block is pushed with a mystery acceleration, how big is the push")
        txt = out_text(p)
        check("B8 AI-invented number (999) never reaches the page", "999" not in txt, txt[:300])
        check("B9 missing value is reported, no Run button", p.locator("#mgRun").count() == 0 and "some values are missing" in txt)

        # provider quota exhausted -> automatic fallback, then no hammering
        fake.mode = "quota_daily"
        p.click("#tabAsk")
        ask(p, "Find the force when mass is 5 kg and acceleration is 3 m/s2"); run_calc(p)
        p.click("#mgResultCard button:has-text('Explain result')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=10000)
        txt = out_text(p)
        check("B10 provider quota exhausted: standard explanation + friendly notice", "Standard explanation" in txt and "provider limit reached" in txt, txt[-400:])
        calls = len(fake.requests)
        for _ in range(3):
            ask(p, "Find the force when mass is 5 kg and acceleration is 3 m/s2"); run_calc(p)
            p.click("#mgResultCard button:has-text('Explain result')")
            p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=10000)
        check("B11 provider is not called again while its quota is exhausted", len(fake.requests) == calls, f"{len(fake.requests)} vs {calls}")
        check("B12 calculators still work with AI down", "15" in p.inner_text("#mgResultCard pre"))
        check("B13 no JS errors (online mode)", not p.errors, "; ".join(p.errors))
        ctx.close()

        # ============================================================ C. safety
        fake.mode = "ok"
        fake.text = '<img src=x onerror="window.__xss=1"> The calculator gave 15 N. <script>window.__xss=2</script>'
        ctx, p = new_page(browser, on.base, f"?api={on.base}")
        ask(p, "<img src=x onerror=window.__xss=3> force when mass is 5 kg and acceleration is 3 m/s2")
        run_calc(p)
        p.click("#mgResultCard button:has-text('Explain result')")
        p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=10000)
        check("C1 no HTML from question or AI is ever injected as markup",
              p.locator("#mgOut img").count() == 0 and p.locator("#mgOut script").count() == 0 and p.evaluate("window.__xss === undefined"))
        ctx.close()

        class Evil(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _o(self):
                self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*")
            def do_OPTIONS(self):
                self.send_response(204); self._o(); self.end_headers()
            def do_GET(self):
                b = json.dumps({"status": "ok", "remaining": 3}).encode(); self.send_response(200); self._o()
                self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = {"ok": True, "source": "ai", "notice": "<b>x</b>", "route": {"tool_id": "force-calculator", "mode": "F", "inputs": {"x": 5, "y": 3, "evil": "1"},
                        "url": "javascript:window.__pwned=1", "query": "x=1&evil=<img>", "tool_name": "<img src=x>"}, "suggestions": [{"tool_id": "force-calculator", "name": "n", "url": "javascript:alert(1)"}]}
                b = json.dumps(body).encode(); self.send_response(200); self._o()
                self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
        evil = ThreadingHTTPServer(("127.0.0.1", 0), Evil); threading.Thread(target=evil.serve_forever, daemon=True).start()
        ctx, p = new_page(browser, on.base, f"?api=http://127.0.0.1:{evil.server_address[1]}")
        p.wait_for_timeout(600)
        ask(p, "anything about force")
        hrefs = p.eval_on_selector_all("#mgOut a", "els=>els.map(a=>a.getAttribute('href'))")
        check("C2 hostile backend cannot inject javascript: links or markup (page rebuilds route from its own registry)",
              all(not h.startswith("javascript") for h in hrefs) and p.locator("#mgOut img").count() == 0 and "pwned" not in p.content()
              and any("../physics/force-calculator.html?mode=F&x=5&y=3" == h for h in hrefs), str(hrefs))
        ctx.close(); evil.shutdown()

        # ============================================================ D. backend unreachable -> graceful fallback
        ctx, p = new_page(browser, on.base, "?api=http://127.0.0.1:9")
        p.wait_for_function("document.querySelector('#mgStatus').innerText.includes('Offline demo')", timeout=30000)
        ask(p, "pressure when force is 100 N on area 2 m2")
        check("D1 unreachable backend: page still works with built-in rules", "Pressure Calculator" in out_text(p), out_text(p)[:200])
        check("D2 forgetting the backend address works", (p.goto(f"{on.base}/magic/?api="), p.wait_for_selector("#mgAsk"), p.evaluate("localStorage.getItem('magicApi')"))[2] is None)
        ctx.close()

        # ============================================================ E. mobile layout
        for width in (320, 360, 412):
            ctx, p = new_page(browser, off.base, width=width)
            ask(p, "Find the force when mass is 5 kg and acceleration is 3 m/s2"); run_calc(p)
            p.click("#mgResultCard button:has-text('Explain result')")
            p.wait_for_function("document.querySelectorAll('#mgOut .mg-card').length>=3 && !document.querySelector('#mgOut .mg-spin')", timeout=8000)
            over = p.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            small = p.evaluate("[...document.querySelectorAll('button,a.mg-btn')].filter(b=>b.offsetParent&&b.getBoundingClientRect().height<40).map(b=>b.textContent.trim())")
            check(f"E {width}px: no sideways scroll, tap targets >= 40px", over <= 1 and not small, f"overflow={over} small={small}")
            ctx.close()

        # ============================================================ F. existing site untouched and still working
        ctx, p = new_page(browser, off.base)
        p.goto(f"{off.base}/physics/force-calculator.html?mode=F&x=5&y=3"); p.wait_for_timeout(500)
        check("F1 existing calculator + share link still work", "15" in p.inner_text("#result"))
        p.goto(f"{off.base}/index.html"); p.wait_for_selector("h1")
        check("F2 homepage unaffected (no link to prototype)", "magic" not in p.content().lower().replace("magical", ""))
        ctx.close()

        browser.close()
    off.close(); on.close(); fake.close()
    bad = [r for r in RESULTS if not r[1]]
    print(f"\nE2E: {len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
