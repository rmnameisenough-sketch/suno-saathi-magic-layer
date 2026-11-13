/*
  Dev tool: builds the Magic Layer tool registry from the real calculator pages.

  Only needed when you ADD or CHANGE a calculator. Run on a PC (or Termux) with Node + Playwright:
    cd website && python3 -m http.server 8765        (in one terminal)
    node tools/build_registry.js                      (in another)

  Output: backend/app/data/registry.json. Then run  python3 tools/sync_data.py  to rebuild website/magic/magic-data.js.
*/
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'website');
const BASE = process.env.BASE || 'http://localhost:8765/';
const SUPPLEMENT = JSON.parse(fs.readFileSync(path.join(__dirname, 'formulas_supplement.json'), 'utf8'));
const PRIMARY_RE = '^(mode|operation|unit|count|unknown)$';

function pagesIn(dir) {
  return fs.readdirSync(path.join(SITE, dir))
    .filter((f) => f.endsWith('.html') && f !== 'index.html')
    .sort()
    .map((f) => dir + '/' + f);
}

function loadSiteData() {
  // site-data.js only assigns window.SSL_TOOLS (and similar), so run it against a fake window object.
  const t = fs.readFileSync(path.join(SITE, 'assets/site-data.js'), 'utf8');
  const w = {};
  new Function('window', t)(w);
  return w.SSL_TOOLS || [];
}

(async () => {
  const siteData = loadSiteData();
  const browser = await chromium.launch();
  const tools = [];

  for (const file of [...pagesIn('physics'), ...pagesIn('chemistry')]) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 800 }, serviceWorkers: 'block' });
    const page = await ctx.newPage();
    await page.goto(BASE + file);
    await page.waitForTimeout(150);

    const base = await page.evaluate((primarySrc) => {
      const re = new RegExp(primarySrc);
      const clean = (t) => t.replace(/\s+/g, ' ').trim();
      const selects = [...document.querySelectorAll('select')].filter((s) => s.id && !s.closest('.search,.search-area'));
      const primary = selects.find((s) => re.test(s.id)) || null;
      const opts = (s) => [...s.options].map((o) => ({ v: o.value, l: clean(o.text) }));
      const h2 = [...document.querySelectorAll('h2')];
      const fh = h2.find((h) => /formula/i.test(h.textContent));
      let formula = '';
      if (fh) {
        let n = fh.nextElementSibling;
        const parts = [];
        while (n && n.tagName !== 'H2' && parts.join(' ').length < 400) { parts.push(clean(n.innerText)); n = n.nextElementSibling; }
        formula = clean(parts.join(' ')).slice(0, 400);
      }
      const rh = h2.find((h) => /related|more (physics|chemistry)/i.test(h.textContent));
      const related = rh && rh.nextElementSibling ? [...rh.nextElementSibling.querySelectorAll('a')].map((a) => a.getAttribute('href')) : [];
      return {
        title: (document.querySelector('h1') || {}).textContent || document.title,
        primary: primary ? { id: primary.id, options: opts(primary) } : null,
        extras: selects.filter((s) => s !== primary).map((s) => ({ id: s.id, options: opts(s) })),
        formula, related,
      };
    }, PRIMARY_RE);

    const fieldsNow = () => page.evaluate(() => [...document.querySelectorAll('input')]
      .filter((x) => x.id && x.offsetParent !== null && !x.closest('.search,.search-area,.ssl-toolbar') && !['button', 'checkbox', 'radio', 'hidden', 'file'].includes(x.type))
      .map((x) => {
        // 1) <label for=id>  2) the nearest LABEL just before the input  3) first label in the container
        let l = '';
        const lab = document.querySelector('label[for="' + x.id + '"]');
        if (lab) { l = lab.textContent; }
        if (!l) { let n = x.previousElementSibling; for (let i = 0; n && i < 3; i++, n = n.previousElementSibling) { if (n.tagName === 'LABEL') { l = n.textContent; break; } } }
        if (!l) { const par = x.closest('div,section'); const pl = par && par.querySelector('label'); if (pl) { l = pl.textContent; } }
        const f = { id: x.id, label: l.replace(/\s+/g, ' ').trim(), type: x.type === 'text' ? 'text' : 'number' };
        if (x.value !== '') { f.default = x.value; }
        return f;
      }));

    const modes = {};
    if (base.primary) {
      for (const o of base.primary.options) {
        await page.selectOption('#' + base.primary.id, o.v);
        await page.waitForTimeout(40);
        modes[o.v] = { label: o.l, fields: await fieldsNow() };
      }
    } else {
      modes[''] = { label: '', fields: await fieldsNow() };
    }

    const id = path.basename(file, '.html');
    const sd = siteData.find((x) => x.u === file) || {};
    const dirOf = file.split('/')[0];
    tools.push({
      id,
      name: (sd.t || base.title).trim(),
      category: dirOf === 'physics' ? 'Physics' : 'Chemistry',
      url: file,
      keywords: sd.k || '',
      modeSelect: base.primary ? base.primary.id : null,
      modes,
      extras: base.extras,
      formula: base.formula || SUPPLEMENT[id] || '',
      related: base.related
        .filter((h) => h && !h.includes('index.html'))
        .map((h) => h.replace(/^\.\.\//, ''))
        .map((h) => (/^(physics|chemistry|chapters)\//.test(h) ? h : dirOf + '/' + h))
        .slice(0, 5),
    });
    await ctx.close();
  }

  const chapters = fs.readdirSync(path.join(SITE, 'chapters'))
    .filter((f) => f.endsWith('.html') && f !== 'index.html')
    .map((f) => {
      const h = fs.readFileSync(path.join(SITE, 'chapters', f), 'utf8');
      const t = (h.match(/<title>(.*?)<\/title>/) || [])[1] || f;
      const links = [...h.matchAll(/href="\.\.\/((?:physics|chemistry)\/[a-z0-9-]+\.html)"/g)].map((m) => m[1]);
      return { url: 'chapters/' + f, title: t.replace(/ \| Suno Saathi Tools$/, '').replace(/&amp;/g, '&'), tools: [...new Set(links)] };
    });
  for (const t of tools) { t.chapter = (chapters.find((c) => c.tools.includes(t.url)) || {}).url || null; }

  const out = { version: 1, generated: new Date().toISOString().slice(0, 10), tools, chapters };
  const s = JSON.stringify(out);
  fs.writeFileSync(path.join(ROOT, 'backend/app/data', 'registry.json'), s);
  console.log('Now run: python3 tools/sync_data.py');
  console.log('tools:', tools.length, '| modes:', tools.reduce((a, t) => a + Object.keys(t.modes).length, 0), '| chapters:', chapters.length, '| bytes:', s.length);
  await browser.close();
})();
