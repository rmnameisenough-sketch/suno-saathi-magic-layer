# Magic Layer: architecture

Status: working prototype. Everything described here exists in this ZIP unless marked **(future)**.

## 1. The one rule

> **Calculators calculate. Rules route. AI only explains, and only when it is allowed and available.**

* The numbers always come from the existing calculator pages (their JavaScript is untouched).
* A free, deterministic layer (rules + templates) handles as much as possible and works with no AI and no internet.
* AI is a bonus layer. Every AI answer is validated before a student sees it. If AI is over quota, down, or fails
  a check, the student still gets a useful (template) answer. **The site never depends on AI.**

## 2. Big picture

```
 Student's phone (browser)                          Cloud (free tier to start)
┌───────────────────────────────────┐            ┌─────────────────────────────────────────────┐
│ website/ (Netlify, static)        │            │ backend/ (Python FastAPI)                   │
│  ├─ physics/ chemistry/ chapters/ │            │  POST /v1/route    GET /v1/usage            │
│  │    existing calculators        │   HTTPS    │  POST /v1/explain  GET /v1/health           │
│  └─ magic/                        │ ─────────▶ │  POST /v1/formula                           │
│      magic.js   page logic        │  JSON      │                                             │
│      magic-engine.js  offline     │ ◀───────── │  identity ─▶ quota ─▶ service ─▶ providers  │
│        rules (no AI, no network)  │            │                      │            │         │
│  runs the REAL calculator in a    │            │                   rules/guards  Gemini ─┐   │
│  hidden frame and reads #result   │            │                   templates     OpenAI- ├─▶ AI│
└───────────────────────────────────┘            │                                 compat ─┘   │
   no keys, no secrets                           └─────────────────────────────────────────────┘
                                                      API keys live ONLY here (environment variables)
```

If the backend is missing, asleep or erroring, `magic.js` switches to `magic-engine.js` (the same rules, in the
browser) and keeps working. That is also what runs in Spck Preview.

## 3. Request flows

### Ask a problem  (`POST /v1/route`)
1. **Rules first** (`rules.py`): keyword shortlist, then pick calculator + mode and match numbers to fields by unit,
   label words and symbols (`m = 5 kg`). Hindi keywords are translated. Units are converted (g to kg, km to m);
   where a calculator keeps its unit in a separate selector (km, h, mL) the selector is set; if the unit cannot be
   handled safely the value is **left empty, never guessed**.
2. If rules are confident (>= 0.75) and every value is found: answer immediately. **Cost: 0 credits, no AI call.**
3. Otherwise ask AI (credit reserved first). The AI sees the shortlisted tools (or all tools when keywords found
   nothing, about 5k tokens) and returns JSON. That JSON is **never trusted**:
   * the tool must be in the list we offered, the mode and field ids must exist (`registry.validate_route`),
   * every number must come from the student's text (allowing unit conversion), so the AI cannot invent values,
   * anything else is dropped; if nothing valid remains the credit is refunded and rules/suggestions are shown.
4. The page rebuilds the route from **its own registry** (`validateRoute`), so even a hostile backend cannot make
   the page link anywhere except a real calculator.

### Run
The page loads the real calculator in a hidden same-origin frame with `?mode=F&x=5&y=3` (the calculators already
support this) and reads `#result`. If the frame cannot be read (for example a `file://` preview), it shows an
"Open full calculator" link instead.

