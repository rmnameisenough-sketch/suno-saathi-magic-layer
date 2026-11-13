# Suno Saathi Tools

Free physics and chemistry calculators and chapter guides. Plain HTML, CSS and JavaScript.
No build step, no backend, no database, no paid API.

Live site: https://sunosaathilabs.netlify.app/

## What is in the project

```
index.html                 homepage (smart search, directory, recent calculations)
physics/                   physics calculators + index.html
chemistry/                 chemistry calculators + index.html
chapters/                  chapter guides (formulas, worked example, links to calculators)
assets/tools.js            shared features: copy/share/print, share links, history, dark mode, offline, search
assets/tools.css           styles for those shared features + print + dark mode
assets/hub.css             styles for the chapter guide pages
assets/site-data.js        list of calculators/chapters used by the homepage search
assets/icons/              app icons (192, 512, maskable)
manifest.json              lets phones "Add to Home screen"
service-worker.js          offline support
offline.html, 404.html     fallback pages (not indexed)
sitemap.xml, robots.txt    for Google
_headers                   Netlify cache rules for service-worker.js and manifest.json
about, contact, privacy-policy, terms .html
```

## Import into Spck Editor (Android)

I could not check the current Spck menus, so the wording below may differ slightly on your version.

1. Download the ZIP to your phone.
2. Extract it with the Files app (long-press the ZIP and choose Extract). You should get a folder
   that has `index.html` directly inside it.
3. In Spck Editor, open that folder as a project (use Spck's "open folder / import project" option).
4. To test, open `index.html` and use Preview. Always start Preview from the root `index.html`.

Notes for Spck Preview:
- Basic pages, calculators, copy/print and dark mode should work.
- Offline mode needs a secure address (https or localhost), so it will not run in Spck Preview.
  Test it on the deployed Netlify site instead.
- Shared links with `?inputs` work only when the page is opened from a normal web address.

## Deploy to Netlify from Android

Use the same method you used for the current live site if it is already working.

**Option A (recommended): GitHub + Netlify**
1. Create a GitHub repository for the project.
2. In Spck, connect the project to the repository, commit all files and push.
3. In Netlify: Add new site > Import an existing project > choose the repository.
4. Leave the build command empty. Leave the publish directory empty (the site root).
   Every later push to GitHub then redeploys the site automatically.

**Option B: manual upload in Netlify**
Netlify's Deploys page offers a manual upload. I could not confirm whether it accepts a ZIP or only a folder on a
phone browser, so use Option A if upload does not work.

## After every deploy: quick checks (5 minutes, on your phone)

1. Open the live site and hard-refresh. Open one calculator, calculate, and tap Copy, Share and Print.
2. Open the Share link in a new tab. The inputs should come back and the answer should appear by itself.
3. Open `/sitemap.xml` and `/robots.txt`.
4. Turn on airplane mode, reload a page you already visited. It should still open.
5. In Google Search Console, resubmit `sitemap.xml` if you added pages.

## Adding a new calculator later

1. Create the page in `physics/` or `chemistry/`. Give the result box `id="result"`, the calculate button
   `onclick="calculate()"`, and every input/select an `id`. The shared features then work automatically.
2. Copy the `<link>`/`<script>` lines from the head of an existing calculator page (manifest, `tools.css`,
   dark-mode line, `tools.js`).
3. Add the page to `assets/site-data.js` (so search finds it), `sitemap.xml`, and a link on its chapter guide.
4. In `service-worker.js`, add the file to `PRECACHE` and change `VERSION` to a new value.

## Things to know

- Calculators use g = 9.8 m/s² on most pages. The friction calculator uses 9.81 (shown in its steps) and the pendulum
  calculator has an editable g (default 9.81). Both are accepted conventions; follow your syllabus.
- Dark mode works by inverting colours, so coloured banners appear light blue in dark mode.
- If you change to a custom domain, update the canonical URLs in the pages and the addresses in `sitemap.xml` and `robots.txt`.

## URLs, canonicals and Netlify "Pretty URLs"

Netlify's Pretty URLs setting rewrites the links in the HTML it serves, so visitors see links without `.html`.
The files in this project still use `.html` links on purpose (this keeps Spck Preview working). Canonical tags and
`sitemap.xml` use the form without `.html`, to match what the live site shows. The service worker treats both forms
as the same page.

What I could and could not check: I could not test Netlify itself. Reports from Netlify's community say that with
Pretty URLs on, both `/page` and `/page.html` return the page without a redirect, which is why the canonical tag
matters. I tested the offline behaviour against a local simulation of that setup, not against Netlify.

## Still to do (manual)

- After deploying, check on your phone: open one calculator page, view the page source and confirm the
  canonical tag has no `.html`; open `/sitemap.xml`; open a page you have not visited, turn on airplane mode and reload.
- In Google Search Console, resubmit `sitemap.xml` (the URLs changed).
- When you add ads or analytics, update `privacy-policy.html` section 4 first, and add a consent banner for visitors
  in the EEA, UK and Switzerland.
