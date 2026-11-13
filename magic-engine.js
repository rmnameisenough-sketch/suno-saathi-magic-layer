/*
  Magic Layer: offline engine (no AI, no network).

  This is a JavaScript port of backend/app/{text,rules,registry,fallback}.py. It reads the same data
  tables (nlp.json, registry.json, strings.json), so the website works with no backend at all and gives
  the same routing as the server's rule layer. tests/ cross-check the two against each other.

  Plain JavaScript, no libraries, no storage, no network.
*/
(function (root) {
  'use strict';

  var D = null;            // { reg, nlp, strings }
  var cache = {};

  function init(reg, nlp, strings) {
    var tools = {};
    reg.tools.forEach(function (t) { tools[t.id] = t; });
    var elAlt = nlp.elements.slice().sort(function (a, b) { return b.length - a.length; }).join('|');
    var unitRe = nlp.unit_re;
    var hindi = Object.keys(nlp.hindi).sort(function (a, b) { return b.length - a.length; });
    D = {
      reg: reg, tools: tools, nlp: nlp, strings: strings,
      stop: new Set(nlp.stopwords), filler: new Set(nlp.filler), labelStop: new Set(nlp.label_stop),
      keyWords: new Set(nlp.key_words), ambiguous: new Set(nlp.ambiguous_classes),
      hindiKeys: hindi,
      quantityRe: function () { return new RegExp('(?<![\\w.])(' + nlp.num_re + ')\\s*(' + unitRe + ')?(?![a-z0-9])', 'gi'); },
      elAlt: elAlt,
      formulaRe: function () { return new RegExp('(?<![A-Za-z0-9])((?:(?:' + elAlt + ')\\d*|\\((?:(?:' + elAlt + ')\\d*)+\\)\\d*)+)(?![A-Za-z0-9])', 'g'); },
      elementRe: new RegExp(elAlt, 'g')
    };
    buildIndex();
    return D;
  }

  // ---------------------------------------------------------------- text helpers (port of text.py)
  var DEV = '०१२३४५६७८९';
  function normalise(text) {
    var t = String(text || '').normalize('NFKC');
    t = t.replace(/[०-९]/g, function (c) { return String(DEV.indexOf(c)); });
    t = t.replace(/²/g, '2').replace(/³/g, '3').replace(/⁻/g, '-').replace(/¹/g, '1').replace(/·/g, ' ')
         .replace(/×/g, '*').replace(/−/g, '-').replace(/–/g, '-').replace(/÷/g, '/');
    t = t.toLowerCase();
    D.hindiKeys.forEach(function (hi) {
      if (t.indexOf(hi) !== -1) { t = t.split(hi).join(' ' + D.nlp.hindi[hi] + ' '); }
    });
    return t.replace(/\s+/g, ' ').trim();
  }
  function tokens(text) {
    var t = normalise(text);
    return (t.match(/[a-z0-9=^/.]+/g) || []).filter(function (w) { return !D.stop.has(w) && w.length > 0; });
  }
  function squash(text) { return normalise(text).replace(/[\s*]+/g, ''); }
  function unitClass(unit) {
    if (!unit) { return null; }
    var u = String(unit).toLowerCase().replace(/²/g, '2').replace(/³/g, '3');
    return Object.prototype.hasOwnProperty.call(D.nlp.unit_class, u) ? D.nlp.unit_class[u] : null;
  }
  function labelClass(label) {
    var low = normalise(label);
    var m = /\(([^)]*)\)/.exec(low);
    if (m) { var c = unitClass(m[1].trim()); if (c) { return c; } }
    var ws = low.match(/[a-z]+/g) || [];
    for (var i = 0; i < ws.length; i++) {
      if (Object.prototype.hasOwnProperty.call(D.nlp.label_word_class, ws[i])) { return D.nlp.label_word_class[ws[i]]; }
    }
    return null;
  }
  function canonUnit(u) {
    if (!u) { return null; }
    u = String(u).toLowerCase().replace(/²/g, '2').replace(/³/g, '3');
    return Object.prototype.hasOwnProperty.call(D.nlp.unit_canon, u) ? D.nlp.unit_canon[u] : u;
  }
  function labelUnit(label) {
    var m = /\(([^)]*)\)/.exec(normalise(label));
    return m ? canonUnit(m[1].trim()) : null;
  }

  // ---------------------------------------------------------------- quantities and assignment (port of rules.py)
  function extractQuantities(question) {
    var t = normalise(question), out = [], prevEnd = 0, re = D.quantityRe(), m;
    while ((m = re.exec(t)) !== null) {
      var v = parseFloat(m[1]);
      if (isNaN(v)) { continue; }
      var unit = canonUnit(m[2]);
      var rawBefore = t.slice(Math.max(prevEnd, m.index - 28), m.index);
      prevEnd = m.index + m[0].length;
      var words = (rawBefore.match(/[a-z]+/g) || []).filter(function (w) { return !D.filler.has(w); });
      var sym = /(?<![a-z])[a-z]\s*=?\s*$/.exec(rawBefore);
      out.push({ value: v, unit: unit, cls: unitClass(unit), before: words.slice(-2).join(' ') + (sym ? ' ' + sym[0] : '') });
      if (m[0].length === 0) { re.lastIndex++; }
    }
    return out;
  }
  function stem(w) {
    var sufs = ['ing', 'es', 'ed', 's'];
    for (var i = 0; i < sufs.length; i++) {
      if (w.length >= sufs[i].length && w.slice(-sufs[i].length) === sufs[i] && w.length - sufs[i].length >= 4) { return w.slice(0, -sufs[i].length); }
    }
    return w;
  }
  function labelWords(label) {
    var base = normalise(label).replace(/\([^)]*\)/g, ' ');
    return (base.match(/[a-z]{3,}/g) || []).filter(function (w) { return D.keyWords.has(w) && !D.labelStop.has(w); });
  }
  function symbols(label) {
    var s = new Set(), stripped = label.replace(/\([^)]*\)/g, ' '), re = /(?<![A-Za-z])[A-Za-z](?![A-Za-z])/g, m;
    while ((m = re.exec(stripped)) !== null) { s.add(m[0].toLowerCase()); }
    if (label.toLowerCase().indexOf('gravity') !== -1) { s.add('g'); }
    return s;
  }
  function pairScore(q, f) {
    var s = 0, isConst = f.label.toLowerCase().indexOf('gravity') !== -1, fc = labelClass(f.label);
    if (q.cls && fc && q.cls === fc && !isConst) { s += 3; }
    var clash = !!(q.cls && fc && q.cls !== fc);
    var bw = new Set((q.before.match(/[a-z]+/g) || []).map(stem));
    if (labelWords(f.label).some(function (w) { return bw.has(stem(w)); })) { s += 4; }
    symbols(f.label).forEach(function (sym) {
      if (new RegExp('(?<![a-z])' + sym.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*=?\\s*$').test(q.before)) { s += 5; }
    });
    if (clash && !isConst) { s -= 5; }
    return Math.max(0, s);
  }
  function converted(q, f) {
    var target = labelUnit(f.label);
    if (!target || !q.unit || target === q.unit) { return q.value; }
    var factor = D.nlp.conversions[q.unit + '|' + target];
    if (factor === undefined) { return null; }
    return parseFloat((q.value * factor).toPrecision(12));
  }
  function assignQuantities(question, tool, fields) {
    var qs = extractQuantities(question), inputs = {}, selects = {};
    var freeQ = qs.map(function (_, i) { return i; });
    var freeF = fields.filter(function (f) { return f.type !== 'text'; });
    var scores = [];
    freeQ.forEach(function (i) { freeF.forEach(function (f) { scores.push({ i: i, fid: f.id, s: pairScore(qs[i], f) }); }); });
    for (;;) {
      var fids = new Set(freeF.map(function (f) { return f.id; }));
      var cand = scores.filter(function (x) { return freeQ.indexOf(x.i) !== -1 && fids.has(x.fid); });
      if (!cand.length) { break; }
      var best = cand.reduce(function (a, b) {          // Python max() over (score, i, fid) tuples
        if (b.s !== a.s) { return b.s > a.s ? b : a; }
        if (b.i !== a.i) { return b.i > a.i ? b : a; }
        return b.fid > a.fid ? b : a;
      });
      if (best.s < 3) { break; }
      var rivals = scores.filter(function (x) {
        return ((x.i === best.i && x.fid !== best.fid) || (x.fid === best.fid && x.i !== best.i)) &&
               freeQ.indexOf(x.i) !== -1 && fids.has(x.fid) && x.s >= best.s;
      });
      freeQ.splice(freeQ.indexOf(best.i), 1);
      freeF = freeF.filter(function (f) { return f.id !== best.fid; });
      if (rivals.length) { continue; }
      var f = fields.filter(function (x) { return x.id === best.fid; })[0], q = qs[best.i];
      if (labelUnit(f.label) === null && q.unit !== null && D.ambiguous.has(q.cls)) {
        var chosen = null;
        (tool.extras || []).forEach(function (ex) {
          ex.options.forEach(function (o) { if (canonUnit(o.v) === q.unit) { chosen = [ex.id, o.v]; } });
        });
        if (chosen === null) { continue; }
        selects[chosen[0]] = chosen[1];
        inputs[best.fid] = q.value;
        continue;
      }
      var val = converted(q, f);
      if (val !== null) { inputs[best.fid] = val; }
    }
    return { inputs: inputs, selects: selects };
  }
  function extractFormula(question) {
    var re = D.formulaRe(), m, s = String(question || '');
    while ((m = re.exec(s)) !== null) {
      var cand = m[1], n = (cand.replace(/\d/g, '').match(D.elementRe) || []).length;
      if (n >= 2 || /\d/.test(cand)) {
        if (cand.toLowerCase() === 'a' || cand.toLowerCase() === 'i') { continue; }
        return cand;
      }
    }
    return null;
  }

  // ---------------------------------------------------------------- registry validation (port of registry.py)
  function hasRealDefault(f) { return f['default'] !== undefined && f['default'] !== '' && (f.label || '').toLowerCase().indexOf('gravity') !== -1; }
  function validateRoute(toolId, mode, inputs, selects) {
    var tool = D.tools[String(toolId)];
    if (!tool) { throw new Error('unknown tool'); }
    var mk = '';
    if (tool.modeSelect) {
      mk = (mode === null || mode === undefined) ? '' : String(mode);
      if (!Object.prototype.hasOwnProperty.call(tool.modes, mk)) { throw new Error('unknown mode'); }
    }
    var fields = tool.modes[mk].fields, provided = inputs || {}, clean = {};
    fields.forEach(function (f) {
      if (!Object.prototype.hasOwnProperty.call(provided, f.id)) { return; }
      var raw = provided[f.id];
      if (f.type === 'text') {
        var s = String(raw).trim();
        if (!/^[A-Za-z0-9().\[\]\u00b7 \-]{1,40}$/.test(s)) { throw new Error('invalid text value'); }
        clean[f.id] = s;
      } else {
        if (typeof raw === 'boolean') { throw new Error('invalid number'); }
        var v = Number(raw);
        if (raw === '' || raw === null || !isFinite(v) || Math.abs(v) > 1e30) { throw new Error('invalid number'); }
        clean[f.id] = v;
      }
    });
    var cleanSel = {};
    (tool.extras || []).forEach(function (ex) {
      if (selects && Object.prototype.hasOwnProperty.call(selects, ex.id)) {
        var val = String(selects[ex.id]);
        if (!ex.options.some(function (o) { return o.v === val; })) { throw new Error('invalid option'); }
        cleanSel[ex.id] = val;
      }
    });
    var params = [];
    if (tool.modeSelect) { params.push([tool.modeSelect, mk]); }
    Object.keys(cleanSel).forEach(function (k) { params.push([k, cleanSel[k]]); });
    Object.keys(clean).forEach(function (k) { params.push([k, String(clean[k])]); });
    var usp = new URLSearchParams();
    params.forEach(function (p) { usp.append(p[0], p[1]); });
    var paramsObj = {}; params.forEach(function (p) { paramsObj[p[0]] = p[1]; });
    return {
      tool_id: tool.id, tool_name: tool.name, url: tool.url, mode: mk, mode_label: tool.modes[mk].label,
      inputs: clean, selects: cleanSel,
      missing: fields.filter(function (f) { return !Object.prototype.hasOwnProperty.call(clean, f.id) && !hasRealDefault(f); }).map(function (f) { return f.id; }),
      params: paramsObj, query: usp.toString()
    };
  }

  // ---------------------------------------------------------------- shortlist, route, formula finder
  function buildIndex() {
    D.docs = {}; D.nameTokens = {}; D.idf = {};
    var df = {}, n = Math.max(1, D.reg.tools.length);
    D.reg.tools.forEach(function (t) {
      var modeText = Object.keys(t.modes).map(function (k) { return t.modes[k].label; }).join(' ');
      var toks = new Set(tokens([t.name, t.keywords || '', modeText, t.category].join(' ')));
      D.docs[t.id] = toks; D.nameTokens[t.id] = new Set(tokens(t.name));
      toks.forEach(function (w) { df[w] = (df[w] || 0) + 1; });
    });
    Object.keys(df).forEach(function (w) { D.idf[w] = Math.log(1 + n / df[w]); });
  }
  function idf(w) { return Object.prototype.hasOwnProperty.call(D.idf, w) ? D.idf[w] : 1.0; }
  function isNum(w) { return /^[-+]?\d+(\.\d+)?$/.test(w); }
  function round3(x) { return Math.round(x * 1000) / 1000; }
  function shortlist(question, n) {
    var qt = tokens(question).filter(function (w) { return !isNum(w); }), sq = squash(question), out = [];
    D.reg.tools.forEach(function (t) {
      var toks = D.docs[t.id], s = 0;
      qt.forEach(function (w) {
        if (toks.has(w)) { s += idf(w) * (D.nameTokens[t.id].has(w) ? 1.6 : 1.0); }
        else if (w.length >= 4) {
          var hit = false; toks.forEach(function (d) { if (d.length >= 4 && d.indexOf(w.slice(0, 4)) === 0) { hit = true; } });
          if (hit) { s += 0.5 * idf(w); }
        }
      });
      (t.keywords || '').toLowerCase().split(/\s+/).forEach(function (kw) { if (kw.indexOf('=') !== -1 && sq.indexOf(kw) !== -1) { s += 4; } });
      if (s > 0) { out.push([t.id, round3(s)]); }
    });
    out.sort(function (a, b) { return b[1] - a[1]; });
    return out.slice(0, n);
  }
  function targetWords(question) {
    var t = normalise(question);
    var m = /(?:find|calculate|compute|determine|what is|what's|get)\s+(?:the\s+)?([a-z ]{2,25}?)(?:\s+(?:of|if|when|given|for|from|with|where|using)\b|[,.?]|$)/.exec(t);
    return new Set(m ? tokens(m[1]) : []);
  }
  function route(question) {
    var sl = shortlist(question, 4);
    if (!sl.length) { return { route: null, confidence: 0, shortlist: [], reason: 'no_match' }; }
    var top = sl[0][1], target = targetWords(question), best = null;
    sl.forEach(function (pair) {
      var tid = pair[0], ts = pair[1], tool = D.tools[tid];
      if (tid === 'centre-of-mass-calculator') { return; }
      Object.keys(tool.modes).forEach(function (mk) {
        var fields = tool.modes[mk].fields, a = assignQuantities(question, tool, fields), inputs = a.inputs;
        var hasText = fields.some(function (f) { return f.type === 'text'; });
        var formula = hasText ? extractFormula(question) : null;
        if (formula) { fields.forEach(function (f) { if (f.type === 'text') { inputs[f.id] = formula; } }); }
        var r;
        try { r = validateRoute(tid, mk, inputs, a.selects); } catch (e) { return; }
        var nIn = Object.keys(r.inputs).length, coverage = nIn / Math.max(1, fields.length), bonus = 0;
        var labelToks = new Set(tokens(r.mode_label));
        if (target.size) { target.forEach(function (w) { if (labelToks.has(w)) { bonus = 2; } }); }
        var score = ts / Math.max(top, 1e-9) + 2 * coverage + bonus;
        if (!nIn) { score -= 1; }
        if (best === null || score > best.score) { best = { score: score, r: r }; }
      });
    });
    if (!best) { return { route: null, confidence: 0.1, shortlist: sl, reason: 'no_route' }; }
    var r = best.r, second = sl.length > 1 ? sl[1][1] : 0;
    var toolClear = top >= 2.0 && (second === 0 || top >= 1.25 * second);
    var picked = 0; sl.forEach(function (p) { if (p[0] === r.tool_id) { picked = p[1]; } });
    if (r.tool_id !== sl[0][0]) { toolClear = toolClear && picked >= 0.8 * top; }
    var nNumbers = extractQuantities(question).length, tool2 = D.tools[r.tool_id];
    var fieldsNow = tool2.modes[r.mode].fields;
    var nAssigned = Object.keys(r.inputs).filter(function (k) { var ff = fieldsNow.filter(function (f) { return f.id === k; })[0]; return !(ff && ff.type === 'text'); }).length;
    var allUsed = nNumbers > 0 && nAssigned >= nNumbers, inTop2 = sl.slice(0, 2).some(function (p) { return p[0] === r.tool_id; });
    var nIn2 = Object.keys(r.inputs).length, conf;
    if (!nIn2) { conf = toolClear ? 0.35 : 0.2; }
    else if (!r.missing.length && toolClear) { conf = 0.9; }
    else if (!r.missing.length) { conf = 0.65; }
    else { conf = toolClear ? 0.5 : 0.3; }
    if (!r.missing.length && allUsed && inTop2) { conf = Math.max(conf, 0.8); }
    return { route: r, confidence: conf, shortlist: sl, reason: 'rules' };
  }
  function findFormulas(query, k) {
    k = k || 6;
    var qt = tokens(query).filter(function (w) { return !isNum(w); });
    if (!qt.length) { return []; }
    var results = [];
    D.reg.tools.forEach(function (tool) {
      var base = new Set(tokens(tool.name + ' ' + (tool.keywords || ''))), ftoks = new Set(tokens(tool.formula || ''));
      Object.keys(tool.modes).forEach(function (mk) {
        var m = tool.modes[mk], mt = new Set(tokens(m.label)), s = 0;
        qt.forEach(function (w) {
          if (mt.has(w)) { s += 3; }
          if (base.has(w)) { s += 1.5 * idf(w); }
          if (ftoks.has(w)) { s += 0.7; }
        });
        if (s > 0) {
          var ch = chapterFor(tool);
          results.push([s, { tool_id: tool.id, tool_name: tool.name, mode: mk, mode_label: m.label, formula: (tool.formula || '').slice(0, 240), url: tool.url,
                              chapter: ch ? { url: ch.url, title: ch.title } : null }]);
        }
      });
    });
    results.sort(function (a, b) { return b[0] - a[0]; });
    var seen = {}, out = [];
    for (var i = 0; i < results.length && out.length < k; i++) {
      var r = results[i][1], key = r.tool_id + '|' + r.formula.slice(0, 40);
      if (seen[key]) { continue; }
      seen[key] = true; r.score = Math.round(results[i][0] * 100) / 100; out.push(r);
    }
    return out;
  }
  function chapterFor(tool) {
    if (!tool.chapter) { return null; }
    return (D.reg.chapters || []).filter(function (c) { return c.url === tool.chapter; })[0] || null;
  }
  function related(tool) {
    var byUrl = {}; D.reg.tools.forEach(function (t) { byUrl[t.url] = t; });
    return (tool.related || []).filter(function (u) { return byUrl[u]; }).map(function (u) { return byUrl[u]; });
  }

  // ---------------------------------------------------------------- templates (port of fallback.py)
  function tr(lang, key, vars) {
    var s = D.strings[lang] || D.strings.en, text = s[key] !== undefined ? s[key] : (D.strings.en[key] !== undefined ? D.strings.en[key] : key);
    if (vars) { Object.keys(vars).forEach(function (k) { text = text.split('{' + k + '}').join(String(vars[k])); }); }
    return text;
  }
  var HEADER_RE = /^[\u2713\u2714\u2611\s]*(calculation (result|successful)|result|answer|magnification)\b/i;
  function parseResult(text) {
    var lines = String(text || '').replace(/\r/g, '').split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    lines = lines.filter(function (l) { return !HEADER_RE.test(l) || /\d/.test(l); });
    var headline = ''; for (var i = 0; i < lines.length; i++) { if (/\d/.test(lines[i]) && lines[i].toLowerCase().indexOf('formula') !== 0) { headline = lines[i]; break; } }
    var formula = '';
    for (var j = 0; j < lines.length; j++) { if (lines[j].toLowerCase().indexOf('formula') === 0) { formula = lines[j].split(':').slice(1).join(':').trim() || lines[j].trim(); break; } }
    if (!formula) { for (var k = 0; k < lines.length; k++) { if (lines[k].indexOf('=') !== -1 && /[A-Za-z\u03b1-\u03c9]/.test(lines[k])) { formula = lines[k]; break; } } }
    var working = lines.filter(function (l) { return l !== headline && l.toLowerCase().indexOf('formula') !== 0; });
    return { headline: headline, formula: formula, working: working };
  }
  function pairsText(inputs) { return inputs.length ? inputs.map(function (i) { return i.label + ' = ' + i.value; }).join('; ') : '—'; }
  function explain(lang, toolName, modeLabel, registryFormula, inputs, resultText) {
    var p = parseResult(resultText), formula = p.formula || registryFormula, parts = [tr(lang, 't.about', { tool: toolName, mode: modeLabel || toolName })];
    if (formula) { parts.push(tr(lang, 't.formula', { formula: formula })); }
    parts.push(tr(lang, 't.entered', { pairs: pairsText(inputs) }));
    if (p.headline) { parts.push(tr(lang, 't.result', { result: p.headline })); }
    parts.push(tr(lang, 't.tip'));
    return parts.join('\n');
  }
  function steps(lang, resultText) {
    var p = parseResult(resultText), work = p.working.slice(0, 8);
    if (!work.length && p.formula) { work = [p.formula]; }
    if (!work.length) { return tr(lang, 't.steps_none'); }
    return tr(lang, 't.steps_intro') + '\n' + work.map(function (w, i) { return (i + 1) + '. ' + w; }).join('\n');
  }

  root.MagicEngine = {
    init: init, normalise: normalise, tokens: tokens, route: route, shortlist: shortlist, findFormulas: findFormulas,
    validateRoute: validateRoute, explain: explain, steps: steps, tr: tr, parseResult: parseResult,
    chapterFor: chapterFor, related: related, tool: function (id) { return D.tools[id]; },
    tools: function () { return D.reg.tools; }, fieldsOf: function (tool, mode) { return tool.modes[mode].fields; }
  };
})(typeof window !== 'undefined' ? window : globalThis);
