# Changelog

## Correction release (2026-11-08): AdSense-readiness fixes 1-3

Base: the uploaded `suno_sathi_Tools_mvp_email_fixed.zip`. No files added, removed or renamed. Calculator formulas,
calculator pages' own scripts and page content are unchanged.

### 1. Footer links
- Added a row with **Privacy Policy, Contact, About, Terms** to the footer of all 38 calculators and the Physics and
  Chemistry index pages (40 pages). Before this, none of them linked to these pages.
- Added **Terms** to the footer of all 9 chapter guides and the chapters index.
- Style for the row lives in `assets/tools.css` (`.ssl-legal`). Footers keep their existing look otherwise.

### 2. Privacy Policy (`privacy-policy.html`)
- Section 4 renamed "Cookies, Analytics and Advertising" and rewritten to match the site today: no advertising, no
  analytics, no cookies of its own; local storage is used for the theme and recent calculations; a service worker may
  keep offline copies of pages. States the policy will be updated (and consent requested where the law requires)
  before ads or analytics are added.
- Added one sentence that the hosting provider may keep standard server logs. Remove it if you prefer.
- Removed the unfinished "this email address will be replaced" sentence.

### 3. Canonical URLs, sitemap and offline cache aligned to the live URL format
- The live site shows links without `.html` (Netlify "Pretty URLs" rewrites links in served HTML), but canonicals and the
  sitemap used `.html`. They now use the same form as the live links, for example
  `https://sunosaathilabs.netlify.app/physics/force-calculator` and `.../physics/` for folder pages.
  51 canonicals changed; `sitemap.xml` regenerated (55 URLs, lastmod 2026-11-08).
- Source links still end in `.html`, so the project keeps working in Spck Preview and on any host.
- `service-worker.js` (version `2026-11-08-1`): one saved copy per page whatever the URL form (`/x`, `/x.html`, `/dir/`,
  `/dir/index.html`), and redirected responses are stored as plain copies. This fixes offline use of pages opened
  through the extensionless links.

### Files changed (59, including README.md and this file)
- 40 calculator and index pages in `physics/` and `chemistry/` (footer row, canonical)
- 10 chapter pages in `chapters/` (Terms link, canonical)
- `about.html`, `assets/tools.css`, `contact.html`, `privacy-policy.html`, `service-worker.js`, `sitemap.xml`, `terms.html`

## MVP release (2026-11-06)

Base: the previous corrected ZIP (`suno_sathi_Tools_fixed.zip`). No files were deleted or renamed.
All existing URLs are unchanged.

### New features (all free, no backend, no API)
- **Copy result / Share / Print-Save as PDF** buttons under the result on all 38 calculators.
- **Shareable links:** the address bar updates after each calculation (e.g. `?mode=F&x=5&y=3`).
  Opening such a link restores the inputs and recalculates automatically.
  Share uses the phone's Share sheet when available, otherwise copies the link.
