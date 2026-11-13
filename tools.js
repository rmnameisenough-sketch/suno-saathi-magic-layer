/*
  Suno Saathi Tools - shared extras
  ---------------------------------
  This file ADDS features to every page. It never changes a calculator's own formulas.
  Features: dark mode button, offline support (service worker), and on calculator pages:
  Copy result, Share, Print/Save as PDF, shareable links that restore inputs,
  and a "Recent calculations" list stored only in the visitor's own browser.
  Homepage: smart calculator search.
*/
(function () {
  'use strict';

  var script = document.currentScript;
  if (!script || !script.src) { return; }
  // Site root = the folder above /assets/. Works on Netlify, localhost and Spck preview.
  var ROOT = new URL('../', script.src).href;

  var HISTORY_KEY = 'sslHistory';
  var THEME_KEY = 'sslTheme';

  /* ---------- small helpers ---------- */
  function store(op, key, value) {
    try {
      if (op === 'get') { return window.localStorage.getItem(key); }
      if (op === 'set') { window.localStorage.setItem(key, value); return true; }
      if (op === 'del') { window.localStorage.removeItem(key); return true; }
    } catch (e) { /* storage blocked or full: features simply stay off */ }
    return null;
  }
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) { Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); }); }
    if (text !== undefined) { n.textContent = text; }
    return n;
  }
  function ready(fn) {
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', fn); } else { fn(); }
  }

  /* ---------- 1. Dark mode ---------- */
  function setupTheme() {
    var root = document.documentElement;
    var btn = el('button', { type: 'button', 'class': 'ssl-fab', 'aria-label': 'Switch dark mode on or off', title: 'Dark mode' });
    function paint() { btn.textContent = root.getAttribute('data-theme') === 'dark' ? '☀️' : '🌙'; }
    btn.addEventListener('click', function () {
      if (root.getAttribute('data-theme') === 'dark') { root.removeAttribute('data-theme'); store('set', THEME_KEY, 'light'); }
      else { root.setAttribute('data-theme', 'dark'); store('set', THEME_KEY, 'dark'); }
      paint();
    });
    paint();
    document.body.appendChild(btn);
  }

  /* ---------- 2. Offline support ---------- */
  function setupServiceWorker() {
    if (!('serviceWorker' in navigator)) { return; }
    var okHost = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    if (!okHost) { return; }
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(ROOT + 'service-worker.js', { scope: ROOT }).catch(function () { /* ignore */ });
    });
  }

  /* ---------- 3. Calculator pages ---------- */
  function isCalculatorPage() {
    return !!document.getElementById('result') && typeof calculate === 'function';
  }

  function visibleFields() {
    var list = document.querySelectorAll('input, select, textarea');
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      if (!f.id) { continue; }
      if (f.closest('.ssl-toolbar, .ssl-recent, .search, .search-area')) { continue; }
      var t = (f.type || '').toLowerCase();
      if (t === 'button' || t === 'submit' || t === 'reset' || t === 'hidden' || t === 'file' || t === 'password') { continue; }
      if (f.offsetParent === null) { continue; } // hidden fields are not part of the current calculation
      out.push(f);
    }
    return out;
  }

  function buildQuery() {
    var p = new URLSearchParams();
    visibleFields().forEach(function (f) {
      if ((f.type === 'checkbox' || f.type === 'radio') && !f.checked) { return; }
      if (f.value !== '') { p.set(f.id, f.value); }
    });
    return p;
  }

  function pageUrlWith(params) {
    var base = location.href.split('#')[0].split('?')[0];
    var q = params.toString();
    return q ? base + '?' + q : base;
  }

  function restoreFromUrl() {
    if (!location.search) { return false; }
    var params;
    try { params = new URLSearchParams(location.search); } catch (e) { return false; }
    var pairs = [];
    params.forEach(function (v, k) { pairs.push([k, String(v).slice(0, 200)]); });
    if (!pairs.length) { return false; }

    function pass() {
      pairs.forEach(function (kv) {
        var node = document.getElementById(kv[0]);
        if (!node) { return; }
        var tag = node.tagName;
        if (tag === 'SELECT') {
          var has = false;
          for (var i = 0; i < node.options.length; i++) { if (node.options[i].value === kv[1]) { has = true; break; } }
          if (!has) { return; }
          node.value = kv[1];
          node.dispatchEvent(new Event('change', { bubbles: true }));
        } else if (tag === 'INPUT' || tag === 'TEXTAREA') {
          if (node.type === 'checkbox' || node.type === 'radio' || node.type === 'file' || node.type === 'password') { return; }
          node.value = kv[1];
          node.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    }
    // Two passes: choosing a mode can create new input boxes that need values afterwards.
    pass(); pass();

    var realAlert = window.alert;
    window.alert = function () { /* stay quiet while restoring from a link */ };
    try { calculate(); } catch (e) { /* page's own validation decides */ }
    window.alert = realAlert;
    return true;
  }

  function resultText() {
    var r = document.getElementById('result');
    if (!r || r.offsetParent === null) { return ''; }
    return (r.innerText || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean).join('\n');
  }

  function pageTitle() {
    var h = document.querySelector('h1');
    return h ? h.textContent.replace(/\s+/g, ' ').trim() : document.title;
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var ta = el('textarea', { readonly: '', 'aria-hidden': 'true' });
      ta.value = text;
      ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); }
      catch (e) { reject(e); }
      document.body.removeChild(ta);
    });
  }

  function setupToolbar() {
    var result = document.getElementById('result');
    var bar = el('div', { 'class': 'ssl-toolbar', role: 'group', 'aria-label': 'Result tools' });
    var bCopy = el('button', { type: 'button' }, '📋 Copy result');
    var bShare = el('button', { type: 'button' }, '🔗 Share');
    var bPrint = el('button', { type: 'button' }, '🖨️ Print / PDF');
    bar.appendChild(bCopy); bar.appendChild(bShare); bar.appendChild(bPrint);
    var msg = el('p', { 'class': 'ssl-msg', role: 'status', 'aria-live': 'polite' });
    result.parentNode.insertBefore(bar, result.nextSibling);
    bar.parentNode.insertBefore(msg, bar.nextSibling);

    var timer = null;
    function say(t) {
      msg.textContent = t;
      clearTimeout(timer);
      timer = setTimeout(function () { msg.textContent = ''; }, 3500);
    }

    bCopy.addEventListener('click', function () {
      var text = resultText();
      if (!text) { say('Please run a calculation first, then copy the result.'); return; }
      var full = pageTitle() + '\n' + text + '\n\n' + pageUrlWith(buildQuery());
      copyText(full).then(function () { say('Result copied.'); }, function () { say('Could not copy. Please select the text and copy it manually.'); });
    });

    bShare.addEventListener('click', function () {
      var url = pageUrlWith(buildQuery());
      var data = { title: document.title, text: pageTitle() + ' on Suno Saathi Tools', url: url };
      if (navigator.share) {
        navigator.share(data).catch(function (e) { if (e && e.name !== 'AbortError') { say('Sharing failed. Try Copy result instead.'); } });
      } else {
        copyText(url).then(function () { say('Link copied. Paste it anywhere to share this calculation.'); }, function () { say('Could not copy the link.'); });
      }
    });

    bPrint.addEventListener('click', function () { window.print(); });

    // Print-only header so a saved PDF shows where it came from.
    var ph = el('div', { 'class': 'ssl-print-header' }, 'Suno Saathi Tools - ' + location.host + location.pathname);
    document.body.insertBefore(ph, document.body.firstChild);
  }

  /* ---------- Recent calculations (stored only on this device) ---------- */
  function readHistory() {
    var raw = store('get', HISTORY_KEY);
    if (!raw) { return []; }
    try {
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }
  function safePath(u) { return typeof u === 'string' && /^[a-z0-9\-\/]+\.html(\?[^\s"'<>]*)?$/i.test(u); }

  function relativePath() {
    var rootPath = new URL(ROOT).pathname;
    var p = location.pathname;
    if (p.indexOf(rootPath) === 0) { p = p.slice(rootPath.length); } else { p = p.replace(/^\//, ''); }
    if (p === '' || p.slice(-1) === '/') { p += 'index.html'; }
    return p;
  }

  function summarise() {
    var lines = resultText().split('\n');
    for (var i = 0; i < lines.length; i++) {
      if (/\d/.test(lines[i]) && lines[i].length <= 90) { return lines[i]; }
    }
    return (lines[0] || '').slice(0, 90);
  }

  function looksLikeError(text) {
    return text.length < 110 && /please|invalid|enter |must |cannot|can't|error|greater than|valid/i.test(text);
  }

  function recordHistory() {
    var text = resultText();
    if (!text || looksLikeError(text)) { return; }
    var q = buildQuery();
    var path = relativePath();
    var item = { t: pageTitle(), u: path + (q.toString() ? '?' + q.toString() : ''), s: summarise(), ts: Date.now() };
    var list = readHistory().filter(function (x) { return x && x.u !== item.u; });
    list.unshift(item);
    store('set', HISTORY_KEY, JSON.stringify(list.slice(0, 12)));
    renderRecent();
    try { history.replaceState(null, '', pageUrlWith(q)); } catch (e) { /* e.g. file:// preview */ }
  }

  function renderRecent() {
    var host = document.getElementById('sslRecentHome');
    var onHome = !!host;
    if (!host) { host = document.getElementById('sslRecent'); }
    var list = readHistory().filter(function (x) { return x && safePath(x.u) && typeof x.t === 'string'; });
    var limit = onHome ? 6 : 5;

    if (!host) {
      if (!list.length) { return; }
      host = el('section', { id: 'sslRecent', 'class': 'ssl-recent', 'aria-label': 'Recent calculations' });
      var footer = document.querySelector('footer');
      if (footer && footer.parentNode) { footer.parentNode.insertBefore(host, footer); } else { document.body.appendChild(host); }
    }
    host.textContent = '';
    if (!list.length) { host.hidden = true; return; }
    host.hidden = false;
    if (onHome) { host.className = 'section'; }

    var wrap = onHome ? el('div', { 'class': 'ssl-recent' }) : host;
    wrap.appendChild(el('h2', null, 'Recent calculations'));
    var ul = el('ul');
    list.slice(0, limit).forEach(function (x) {
      var li = el('li');
      var a = el('a', { href: ROOT + x.u }, x.t);
      li.appendChild(a);
      if (x.s) { li.appendChild(el('span', null, String(x.s).slice(0, 90))); }
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    var clear = el('button', { type: 'button' }, 'Clear history');
    clear.addEventListener('click', function () { store('del', HISTORY_KEY); renderRecent(); });
    wrap.appendChild(clear);
    wrap.appendChild(el('p', { 'class': 'ssl-note' }, 'Saved only in this browser on your device. Nothing is sent to our servers.'));
    if (onHome) { host.appendChild(wrap); }
  }

  /* Tidy floating-point noise in results (e.g. 14.999999999999996 -> 15).
     Only numbers with 10 or more decimal places are touched, and exponent forms
     such as 6.02214076e23 are left alone. The calculators' own maths is not changed. */
  function tidyNumbers(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var node;
    while ((node = walker.nextNode())) {
      var t = node.nodeValue;
      if (!t || t.indexOf('.') === -1) { continue; }
      var fixed = t.replace(/(\d+\.\d{10,})(?![\d]|[eE][+-]?\d)/g, function (m) {
        var n = parseFloat(m);
        if (!isFinite(n) || Math.abs(n) < 1e-4) { return m; }
        return String(Number(n.toPrecision(8)));
      });
      if (fixed !== t) { node.nodeValue = fixed; }
    }
  }

  function watchResult() {
    var r = document.getElementById('result');
    if (!r || !window.MutationObserver) { return; }
    var busy = false;
    var obs = new MutationObserver(function () {
      if (busy) { return; }
      busy = true;
      obs.disconnect();
      try { tidyNumbers(r); } catch (e) { /* ignore */ }
      obs.observe(r, { childList: true, subtree: true, characterData: true });
      busy = false;
    });
    obs.observe(r, { childList: true, subtree: true, characterData: true });
    try { tidyNumbers(r); } catch (e) { /* ignore */ }
  }

  function setupCalculator() {
    setupToolbar();
    watchResult();
    var restored = restoreFromUrl();
    document.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b || b.closest('.ssl-toolbar, .ssl-recent')) { return; }
      var oc = b.getAttribute('onclick') || '';
      if (/calculate\s*\(/.test(oc)) { setTimeout(recordHistory, 150); }
    });
    if (restored) { setTimeout(recordHistory, 250); }
  }

  /* ---------- 4. Homepage smart search ---------- */
  var STOP = { calculator: 1, calculate: 1, calc: 1, find: 1, of: 1, the: 1, to: 1, for: 1, a: 1, an: 1, and: 1, how: 1, what: 1, is: 1, tool: 1, free: 1, online: 1 };

  function tokens(q) {
    return q.toLowerCase().replace(/[^a-z0-9=/+\-.²]+/g, ' ').split(' ').filter(function (t) {
      return t && !STOP[t] && !/^[0-9.]+$/.test(t);
    });
  }

  function scoreItem(item, toks) {
    var title = item.t.toLowerCase();
    var tWords = title.replace(/[^a-z0-9]+/g, ' ').split(' ');
    var kw = ' ' + (item.k || '').toLowerCase() + ' ';
    var score = 0;
    toks.forEach(function (t) {
      if (tWords.indexOf(t) !== -1) { score += 6; }
      else if (title.indexOf(t) !== -1) { score += 4; }
      if (kw.indexOf(' ' + t + ' ') !== -1) { score += 3; }
      else if (t.length >= 3 && kw.indexOf(t) !== -1) { score += 1; }
    });
    return score;
  }

  function setupSearch() {
    var input = document.getElementById('searchInput');
    var tools = window.SSL_TOOLS;
    if (!input || !tools) { return; }
    var hubs = window.SSL_HUBS || [];
    var box = el('ul', { 'class': 'ssl-sr', id: 'sslSearchResults', 'aria-label': 'Search results' });
    var area = input.closest('.search-area') || input.parentNode;
    area.appendChild(box);

    function find(q) {
      var toks = tokens(q);
      if (!toks.length) { return null; }
      var hits = [];
      tools.forEach(function (t) { var s = scoreItem(t, toks); if (s > 0) { hits.push({ s: s, t: t.t, u: t.u, tag: t.s }); } });
      hits.sort(function (a, b) { return b.s - a.s; });
      var out = hits.slice(0, 7);
      var hubHits = [];
      hubs.forEach(function (h) { var s = scoreItem({ t: h.t, k: h.k }, toks); if (s > 0) { hubHits.push({ s: s, t: h.t, u: h.u, tag: 'Chapter guide' }); } });
      hubHits.sort(function (a, b) { return b.s - a.s; });
      return out.concat(hubHits.slice(0, 2));
    }

    function render() {
      var q = input.value.trim();
      box.textContent = '';
      if (!q) { return []; }
      var res = find(q);
      if (res === null) { return []; }
      if (!res.length) {
        box.appendChild(el('li', { 'class': 'ssl-sr-none' }, 'No match found. Try words like force, pH, pendulum or molarity, or browse the full list below.'));
        return [];
      }
      res.forEach(function (r) {
        var li = el('li');
        var a = el('a', { href: ROOT + r.u });
        a.appendChild(el('strong', null, r.t));
        a.appendChild(el('span', null, r.tag));
        li.appendChild(a);
        box.appendChild(li);
      });
      return res;
    }

    input.addEventListener('input', render);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        var res = render();
        if (res.length) { location.href = ROOT + res[0].u; }
      }
    });
    window.sslSearch = { go: function () { var res = render(); if (res.length) { location.href = ROOT + res[0].u; } } };
  }

  /* ---------- start ---------- */
  setupServiceWorker();
  ready(function () {
    setupTheme();
    if (isCalculatorPage()) { setupCalculator(); }
    renderRecent();
    setupSearch();
  });
})();
