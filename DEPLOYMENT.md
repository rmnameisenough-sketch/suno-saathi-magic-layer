# Deploying the backend (separate from the website)

The website stays on Netlify exactly as today. The backend is a separate small Python service. Until it is
deployed, the Magic Layer page works in **offline demo mode** (rules + templates, no AI).

> **Honest status:** `app/main.py` (the FastAPI layer) could not be run in the environment where this was built
> (FastAPI could not be installed there). Its logic was exercised against a stand-in, and the same service code is
> fully tested through the zero-dependency dev server. **Do the "first run check" in step 2 before going public.**

## 0. Try everything locally first (no accounts, no keys)

On a PC or in Termux with Python 3.10+ (built and tested on 3.12):

```
cd backend
python dev_server.py --site ../website --mock --port 8000
```
Open `http://localhost:8000/magic/?api=http://localhost:8000`. `--mock` turns on a fake AI so you can see the
"AI" path, the credits meter and the fallbacks. Without `--mock` the server runs with AI off (templates only).

## 1. Get an AI key (optional, free tier)

1. Open Google AI Studio and create an API key for the Gemini API.
2. In AI Studio check which model is available on the free tier for your project and note its name.
3. **Never** put the key in the website, in `config.js`, or in GitHub. It goes only into the backend host's environment
   variables (step 3).

## 2. First run check with real FastAPI (on a PC, 5 minutes)

```
cd backend
pip install -r requirements.txt httpx
python -m unittest discover -s tests -t . -v        # includes tests/test_fastapi.py, skipped until FastAPI is installed
uvicorn app.main:app --port 8000
```
Visit `http://localhost:8000/v1/health` (should show `"status": "ok"`). If anything in `test_fastapi.py` fails,
fix it before deploying; the rest of the logic is already covered by 77 other passing tests.

## 3. Deploy on Render (free web service)

Render's pages change, so follow its current screens; the values you need are:

| Setting | Value |
|---|---|
| Source | the GitHub repo that contains the `backend/` folder |
| Root directory | `backend` |
| Runtime | Python (version 3.10 or newer; check Render's current default) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Free |

Environment variables (Render dashboard, **Environment** page):

| Name | Value |
|---|---|
| `ENV` | `prod` |
| `CORS_ORIGINS` | `https://sunosaathilabs.netlify.app` |
| `TRUST_PROXY_HOPS` | `1` (Render sits in front; confirm the visitor IP really arrives as the last `X-Forwarded-For` entry) |
| `AI_PROVIDERS` | `gemini` |
| `GEMINI_API_KEY` | your key (mark as secret) |
| `GEMINI_MODEL` | the model name from step 1 |
| `GLOBAL_DAILY` | a number **below** your provider's daily free allowance |

Everything else has safe defaults (see `backend/.env.example`).

Know the free-tier behaviour (details in `FREE_TIERS.md`): the service **sleeps** after idle time and takes about a
minute to wake; the page shows a message and falls back to built-in rules meanwhile. Usage counters live in memory
and **reset when the service restarts**, so daily limits are approximate until you add a database-backed store.

## 4. Connect the website

1. Edit `website/magic/config.js` and set `API_BASE` to your Render address (no trailing slash).
   (To test first without editing: open `/magic/?api=https://your-service.onrender.com`; the address is remembered in
   that browser. `/magic/?api=` forgets it.)
2. Commit and push; Netlify redeploys.
3. Open `/magic/` on your phone. The status line should change from "Offline demo" to "AI uses left today: N".

## 5. Checklist before showing it to real students

* [ ] `ENV=prod`, exact `CORS_ORIGINS`, `GLOBAL_DAILY` below the provider quota.
* [ ] Test the provider failure path on purpose: temporarily set a wrong `GEMINI_API_KEY`; the page must still work
      (templates) and `/v1/health` should show the provider as `disabled`.
* [ ] Privacy Policy updated: questions are sent to an AI provider; free-tier terms; under-18 rules. Decide whether to
      keep AI for logged-in users only.
* [ ] Decide who may call `/v1/health` (it shows provider state and counters, no secrets).
* [ ] Remove `noindex`, add the link and the sitemap entry **only** when you are ready to launch.
* [ ] Re-test on a real Android phone (Chrome) and with Hindi questions.

## 6. Android and Spck workflow

* In Spck open the **`website/`** folder as the project. Preview `magic/index.html` (or open `index.html` and
  edit the address to `magic/`).
* In Spck Preview the page runs in **offline demo mode**. Routing, formula finder, templates, Hindi/English all work.
  "Run the calculator" needs the page and the calculators on the same web address; if Spck serves them differently the
  page shows an "Open full calculator" link instead (I could not test Spck itself).
* Edit `magic/magic.js`, `magic.css`, `config.js` freely. **Do not hand-edit** `magic-data.js` (generated).
* Commit and push from Spck's Git screen; Netlify publishes.
* Rebuilding the data after you change a calculator needs Node/Playwright (`tools/build_registry.js`), so do that on a
  PC and commit the regenerated files.
* The backend is edited in the `backend/` folder the same way; Render redeploys on each push.
