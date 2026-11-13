/*
  Magic Layer page logic.

  Flow:  question -> /v1/route (or built-in rules) -> shows which calculator + values
         -> "Run" executes the REAL calculator page in a hidden frame and reads its result
         -> "Explain" / "Step-by-step" -> /v1/explain (AI, with checks) or built-in templates.

  The AI never calculates. Numbers come from the site's calculators.
  No API keys here, ever. If the backend is missing or fails, everything falls back to the
  built-in engine (magic-engine.js), so the page keeps working without AI.
  All dynamic text is inserted with textContent (never innerHTML).
*/
(function () {
  'use strict';
  var E = window.MagicEngine, DATA = window.MAGIC_DATA, CFG = window.MAGIC_CONFIG || {};
  E.init(DATA.registry, DATA.nlp, DATA.strings);

  var $ = function (id) { return document.getElementById(id); };
  var out = $('mgOut');
  var state = { lang: 'en', online: false, usage: null, ctx: null, api: '', clientId: '' };

  // ---------------------------------------------------------------- storage helpers (safe if blocked)
  function store(key, val) { try { if (val === undefined) { return localStorage.getItem(key); } if (val === null) { localStorage.removeItem(key); } else { localStorage.setItem(key, val); } } catch (e) { /* ignore */ } return null; }
  function clientId() {
    var id = store('magicClientId');
    if (!id) { id = 'c' + Math.random().toString(36).slice(2, 12) + Date.now().toString(36); store('magicClientId', id); }
    return id;
  }
  (function readSettings() {
    var q = new URLSearchParams(location.search);
    if (q.has('api')) { var v = (q.get('api') || '').trim(); store('magicApi', v === '' ? null : v); }
    state.api = (store('magicApi') || CFG.API_BASE || '').replace(/\/+$/, '');
    var l = store('magicLang') || CFG.DEFAULT_LANG || 'en';
    state.lang = l === 'hi' ? 'hi' : 'en';
    state.clientId = clientId();
  })();

  var t = function (key, vars) { return E.tr(state.lang, key, vars); };

  // ---------------------------------------------------------------- tiny DOM helper
  function h(tag, props, kids) {
    var el = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      if (k === 'text') { el.textContent = props[k]; } else if (k === 'class') { el.className = props[k]; }
      else if (k.slice(0, 2) === 'on') { el.addEventListener(k.slice(2), props[k]); } else { el.setAttribute(k, props[k]); }
    });
    (kids || []).forEach(function (c) { if (c) { el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); } });
    return el;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function card(title) { var c = h('section', { 'class': 'mg-card' }); if (title) { c.appendChild(h('h2', { text: title })); } return c; }
  function note(text) { return h('p', { 'class': 'mg-note', text: text }); }
  function busy(text) { return h('p', { 'class': 'mg-note' }, [h('span', { 'class': 'mg-spin' }), text]); }
  function safeUrl(u) { return /^(physics|chemistry|chapters)\/[a-z0-9-]+\.html$/.test(u) ? '../' + u : null; }

  // ---------------------------------------------------------------- static text
  var EX = ['ui.ex1', 'ui.ex2', 'ui.ex3', 'ui.ex4'];
  function applyStaticText() {
    document.documentElement.lang = state.lang;
    $('mgTitle').textContent = t('ui.title'); $('mgBeta').textContent = t('ui.beta'); $('mgSub').textContent = t('ui.subtitle');
    $('mgBack').setAttribute('aria-label', t('ui.back')); $('mgBack').setAttribute('title', t('ui.back'));
    $('tabAsk').textContent = t('ui.tab_ask'); $('tabFormula').textContent = t('ui.tab_formula');
    $('mgQuestion').placeholder = t('ui.placeholder'); $('mgQLabel').textContent = t('ui.placeholder');
    $('mgAsk').textContent = t('ui.ask');
    $('mgFormulaQ').placeholder = t('ui.formula_placeholder'); $('mgFLabel').textContent = t('ui.formula_placeholder');
    $('mgFind').textContent = t('ui.find'); $('mgUseAiText').textContent = t('ui.use_ai_formula');
    $('mgDisclaimer').textContent = t('ui.disclaimer');
    $('mgLangEn').setAttribute('aria-pressed', String(state.lang === 'en')); $('mgLangHi').setAttribute('aria-pressed', String(state.lang === 'hi'));
    $('mgAiRow').hidden = !state.online;
    var ex = $('mgExamples'); clear(ex);
    ex.appendChild(h('span', { 'class': 'mg-note', text: t('ui.examples') + ':' }));
    EX.forEach(function (k) { ex.appendChild(h('button', { type: 'button', 'class': 'mg-chip', text: t(k), onclick: function () { $('mgQuestion').value = t(k); ask(); } })); });
    renderStatus();
  }
  function renderStatus() {
    var s = $('mgStatus');
    if (!state.online) { s.textContent = t('ui.offline'); return; }
    var u = state.usage;
    s.textContent = u ? (u.remaining > 0 && u.ai_available !== false ? t('ui.usage', { n: u.remaining }) : t('ui.usage_none')) : '';
  }
  function setLang(l) { state.lang = l; store('magicLang', l); applyStaticText(); }

  // ---------------------------------------------------------------- backend calls
  function api(path, body) {
    var ctl = ('AbortController' in window) ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) { ctl.abort(); } }, CFG.REQUEST_TIMEOUT_MS || 20000);
    var headers = { 'Content-Type': 'application/json', 'X-Client-Id': state.clientId };
    var token = store('magicToken'); if (token) { headers.Authorization = 'Bearer ' + token; }   // future login
    return fetch(state.api + path, { method: body ? 'POST' : 'GET', headers: headers, body: body ? JSON.stringify(body) : undefined, signal: ctl ? ctl.signal : undefined })
      .then(function (r) { clearTimeout(timer); return r.json().catch(function () { return {}; }).then(function (j) { return { status: r.status, data: j }; }); })
      .catch(function (e) { clearTimeout(timer); throw e; });
  }
  function connect() {
    if (!state.api) { state.online = false; applyStaticText(); return; }
    $('mgStatus').textContent = t('ui.waking');
    api('/v1/health').then(function (r) {
      state.online = r.status === 200 && r.data.status === 'ok';
      return state.online ? api('/v1/usage').then(function (u) { if (u.status === 200) { state.usage = u.data; } }) : null;
    }).catch(function () { state.online = false; }).then(applyStaticText);
  }
  function remember(data) { if (data && data.usage) { state.usage = data.usage; renderStatus(); } }

  // ---------------------------------------------------------------- ASK
  function localRoute(q) {
    var rr = E.route(q);
    var sugg = rr.shortlist.slice(0, 3).map(function (p) { var tl = E.tool(p[0]); return { tool_id: tl.id, name: tl.name, url: tl.url }; });
    return { ok: true, source: 'rules', route: rr.confidence >= 0.5 ? rr.route : null, suggestions: sugg, notice: '' };
  }
  function ask() {
    var q = $('mgQuestion').value.trim();
    if (!q) { return; }
    clear(out); out.appendChild(card().appendChild(busy(t('ui.loading'))).parentNode);
    $('mgAsk').disabled = true;
    var done = function (data) { $('mgAsk').disabled = false; remember(data); renderRoute(data); };
    if (state.online) {
      api('/v1/route', { question: q, lang: state.lang }).then(function (r) {
        if (r.status === 200) { done(r.data); } else { done(Object.assign(localRoute(q), { notice: r.data && r.data.error === 'too_long' ? t('n.too_long') : t('n.bad_request') })); }
      }).catch(function () { done(Object.assign(localRoute(q), { notice: t('ui.fallback_offline') })); });
    } else { done(localRoute(q)); }
  }
  function toRoute(data) {
    if (!data || !data.route) { return null; }
    try { return E.validateRoute(data.route.tool_id, data.route.mode, data.route.inputs, data.route.selects); } catch (e) { return null; }
  }
  function renderRoute(data) {
    clear(out);
    var route = toRoute(data);
    var c = card(route ? t('ui.picked') + ': ' + route.tool_name + (route.mode_label ? ' — ' + route.mode_label : '') : '');
    if (data.notice) { c.appendChild(h('p', { 'class': 'mg-warn', text: data.notice })); }
    if (!route) {
      c.appendChild(h('p', { 'class': 'mg-text', text: t('ui.no_match') }));
      var ul = h('ul', { 'class': 'mg-list' });
      (data.suggestions || []).forEach(function (s) {
        var u = safeUrl(s.url); var tl = E.tool(s.tool_id);
        if (u && tl) { ul.appendChild(h('li', {}, [h('a', { href: u, text: tl.name })])); }
      });
      c.appendChild(ul); out.appendChild(c); return;
    }
    state.ctx = { route: route, resultText: '' };
    var fields = E.fieldsOf(E.tool(route.tool_id), route.mode), table = h('table', { 'class': 'mg-vals' });
    fields.forEach(function (f) {
      if (Object.prototype.hasOwnProperty.call(route.inputs, f.id)) { table.appendChild(h('tr', {}, [h('td', { text: f.label }), h('td', { text: String(route.inputs[f.id]) })])); }
    });
    Object.keys(route.selects).forEach(function (k) { table.appendChild(h('tr', {}, [h('td', { text: k }), h('td', { text: route.selects[k] })])); });
    if (table.childNodes.length) { c.appendChild(h('p', { 'class': 'mg-note', text: t('ui.with_values') + ':' })); c.appendChild(table); }
    c.appendChild(note(data.source === 'ai' ? t('ui.src_ai') : t('ui.src_rules')));
    var complete = route.missing.length === 0;
    if (!complete) { c.appendChild(h('p', { 'class': 'mg-warn', text: t('ui.missing') })); }
    var link = '../' + route.url + (route.query ? '?' + route.query : '');
    if (complete) { c.appendChild(h('button', { type: 'button', 'class': 'mg-btn mg-primary', id: 'mgRun', text: t('ui.run'), onclick: function (ev) { runIt(ev.target); } })); }
    c.appendChild(h('a', { 'class': 'mg-btn', href: link, text: t('ui.open') }));
    out.appendChild(c);
    if (!complete) { return; }
    out.appendChild(note(t('ui.run_hint')));
  }

  // ---------------------------------------------------------------- RUN the real calculator (hidden frame)
  function runCalculator(route) {
    return new Promise(function (resolve) {
      var f = document.createElement('iframe'), finished = false, timer;
      f.setAttribute('aria-hidden', 'true'); f.setAttribute('tabindex', '-1'); f.setAttribute('title', 'calculator');
      f.style.cssText = 'position:absolute;left:-9999px;top:0;width:420px;height:900px;border:0;visibility:hidden';
      function finish(v) { if (finished) { return; } finished = true; clearTimeout(timer); setTimeout(function () { if (f.parentNode) { f.parentNode.removeChild(f); } }, 0); resolve(v); }
      timer = setTimeout(function () { finish(null); }, 7000);
      f.onload = function () {
        var tries = 0;
        (function poll() {
          try {
            var d = f.contentDocument, r = d && d.getElementById('result');
            if (r && r.offsetParent !== null && /\d/.test(r.innerText)) { return finish(r.innerText.trim()); }
          } catch (e) { return finish(null); }        // different origin (for example a file:// preview)
          if (++tries > 50) { return finish(null); }
          setTimeout(poll, 100);
        })();
      };
      f.src = '../' + route.url + '?' + route.query;
      document.body.appendChild(f);
    });
  }
  function runIt(btn) {
    var route = state.ctx && state.ctx.route; if (!route) { return; }
    btn.disabled = true;
    var spin = busy(t('ui.loading')); btn.parentNode.appendChild(spin);
    runCalculator(route).then(function (text) {
      spin.remove(); btn.disabled = false;
      if (!text) { btn.parentNode.appendChild(h('p', { 'class': 'mg-warn', text: t('ui.hint_iframe') })); return; }
      state.ctx.resultText = text; renderResult(text);
    });
  }
  function renderResult(text) {
    var old = $('mgResultCard'); if (old) { old.remove(); }
    var c = card(t('ui.result')); c.id = 'mgResultCard';
    c.appendChild(h('pre', { 'class': 'mg-result', text: text }));
    c.appendChild(note(t('ui.verified')));
    c.appendChild(h('button', { type: 'button', 'class': 'mg-btn mg-primary', text: t('ui.explain'), onclick: function (e) { explain('explain', e.target); } }));
    c.appendChild(h('button', { type: 'button', 'class': 'mg-btn', text: t('ui.steps'), onclick: function (e) { explain('steps', e.target); } }));
    c.appendChild(h('button', { type: 'button', 'class': 'mg-btn', text: t('ui.find_formula'), onclick: function () { showTab('formula'); $('mgFormulaQ').value = state.ctx.route.tool_name + ' ' + (state.ctx.route.mode_label || ''); findFormula(); } }));
    out.appendChild(c); c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---------------------------------------------------------------- EXPLAIN / STEPS
  function localExplain(kind) {
    var ctx = state.ctx, route = ctx.route, tool = E.tool(route.tool_id);
    var labels = {}; E.fieldsOf(tool, route.mode).forEach(function (f) { labels[f.id] = f.label; });
    var inputs = Object.keys(route.inputs).map(function (k) { return { label: labels[k] || k, value: route.inputs[k] }; });
    var text = kind === 'steps' ? E.steps(state.lang, ctx.resultText) : E.explain(state.lang, route.tool_name, route.mode_label, tool.formula || '', inputs, ctx.resultText);
    var ch = E.chapterFor(tool);
    return { ok: true, text: text, source: 'template', kind: kind, notice: '',
             next: { related: E.related(tool).slice(0, 4).map(function (x) { return { name: x.name, url: x.url }; }), chapter: ch ? { url: ch.url, title: ch.title } : null } };
  }
  function explain(kind, btn) {
    var ctx = state.ctx; if (!ctx || !ctx.resultText) { return; }
    var holder = h('section', { 'class': 'mg-card' }, [busy(t('ui.loading'))]); out.appendChild(holder);
    btn.disabled = true;
    var finish = function (d) { btn.disabled = false; remember(d); holder.remove(); renderExplain(d); };
    if (state.online) {
      api('/v1/explain', { tool_id: ctx.route.tool_id, mode: ctx.route.mode, inputs: ctx.route.inputs, selects: ctx.route.selects, result_text: ctx.resultText, lang: state.lang, kind: kind })
        .then(function (r) { if (r.status === 200) { finish(r.data); } else { var d = localExplain(kind); d.notice = t('n.bad_request'); finish(d); } })
        .catch(function () { var d = localExplain(kind); d.notice = t('ui.fallback_offline'); finish(d); });
    } else { finish(localExplain(kind)); }
  }
  function renderExplain(d) {
    var c = card(d.kind === 'steps' ? t('ui.steps') : t('ui.explain'));
    if (d.notice) { c.appendChild(h('p', { 'class': 'mg-warn', text: d.notice })); }
    c.appendChild(h('p', { 'class': 'mg-text', text: d.text }));
    c.appendChild(note(d.source === 'ai' ? t('ui.src_ai_text') : t('ui.src_template')));
    out.appendChild(c);
    var nx = d.next || {}, items = [];
    (nx.related || []).forEach(function (r) { var u = safeUrl(r.url); if (u) { items.push(h('li', {}, [h('a', { href: u, text: r.name })])); } });
    var chap = nx.chapter && safeUrl(nx.chapter.url);
    if (items.length || chap) {
      var n = card(t('ui.next'));
      if (items.length) { n.appendChild(h('h3', { text: t('ui.related') })); n.appendChild(h('ul', { 'class': 'mg-list' }, items)); }
      if (chap) { n.appendChild(h('a', { 'class': 'mg-btn', href: chap, text: t('ui.chapter') + ': ' + nx.chapter.title })); }
      out.appendChild(n);
    }
    c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---------------------------------------------------------------- FORMULA FINDER
  function findFormula() {
    var q = $('mgFormulaQ').value.trim(); if (!q) { return; }
    clear(out); out.appendChild(card().appendChild(busy(t('ui.loading'))).parentNode);
    var useAi = state.online && $('mgUseAi').checked;
    var done = function (d) { remember(d); renderFormulas(d); };
    if (state.online) {
      api('/v1/formula', { query: q, lang: state.lang, use_ai: useAi }).then(function (r) {
        if (r.status === 200) { done(r.data); } else { done({ formulas: E.findFormulas(q, 6), summary: '', notice: t('n.bad_request') }); }
      }).catch(function () { done({ formulas: E.findFormulas(q, 6), summary: '', notice: t('ui.fallback_offline') }); });
    } else { done({ formulas: E.findFormulas(q, 6), summary: '', source: 'rules', notice: '' }); }
  }
  function renderFormulas(d) {
    clear(out);
    var c = card(t('ui.formulas_found'));
    if (d.notice) { c.appendChild(h('p', { 'class': 'mg-warn', text: d.notice })); }
    if (d.summary) { c.appendChild(h('p', { 'class': 'mg-text', text: d.summary })); c.appendChild(note(t('ui.src_ai_text'))); }
    if (!(d.formulas || []).length) { c.appendChild(h('p', { 'class': 'mg-text', text: t('ui.no_match') })); }
    out.appendChild(c);
    (d.formulas || []).forEach(function (f) {
      var tl = E.tool(f.tool_id); if (!tl) { return; }
      var u = safeUrl(tl.url), card2 = card(tl.name + (f.mode_label ? ' — ' + f.mode_label : ''));
      if (tl.formula) { card2.appendChild(h('div', { 'class': 'mg-formula', text: tl.formula.slice(0, 240) })); }
      if (u) { card2.appendChild(h('a', { 'class': 'mg-btn mg-primary', href: u, text: t('ui.use_calc') })); }
      var cu = f.chapter && safeUrl(f.chapter.url);
      if (cu) { card2.appendChild(h('a', { 'class': 'mg-btn', href: cu, text: t('ui.chapter') })); }
      out.appendChild(card2);
    });
  }

  // ---------------------------------------------------------------- tabs and wiring
  function showTab(name) {
    var ask = name === 'ask';
    $('panelAsk').hidden = !ask; $('panelFormula').hidden = ask;
    $('tabAsk').setAttribute('aria-selected', String(ask)); $('tabFormula').setAttribute('aria-selected', String(!ask));
  }
  $('tabAsk').addEventListener('click', function () { showTab('ask'); });
  $('tabFormula').addEventListener('click', function () { showTab('formula'); });
  $('mgAsk').addEventListener('click', ask);
  $('mgFind').addEventListener('click', findFormula);
  $('mgLangEn').addEventListener('click', function () { setLang('en'); });
  $('mgLangHi').addEventListener('click', function () { setLang('hi'); });
  $('mgQuestion').addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { ask(); } });
  $('mgFormulaQ').addEventListener('keydown', function (e) { if (e.key === 'Enter') { findFormula(); } });

  applyStaticText();
  connect();
  window.__magic = { state: state, ask: ask, setLang: setLang };   // handy for tests and debugging
})();
