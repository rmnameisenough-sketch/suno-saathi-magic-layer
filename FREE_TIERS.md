# Free services: what is genuinely free, and the catches

Researched in November 2026 from the providers' own pages where possible. **Free tiers change often. Re-check the
linked pages before you rely on any number.** Nothing here needs a paid service to run the prototype.

## Needed to run the prototype: nothing paid

| What | Cost |
|---|---|
| Frontend preview in Spck, offline demo mode | free, no account, no backend |
| Local backend (`python dev_server.py`) with the fake AI | free, Python only |
| All tests | free |

## Needed when you go live (all have a free tier)

| Service | What the free tier gives | Catches that matter for you | How sure I am |
|---|---|---|---|
| **Netlify** (already in use) | static hosting for the website | the Magic Layer page is part of it; backend must live elsewhere | already working for you |
| **GitHub** | repository, Netlify auto-deploy | none for this use | standard |
| **Google Gemini API** (AI) | a free tier exists. Limits are per **project** (not per key), the daily limit resets at **midnight Pacific**, and exact per-model numbers are shown only inside Google AI Studio | Google says limits are not guaranteed. Google's billing docs say paid usage is not used to improve its products, which implies **free-tier prompts may be**: read the current terms before sending student text. Which models are free changes, so check AI Studio. | Official docs read: https://ai.google.dev/gemini-api/docs/rate-limits . **Model names and numbers not verified**: `GEMINI_MODEL` is a setting for this reason |
| **Render** (backend hosting) | free web service: about 750 instance-hours a month | **sleeps after 15 minutes without traffic**; waking takes about a minute (community reports), which is why the page shows a "waking the server" message and falls back to built-in rules. **Free Postgres databases expire after 30 days**, so do not keep usage counters or accounts there | Official: https://docs.render.com/free (sleep + 750 h + 30-day Postgres). Wake time from community reports |
| **Supabase** (future login + database) | free plan with auth for a large number of monthly users and a small database | free projects are **paused after a week of inactivity**; capacity numbers differ between articles | Pricing page: https://supabase.com/pricing . Confirm the current numbers there |

## Looked at but NOT verified (do your own check before choosing)

* **Other free AI hosts** (Groq, OpenRouter and similar): the `openai_compat` provider is built and tested against a
  fake server, but I did not check any host's current free limits, terms or data use.
* **Google Cloud Run, Fly.io, Koyeb, PythonAnywhere** as backend hosts: not researched. (One article I saw said
  Fly.io no longer offers a free plan to new accounts; I could not confirm it.)
* **Payments** (Razorpay, Stripe, others), fees and Indian-market availability: not researched.
* **Legal:** child-data rules (DPDP Act), AI disclosure expectations, Google's terms for student content: not assessed.

## Budget thinking (so a free tier does not surprise you)

* Set `GLOBAL_DAILY` **below** your provider's real daily free allowance. When it is reached the site degrades to
  templates automatically instead of failing.
* A typical interaction costs 0 credits (rules), 1 (explain) or 2 (step-by-step). With the default 5 anonymous
  credits, one visitor can use at most 5 AI calls a day.
* The "all tools" routing fallback sends about 5k tokens; it only happens when keywords found nothing useful.
