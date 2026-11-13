# Test report

Run in the build sandbox: Python 3.12, Node 22, headless Chromium (desktop engine, phone-size viewports).
There was **no network access** and FastAPI/pydantic/uvicorn could not be installed.

## What was tested, and how

| Area | Method | Result |
|---|---|---|
| Registry (38 calculators, all modes and fields) | generated from the real pages with a browser; validated by 10 tests (unknown tools/modes, bad numbers, injection, text fields, unit selectors, URL format) | pass |
| Rule router, English + Hindi, unit conversion | 14 targeted tests plus 50 diverse questions | pass |
| Safety of rules | tests that an unconvertible unit (for example 36 km/h) is **left empty, never guessed**, and that selectors (km, h, mL) are set instead | pass |
| JavaScript offline engine vs Python rules | the same 50 questions through both, comparing tool, mode, inputs, selectors, missing fields, confidence, shortlist scores and formula-finder order. A **negative test** (deliberately wrong expectations) confirmed the check can fail | **50/50 identical** |
| Output guard | accepts rounding, rejects invented numbers, links, e-mails, wrong script (Hindi/English) | pass |
| Quota | daily limits, refunds, next-day reset, per-minute limit not burning credits, premium reserve inside the global budget, anonymous per-IP cap, memory **and** SQLite stores | pass |
| Provider chain | daily quota skip until Pacific midnight (clock injected), `Retry-After`, circuit breaker, auth disable, fall-through to a second provider | pass |
| Gemini + OpenAI-compatible providers over **real HTTP** | local fake servers imitating the documented response and error shapes: success, key in header (not URL), request shape, daily vs per-minute 429 (with `retryDelay`), 503, 403, bad-key 400, blocked, empty, timeout, unreachable | pass |
| Identity | anonymous ids, dev tier header only in `ENV=dev`, JWT valid / expired / forged / garbage, tier claim, proxy IP handling | pass |
| Service behaviour | rules-only answers cost 0 AI calls; AI routes validated and invented numbers dropped; tool outside a strong shortlist refused; explanations pass or fall back; guard failures refund; quota exhaustion degrades with a notice and **does not hammer the provider**; Hindi; premium vs anonymous; input validation; prompt-injection text kept as data; `/v1/health` has no secrets | pass |
| HTTP server (real sockets) | health, route, explain, formula, usage, 400/401/404/413, CORS preflight and allowlist, quota over HTTP, static file serving incl. path-traversal attempts | pass |
| **Backend total** | `python -m unittest discover -s tests -t .` | **80 tests: 77 pass, 3 skipped** (the 3 are the FastAPI-only tests) |
| `app/main.py` logic | run against a minimal stand-in for FastAPI (routes, body-size limit, bad JSON, auth errors) | works; **this is not proof it works on real FastAPI** |
| Browser end-to-end | real page + real dev server + fake Gemini behind the real provider chain | **38/38 checks** (below) |

### Browser end-to-end checks (38)
Offline mode: banner; routing; running the real calculator in a hidden frame and reading 15 N; frame removed after;
template explanation, next steps (related calculators, chapter guide), numbered steps; Hindi UI and Hindi question
and Hindi explanation; persistence; unmatched question; Formula Finder; link safety; AI checkbox hidden offline.
Online mode: usage meter; **no AI call for a confident rules question**; AI explanation labelled as AI; credit
deducted; AI text with invented numbers rejected and **refunded**; AI routing validated; AI-invented value never shown;
provider quota exhausted gives a friendly notice and **no further provider calls**; calculators still work.
Safety: hostile question and hostile AI text never become markup; a hostile backend cannot inject `javascript:` links.
Fallback: unreachable backend still works. Layout at 320, 360 and 412 px: no sideways scroll, tap targets >= 40 px.
Regression: the existing calculator and share links still work, the homepage does not mention the prototype.

### Spck-like situations (approximate, not Spck itself)
* Plain static web server: routing works **and** the real calculator result appears in the page.
* Opened from `file://`: routing and templates work; the in-page calculator run falls back to an
  "Open full calculator" link (browsers block reading another file's page); no errors.

## Bugs found by this testing and fixed during the build
* Registry labels were wrong for pages with two inputs in one container (both showed "Mass").
* A number's label leaked the previous number's unit, so molarity picked the wrong mode.
* Unit-less labels let "36 km/h" or "120 km" slip through unconverted; now converted, set on the selector, or skipped.
* "Launched" matched the label "Launch Angle"; acceleration could be taken as a mass.
* Page example values were wrongly treated as defaults; only gravity is a true default.
* When no keyword matched, AI was never consulted; and a weak keyword shortlist rejected correct AI answers.
* A low-confidence rules guess was shown as a prefilled route; now only offered as suggestions.
* The AI checkbox stayed visible offline (CSS overrode `hidden`); example chips were below a comfortable tap size.

## NOT tested (please treat as unverified)

* **Real FastAPI/uvicorn/pydantic.** `app/main.py` compiles and its logic ran against a stand-in only. Run
  `tests/test_fastapi.py` on a PC first (see DEPLOYMENT.md).
* **The real Gemini API** (or any real AI host): request/response shapes follow Google's documented format as seen in
  public documentation and were tested only against my fake server. Model names, free quotas and error wording may differ.
* **Real Android devices**, Android Chrome, Samsung Internet, Firefox, Safari. Chromium here is a desktop engine.
  The page uses regex look-behind, which very old browsers (for example Safari before 16.4) do not support.
* **Spck Editor's Preview** itself.
* **Render, Netlify (for this page) and real cold starts**; real proxy headers for `TRUST_PROXY_HOPS`.
* **Real login tokens** (Supabase/Firebase): JWT verification is tested with tokens made by PyJWT only.
* **Load and concurrency**, long-running memory use, database failures.
* **Quality of real AI answers**, especially Hindi: the guard checks numbers, links and script, not whether the
  explanation is correct or well written. A teacher should review a sample before launch.
* **Accessibility audit** (screen readers), **legal/privacy review**.
* Rule coverage is good for the common phrasings tested, not for every way students write; harder phrasings go to AI
  by design. Centre-of-mass is excluded from rule extraction because its fields have identical labels.
