// The interface language. The text in the code is Arabic, and it is also the key: tx('حذف الصفحة {page}؟', { page: 3 })
// looks it up in the chosen language and falls back to the Arabic.
//
// A language is one file, web/i18n/<code>.js: I18N.add('<code>', { name, dir }, { key: text, ... }). The server
// serves them all as /i18n/all.js (server/main.py), so a new file is all a new language needs. An entry can be
// { one, other } for plurals (Intl.PluralRules, by vars.n), with zero where it reads better than "0 ...".
// web/i18n/ar.js holds only Arabic's own plural forms. web/js/i18n.test.js checks every language has every key.
//
// Loaded in <head>, like theme.js; the language files right after it set the page's lang and dir before it is drawn.
// I18N.apply() translates the static page once, so changing the language reloads the page.
(function (root) {
  var dicts = {}, metas = {};
  var SOURCE = 'ar';  // the language the code is written in
  function stored() {
    try { return localStorage.getItem('ds.lang'); } catch (e) { return null; }  // storage blocked
  }
  // ds.lang when chosen; else the default the server gives (/js/lang-default.js: the Windows program's installer)
  var wanted = stored() || root.HARF_LANG_DEFAULT || SOURCE;
  function current() { return metas[wanted] ? wanted : SOURCE; }

  var rules = {};
  function plural(n) {
    var l = current();
    try { return (rules[l] = rules[l] || new Intl.PluralRules(l)).select(n); } catch (e) { return n === 1 ? 'one' : 'other'; }
  }
  var norm = function (s) { return String(s).replace(/\s+/g, ' ').trim(); };
  // {name} -> its value; a value that is itself a server message ({ key, args }) is put in the language too
  function fill(s, vars) {
    return vars ? s.replace(/\{(\w+)\}/g, function (m, k) {
      if (!(k in vars)) return m;
      var x = vars[k];
      return x && typeof x === 'object' && x.key ? t(x.key, x.args) : x;
    }) : s;
  }
  function t(text, vars) {
    var d = dicts[current()];
    var v = d ? d[text] : null;
    // an explicit zero form ("No pages") where the language has none of its own (English 0 is "other")
    if (v && typeof v === 'object') v = (vars && vars.n === 0 && v.zero) || v[plural(vars && vars.n)] || v.other;
    return fill(typeof v === 'string' ? v : String(text), vars);
  }
  // the message in a server reply, { error, key, args } (server/messages.py): its key in the chosen language, else its
  // text; also a plain text the server sent
  function message(data) {
    if (!data) return '';
    if (typeof data === 'string') return t(data);
    if (data.key) return t(data.key, data.args);
    var m = data.error || data.detail;
    return typeof m === 'string' ? t(m) : '';
  }

  // the static page, once: text, and the attributes people read; translate="no" (language names) stays as written
  var ATTRS = ['title', 'aria-label', 'placeholder', 'alt', 'data-short'];
  function apply(node) {
    var d = dicts[current()];
    if (!d || current() === SOURCE) return;  // the page is written in it
    var walk = node.ownerDocument.createTreeWalker(node, 4 /* text */), n, k;
    while ((n = walk.nextNode())) {
      if (/^(SCRIPT|STYLE)$/.test(n.parentNode.nodeName) || n.parentNode.closest('[translate="no"]')) continue;
      k = norm(n.nodeValue);
      if (k && typeof d[k] === 'string') n.nodeValue = n.nodeValue.replace(/\S[\s\S]*\S|\S/, d[k]);
    }
    var els = node.querySelectorAll('[' + ATTRS.join('],[') + ']');
    for (var i = 0; i < els.length; i++) {
      if (els[i].closest('[translate="no"]')) continue;
      for (var j = 0; j < ATTRS.length; j++) {
        var a = els[i].getAttribute(ATTRS[j]);
        if (a && typeof d[norm(a)] === 'string') els[i].setAttribute(ATTRS[j], d[norm(a)]);
      }
    }
  }

  var I18N = {
    t: t, message: message, apply: apply, plural: plural, norm: norm,
    lang: current,
    dir: function () { return (metas[current()] || { dir: 'rtl' }).dir; },
    // { code, name, dir } for each language, the source first: names in their own language
    languages: function () {
      return Object.keys(metas).sort(function (a, b) { return (a !== SOURCE) - (b !== SOURCE) || (a < b ? -1 : 1); })
        .map(function (c) { return { code: c, name: metas[c].name, dir: metas[c].dir }; });
    },
    add: function (code, meta, entries) {
      metas[code] = meta;
      dicts[code] = entries;
      if (code === current() && root.document) {
        root.document.documentElement.lang = code;
        root.document.documentElement.dir = meta.dir;
      }
    },
    dict: function (code) { return dicts[code]; },
    // saves the choice; the caller reloads the page (after saving the open draft)
    set: function (code) {
      try { if (metas[code]) localStorage.setItem('ds.lang', code); else localStorage.removeItem('ds.lang'); } catch (e) { /* blocked */ }
    }
  };
  root.I18N = I18N;
  root.tx = t;  // "tx", not "t": many functions here have a local t
})(typeof window !== 'undefined' ? window : globalThis);