- **Recent calculations** (last 12, stored only in the visitor's own browser) with a **Clear history** button.
  Shown on calculator pages and on the homepage.
- **Dark mode** button (bottom-right). Remembers the choice. System preference is not auto-detected.
- **Offline support (PWA):** `manifest.json`, `service-worker.js`, icons, `offline.html`.
  Pages load fresh from the network when online; the last saved copy is used when offline or very slow.
- **Homepage smart search:** keyword/synonym matching across all 38 calculators and 9 chapter guides
  (try "F=ma", "ohm", "kwh", "escape velocity"). Replaces the old tile filter that scrolled the page on every keystroke.
- **Chapter guides** (`/chapters/`): 9 hand-written pages with key formulas, a worked example,
  common mistakes, quick FAQ and links to the matching calculators. Linked from the homepage, physics/chemistry
  index pages and each calculator's "related" list.
- Print stylesheet: hides buttons and navigation, keeps the title, inputs and result.

### Bugs fixed (confirmed by reproducing them in the previous ZIP first)
- **Small answers displayed as 0** (e.g. density 0.0004 / 2 showed `0`; molarity 0.0005 mol in 10 L showed `0 M`).
  The number-formatting helper dropped digits. Fixed on 10 pages (list below).
- **Wave calculator, "Time Period" mode** asked for a period input instead of frequency (T = 1/f). Fixed.
- **Optics, "Magnification" mode** labelled the answer in "cm". Magnification has no unit. Fixed; step text now
  distinguishes the mirror (m = -v/u) and lens (m = v/u) sign conventions.
- **Headline answer showed `0.0000`** for very small results while the steps showed the real value
  (Hooke's law, friction, kinematics, SHM energy, angular acceleration, centripetal force). Now shown as e.g. `1.0000e-6`.
- **Floating-point noise** such as `14.999999999999996` or `0.7500000000000001` in results and steps is tidied in
  `assets/tools.js` (only numbers with 10+ decimals; constants such as Avogadro's number are untouched).
- Round dark-mode button no longer covers the last line of a page.

### Privacy policy
Added a section "Information Stored on Your Device" describing theme choice, recent calculations,
saved page copies for offline use, and that shared links contain the entered values. Later sections renumbered.

### Other
- `sitemap.xml`: now 55 URLs (added 10 chapter pages). `offline.html` and `404.html` are excluded and set to noindex.
- `_headers`: `service-worker.js` and `manifest.json` are never cached by the browser (so updates go live quickly).
- `service-worker.js` always revalidates with the server while online.

### Not changed
Calculator formulas and logic are untouched except the formatting fixes listed above.
`robots.txt` and `404.html` are identical to the previous ZIP.

## Files

### Added (23)
- `_headers`
- `assets/hub.css`
- `assets/icons/icon-192.png`
- `assets/icons/icon-512.png`
- `assets/icons/icon-maskable-512.png`
- `assets/site-data.js`
- `assets/tools.css`
- `assets/tools.js`
- `chapters/acids-bases-and-ph.html`
- `chapters/circular-and-rotational-motion.html`
- `chapters/electricity-and-optics.html`
- `chapters/index.html`
- `chapters/mole-concept-and-molar-mass.html`
- `chapters/motion-and-forces.html`
- `chapters/oscillations-and-waves.html`
- `chapters/properties-of-matter-and-heat.html`
- `chapters/solutions-and-concentration.html`
- `chapters/work-energy-and-gravitation.html`
- `manifest.json`
- `offline.html`
- `service-worker.js`
- `README.md`
- `CHANGELOG.md`

### Calculator pages whose own script was changed (16)
- `chemistry/molarity-calculator.html`
- `chemistry/mole-calculator.html`
- `physics/angular-acceleration-calculator.html`
- `physics/centripetal-force-calculator.html`
- `physics/density-calculator.html`
- `physics/electrical-energy.html`
- `physics/friction-calculator.html`
- `physics/gravitational-calculator.html`
- `physics/hookes-law-calculator.html`
- `physics/kinematics-equation-solver.html`
- `physics/momentum-impulse-calculator.html`
- `physics/ohms-law-calculator.html`
- `physics/optics-calculator.html`
- `physics/shm-energy-calculator.html`
- `physics/wave-frequency-calculator.html`
- `physics/work-energy-power.html`

### Other modified files (30)
Most of these only gained shared includes (manifest link, `assets/tools.css`, dark-mode initialiser, `assets/tools.js`)
and a "Chapter guide" link. Larger edits: `index.html` (smart search, chapter section, recent-calculations block),
`privacy-policy.html` (new on-device storage section), `sitemap.xml`, and the physics/chemistry `index.html` navigation.
Calculator logic is untouched in all of them.
`about.html`, `chemistry/dilution-calculator.html`, `chemistry/index.html`, `chemistry/molar-mass-calculator.html`, `chemistry/ph-calculator.html`, `contact.html`, `index.html`, `physics/acceleration-calculator.html`, `physics/centre-of-mass-calculator.html`, `physics/circular-motion-calculator.html`, `physics/conservation-of-momentum-calculator.html`, `physics/fluid-mechanics-calculator.html`, `physics/force-calculator.html`, `physics/gravitation-orbital-calculator.html`, `physics/heat-temperature-calculator.html`, `physics/index.html`, `physics/moment-of-inertia-calculator.html`, `physics/pressure-calculator.html`, `physics/projectile-motion-calculator.html`, `physics/rolling-motion-calculator.html`, `physics/rotational-kinematics-calculator.html`, `physics/rotational-motion-calculator.html`, `physics/shm-advanced-calculator.html`, `physics/shm-calculator.html`, `physics/simple-pendulum-calculator.html`, `physics/speed-distance-time.html`, `physics/thermodynamics-calculator.html`, `privacy-policy.html`, `sitemap.xml`, `terms.html`

### Unchanged
`404.html`, `robots.txt`