### Explain / Step-by-step  (`POST /v1/explain`)
Input: calculator, mode, inputs and the calculator's own result text. Output: explanation text.
* Template answer is built first (formula, your values, the result line, or the calculator's own working lines).
* Then AI is tried (explain = 1 credit, steps = 2). The text must pass `guard.py`: **no numbers that were not in the
  data we sent** (rounding allowed), no links or e-mail addresses, correct script (Devanagari for Hindi). A failure
  refunds the credit and shows the template with a short notice.

### Formula Finder  (`POST /v1/formula`)
Deterministic search over modes, names, keywords and formulas. An optional AI summary (1 credit) is checked
by the same guard and can only talk about the formulas we provide.

## 4. AI provider abstraction  (`backend/app/providers/`)

| File | Role |
|---|---|
| `base.py` | `AIProvider.generate(AIRequest) -> AIResponse`, and `ProviderError(kind=quota/rate_limit/auth/server/timeout/blocked/empty)` |
| `gemini.py` | Google Gemini over REST (`generateContent`), key in the `x-goog-api-key` header |
| `openai_compat.py` | Any OpenAI-style `/chat/completions` host (Groq, OpenRouter, ...). Set base URL, key and model |
| `mock.py` | Fake AI for development and tests only. Can imitate failures |
| `chain.py` | Tries providers in order with automatic quota handling (below) |

To add a provider: write one class with `generate()`, register it in `service.build_providers`. Nothing else changes.

### Automatic quota-exhaustion handling (`chain.py`)
* **Daily quota error (429):** the provider is skipped until its quota resets (Google's daily quota resets at
  midnight Pacific; we compute that), instead of being hit on every request.
* **Per-minute limit:** rests for `Retry-After` / `retryDelay` seconds (default 60).
* **Server errors / timeouts:** after 2 in a row, a growing cool-down (30 s up to 5 min).
* **Bad key (auth):** provider switched off until restart; visible in `/v1/health`.
* **All providers unavailable:** template answers with a clear notice. The user is never charged for a failure.

## 5. Limits, credits and tiers  (`quota.py`)

| | anonymous | free (logged in) | premium |
|---|---|---|---|
| AI credits per day (default) | 5 | 15 | 300 |
| Burst limit per minute | 4 | 8 | 20 |

* Only AI calls cost credits (route 1, explain 1, steps 2, formula 1). Calculators, rules and templates are free.
* Credits are reserved before the AI call and **refunded** on any failure or rejected output.
* **Global ceiling** (`GLOBAL_DAILY`) protects the provider's real free quota. Free + anonymous users may use at
  most `FREE_SHARE` (80%) of it, so paying users keep working when free users have used their share.
* Anonymous users are identified by browser id + IP; because a browser id is easy to change, anonymous traffic
  from one IP also shares a larger cap (6x the anonymous daily limit).
* A light 90-requests-per-minute limit applies to all requests, with or without AI.
* Storage is behind `UsageStore` (memory and SQLite included). **Free hosts wipe local files on redeploy**, so for
  a real launch add a Postgres/Supabase store (about 40 lines, same interface).

## 6. Accounts and subscriptions **(future, designed for)**

`identity.py` already separates *who is calling* from *what they may do*:

1. **Login:** use a provider that issues signed tokens (for example Supabase Auth or Firebase Auth). The frontend sends
   `Authorization: Bearer <token>`. The backend only **verifies** it (`JwtAuth`, HS256 included and tested); it never
   stores passwords. For asymmetric tokens (RS256/JWKS) extend `Authenticator.authenticate`.
2. **Tier:** `TierResolver.resolve(user_id, claim)` decides the tier. Today it trusts the `tier` claim in a token *we
   verified* (`ClaimsTierResolver`). For payments, replace it with a lookup in your database.
3. **Subscription verification:** the payment provider's **webhook** (server to server, signature-verified) writes
   `premium` + expiry to the database. The browser is never trusted to say it is premium.
4. **Credits as a product:** the quota layer already counts units; "buy more credits" is just a higher limit per user.
5. **Dev testing:** with `ENV=dev` the header `X-Dev-Tier: premium` simulates tiers. It is ignored when `ENV=prod`.

Not built: payment integration, a user database, e-mail flows, admin screens, abuse dashboards.

## 7. Security notes

* **Keys:** only in backend environment variables. `/v1/health` shows provider *state*, never keys (tested).
* **CORS:** set `CORS_ORIGINS` to your exact site in production.
* **Prompt injection:** student text and calculator output are passed to the AI as JSON *data*; the system prompt says to
  ignore instructions inside them; every output is validated (registry, number check, no links). A successful
  injection can at worst waste one credit, not change a route, a number or a link.
* **XSS:** the page inserts all dynamic text with `textContent`, never `innerHTML` (tested with hostile input and a
  hostile backend).
* **Known limitation:** `/v1/explain` trusts the `result_text` the browser sends (the calculators run in the browser).
  Someone could send their own text and get an AI explanation of it. Credits, limits, the output guard and the
  "only explain this calculator result" prompt contain the damage. A later hardening is to compute results on the server.
* **Proxy IPs:** `TRUST_PROXY_HOPS` must match the number of trusted proxies, otherwise visitors can fake their IP.
* **Privacy (decide before launch):** question text is sent to the AI provider. Google's free tier may use submitted
  content to improve its products (check its current terms); the site's Privacy Policy and any under-18 rules
  (India's DPDP Act) need review before this goes public. The page is currently `noindex` and not linked from the site.
* Logs contain provider error kinds, not student text.

## 8. Shared data and how it is generated

| File | Made by | Used by |
|---|---|---|
| `backend/app/data/registry.json` | `tools/build_registry.js` (reads the real calculator pages) | backend, and (inside magic-data.js) the page |
| `shared/strings.json` | hand-written, English + Hindi | backend fallbacks and the page |
| `shared/nlp.json` | generated from the Python rule tables by `tools/sync_data.py` | the page's offline engine |
| `website/magic/magic-data.js` | `tools/sync_data.py` (registry + nlp + strings in one file) | the page |

After you add or change a calculator: run `build_registry.js`, then `sync_data.py`. The cross-check test then
confirms the JavaScript engine still matches the Python rules.

## 9. Roadmap, and what NOT to build yet

1. **Now (this prototype):** rules + templates + optional AI, EN/HI, limits, safe fallbacks.
2. **Next:** deploy the backend, gather real questions (without storing identities), tune `rules.py` and the AI prompts
   against them, extend the registry to every mode, add a privacy-policy section.
3. **Then:** login + free tier, then premium + payments, a Postgres usage store, an admin view of costs.
4. **Later, only if used:** "personalised" practice (needs accounts and data), API/white-label for schools.

**Do not build yet:** an AI chat box, image/photo question solving, your own model, a vector database, user content,
or personalisation. The routing + explanation loop above is the valuable, defensible core; the rest adds cost and risk
before there is evidence students want it.
