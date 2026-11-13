/*
  Suno Saathi Tools - service worker (offline support)

  How it works (simple version):
  - Online: every page is fetched fresh from the network, so visitors never see an old page.
  - Offline or very slow network (over 4.5 seconds): the last saved copy is used instead.
  - Only pages from this website are saved. Nothing else is touched.

  WHEN YOU ADD A NEW PAGE: add its path to PRECACHE below (optional, the page will also be
  saved automatically the first time someone visits it). WHEN YOU CHANGE THE PRECACHE LIST
  OR WANT EVERYONE'S SAVED COPIES REFRESHED: change VERSION to a new value.
*/
const VERSION = '2026-11-08-1';
const CACHE = 'ssl-' + VERSION;
const NETWORK_TIMEOUT_MS = 4500;

const PRECACHE = [
  './',
  'physics/',
  'chemistry/',
  'chapters/',
  'about.html',
  'chapters/acids-bases-and-ph.html',
  'chapters/circular-and-rotational-motion.html',
  'chapters/electricity-and-optics.html',
  'chapters/index.html',
  'chapters/mole-concept-and-molar-mass.html',
  'chapters/motion-and-forces.html',
  'chapters/oscillations-and-waves.html',
  'chapters/properties-of-matter-and-heat.html',
  'chapters/solutions-and-concentration.html',
  'chapters/work-energy-and-gravitation.html',
  'chemistry/dilution-calculator.html',
  'chemistry/index.html',
  'chemistry/molar-mass-calculator.html',
  'chemistry/molarity-calculator.html',
  'chemistry/mole-calculator.html',
  'chemistry/ph-calculator.html',
  'contact.html',
  'index.html',
  'offline.html',
  'physics/acceleration-calculator.html',
  'physics/angular-acceleration-calculator.html',
  'physics/centre-of-mass-calculator.html',
  'physics/centripetal-force-calculator.html',
  'physics/circular-motion-calculator.html',
  'physics/conservation-of-momentum-calculator.html',
  'physics/density-calculator.html',
  'physics/electrical-energy.html',
  'physics/fluid-mechanics-calculator.html',
  'physics/force-calculator.html',
  'physics/friction-calculator.html',
  'physics/gravitation-orbital-calculator.html',
  'physics/gravitational-calculator.html',
  'physics/heat-temperature-calculator.html',
  'physics/hookes-law-calculator.html',
  'physics/index.html',
  'physics/kinematics-equation-solver.html',
  'physics/moment-of-inertia-calculator.html',
  'physics/momentum-impulse-calculator.html',
  'physics/ohms-law-calculator.html',
  'physics/optics-calculator.html',
  'physics/pressure-calculator.html',
  'physics/projectile-motion-calculator.html',
  'physics/rolling-motion-calculator.html',
  'physics/rotational-kinematics-calculator.html',
  'physics/rotational-motion-calculator.html',
  'physics/shm-advanced-calculator.html',
  'physics/shm-calculator.html',
  'physics/shm-energy-calculator.html',
  'physics/simple-pendulum-calculator.html',
  'physics/speed-distance-time.html',
  'physics/thermodynamics-calculator.html',
  'physics/wave-frequency-calculator.html',
  'physics/work-energy-power.html',
  'privacy-policy.html',
  'terms.html',
  'manifest.json',
  'assets/tools.js',
  'assets/tools.css',
  'assets/hub.css',
  'assets/site-data.js',
  'assets/icons/icon-192.png',
  'assets/icons/icon-512.png'
];

// One saved copy per page, however the page is opened:
//   /physics/force-calculator  and  /physics/force-calculator.html  -> same copy
//   /physics/  and  /physics  and  /physics/index.html              -> same copy
//   ?inputs and #anchors are ignored.
// (Netlify's "Pretty URLs" setting shows links without .html, so a visitor can arrive either way.)
function keyFor(url) {
  const u = new URL(url);
  u.search = '';
  u.hash = '';
  let p = u.pathname.replace(/\/index\.html$/, '/').replace(/\.html$/, '');
  if (p.length > 1 && p.endsWith('/')) { p = p.slice(0, -1); }
  u.pathname = p;
  return u.href;
}

// A browser refuses to show a "redirected" response as a page, so store a plain copy instead.
async function plainCopy(res) {
  if (!res.redirected) { return res; }
  return new Response(await res.blob(), { status: res.status, statusText: res.statusText, headers: res.headers });
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(PRECACHE.map(async (path) => {
      try {
        const url = new URL(path, self.registration.scope).href;
        const res = await fetch(new Request(url, { cache: 'reload' }));
        if (res && res.ok && res.type === 'basic') { await cache.put(keyFor(url), await plainCopy(res)); }
      } catch (e) { /* skip files that fail; they are saved later when visited */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n.startsWith('ssl-') && n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

async function networkFirst(request) {
  const key = keyFor(request.url);
  try {
    // 'no-cache' = always ask the server if the file changed (cheap), so old copies are never served while online
    const res = await withTimeout(fetch(request, { cache: 'no-cache' }), NETWORK_TIMEOUT_MS);
    if (res && res.ok && res.type === 'basic') {
      plainCopy(res.clone()).then((copy) => caches.open(CACHE).then((c) => c.put(key, copy))).catch(() => {});
    }
    return res;
  } catch (e) {
    const hit = await caches.match(key, { ignoreVary: true });
    if (hit) { return hit; }
    if (request.mode === 'navigate') {
      const off = await caches.match(keyFor(new URL('offline.html', self.registration.scope).href), { ignoreVary: true });
      if (off) { return off; }
    }
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') { return; }
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) { return; }          // never touch ads, fonts or other sites
  const p = url.pathname;
  if (/\/(service-worker\.js|sitemap\.xml|robots\.txt|_headers)$/.test(p)) { return; }  // always live
  event.respondWith(networkFirst(req));
});
