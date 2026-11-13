# Suno Saathi Tools: Magic Layer prototype

A separate working prototype that sits next to your existing website. It adds:

* **Ask a problem** (English or Hindi): finds the right calculator, fills in your numbers, runs the *real* calculator.
* **Explain result** and **Step-by-step**: AI-written when AI is available, a clear template when it is not.
* **Formula Finder**: which formula fits, with a link to the calculator and chapter guide.
* **Python FastAPI backend** with an AI-provider abstraction (Gemini + any OpenAI-compatible host), daily credits,
  per-minute limits, premium reserve, automatic quota-exhaustion handling, and login/subscription hooks.

**The calculators keep working with no AI, no backend and no internet.** The existing website is untouched
except for one new folder, `website/magic/` (not linked from the site, `noindex`).

## What is in the ZIP

```
website/        your existing site, unchanged, plus website/magic/  (the prototype page)
backend/        FastAPI app (app/), zero-install dev server (dev_server.py), unit tests (tests/)
shared/         strings.json (English + Hindi) and generated nlp.json
tools/          build_registry.js, sync_data.py, run_tests.sh
tests_frontend/ cross-check of the JavaScript engine against Python, and browser end-to-end tests
docs/           ARCHITECTURE.md  DEPLOYMENT.md  FREE_TIERS.md  TEST_REPORT.md
```

## Try it on your Android phone (Spck), no backend

1. Open the **`website/`** folder in Spck Editor as a project.
2. Preview `magic/index.html`.
3. Tap an example, press **Ask**, then **Run the calculator**, **Explain result**, **Step-by-step**.
   Switch **EN / हिं**. The status line says "Offline demo: no AI": that is expected.

If Spck serves the files in a way that stops the page from reading the calculator, you will see an
"Open full calculator" link instead of the in-page result. (I could not test Spck itself.)

## Try it with a backend on a PC / Termux (still free, no keys)

```
cd backend
python dev_server.py --site ../website --mock --port 8000
# open http://localhost:8000/magic/?api=http://localhost:8000
```
`--mock` is a fake AI so you can see credits, AI labels and fallbacks.

## Go live (separate from the website)

Follow `docs/DEPLOYMENT.md` (Render free tier + a Gemini key kept only on the server), then put the backend address
in `website/magic/config.js`. Free-tier limits and catches are in `docs/FREE_TIERS.md`.

## Tests

`sh tools/run_tests.sh` runs everything your machine supports. Results and, importantly, **what was not tested** are
in `docs/TEST_REPORT.md`. Short version: the logic is heavily tested; real FastAPI, the real Gemini API, real Android
devices and Spck Preview were not available and are untested.

## Design in one paragraph

Calculators calculate; rules route; AI only explains. Rules and templates are free and always available. AI is used
only when rules are unsure or an explanation is requested, costs credits that are refunded on failure, and every AI
answer is validated (real calculator and field names only, no invented numbers, no links, right language) before a
student sees it. If AI is over quota or down, students get the standard explanation automatically. See
`docs/ARCHITECTURE.md`.
