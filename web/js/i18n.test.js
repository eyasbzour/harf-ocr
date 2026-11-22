// Every language misses nothing: every Arabic string in the code, the static pages, the server's messages and the
// Windows program's launcher has its entry in each language file (web/i18n/<code>.js), and no entry is left over.
// node --test web/js/*.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const AR = /[؀-ۿ]/;
const CODES = fs.readdirSync(path.join(ROOT, 'web/i18n')).filter((f) => f.endsWith('.js')).map((f) => f.slice(0, -3)).sort();

// a page's I18N, with every language file loaded, as the server's /i18n/all.js does; lang: the chosen one
function load(lang) {
  const ctx = { Intl, String, Object, HARF_LANG_DEFAULT: lang };
  vm.createContext(ctx);
  vm.runInContext(read('web/js/i18n.js'), ctx);
  for (const code of CODES) vm.runInContext(read(`web/i18n/${code}.js`), ctx);
  return ctx;
}
const I18N = load().I18N;
const LANG_INFO = I18N.languages();
const norm = I18N.norm;

// ---- where the keys come from
// A small JavaScript lexer: the string and template literals of a source, past comments and regex literals.
// A template's "text" is its fixed parts only: the literals inside its ${...} are listed on their own.
const AFTER_REGEX_OK = /^(?:[(,=:[!&|?{;+\-*%<>~^]|return|typeof|case|do|else|in|of|new|delete|void|throw|yield|await)$/;
function lex(src) {
  const out = [];
  let i = 0, prev = '';
  const n = src.length;
  const add = (at, raw, text, template) => out.push({ at, raw, text, template });
  function quoted(q) {
    const s = i++;
    while (i < n && src[i] !== q) i += src[i] === '\\' ? 2 : 1;
    i++;
    return src.slice(s, i);
  }
  function template() {
    const s = i++;
    let fixed = '';
    while (i < n && src[i] !== '`') {
      if (src[i] === '\\') { fixed += src.slice(i, i + 2); i += 2; continue; }
      if (src[i] === '$' && src[i + 1] === '{') { i += 2; code('}'); i++; fixed += '${}'; continue; }
      fixed += src[i++];
    }
    i++;
    return [src.slice(s, i), fixed];
  }
  function code(stop) {
    let depth = 0;
    while (i < n) {
      const c = src[i];
      if (stop && c === '}' && depth === 0) return;
      if (c === '/' && src[i + 1] === '/') { while (i < n && src[i] !== '\n') i++; continue; }
      if (c === '/' && src[i + 1] === '*') { i = src.indexOf('*/', i + 2) + 2; continue; }
      if (c === "'" || c === '"') { const at = i, raw = quoted(c); add(at, raw, unquote(raw), false); prev = 'str'; continue; }
      if (c === '`') { const at = i, [raw, fixed] = template(); add(at, raw, fixed, true); prev = 'str'; continue; }
      if (c === '/' && (!prev || AFTER_REGEX_OK.test(prev))) {
        i++;
        for (let cls = false; i < n && src[i] !== '\n'; i++) {
          if (src[i] === '\\') { i++; continue; }
          if (src[i] === '[') cls = true; else if (src[i] === ']') cls = false; else if (src[i] === '/' && !cls) break;
        }
        i++;
        while (i < n && /[a-z]/i.test(src[i])) i++;
        prev = 're';
        continue;
      }
      if (/\s/.test(c)) { i++; continue; }
      if (/[\w$]/.test(c)) { const s = i; while (i < n && /[\w$]/.test(src[i])) i++; prev = src.slice(s, i); continue; }
      if (c === '{') depth++;
      if (c === '}') depth--;
      prev = c;
      i++;
    }
  }
  code();
  return out;
}
const unquote = (s) => s.slice(1, -1).replace(/\\(['"`\\])/g, '$1').replace(/\\n/g, '\n');

// Arabic literals in a JS source, each with what comes just before it
function arabicLiterals(file, src) {
  return lex(src).filter((l) => AR.test(l.text)).map((l) => ({ ...l, file, before: src.slice(Math.max(0, l.at - 40), l.at) }));
}
const jsLiterals = (file) => arabicLiterals(file, read(file));
const JS = fs.readdirSync(path.join(ROOT, 'web/js')).filter((f) => f.endsWith('.js') && !f.endsWith('.test.js') && f !== 'i18n.js')
  .map((f) => 'web/js/' + f);
// a literal that is a key: the first argument of tx() or I18N.t()
const KEYED = /(?:\btx|I18N\.t)\(\s*$/;
// Arabic that is not interface text: patterns and digit tables, named here one by one
const NOT_TEXT = new Set([
  'web/js/editor.js|١.', 'web/js/editor.js|٢.', 'web/js/editor.js|٣.',  // list marker samples: Hindi digits
  'web/js/editor.js|أ.', 'web/js/editor.js|ب.', 'web/js/editor.js|ت.',  // and Arabic letters
  'web/js/app.js|ا', 'web/js/app.js|ه', 'web/js/app.js|ي',  // the drafts search folds أ إ آ, ة and ى
  'web/js/docx-export.js|مراجع',  // the comment author when a caller gives none; app.js always gives one
]);

function htmlKeys(file) {
  const src = read(file).replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, '')
    .replace(/<(\w+)\b[^>]*\btranslate="no"[^>]*>[\s\S]*?<\/\1>/g, '');  // never translated: language names
  const keys = [];
  for (const m of src.matchAll(/>([^<]+)</g)) if (AR.test(m[1])) keys.push(norm(m[1]));
  for (const m of src.matchAll(/\s(?:title|aria-label|placeholder|alt|data-short)="([^"]*)"/g)) if (AR.test(m[1])) keys.push(norm(m[1]));
  return keys;
}
function pageScriptLiterals(file) {
  return [...read(file).matchAll(/<script>([\s\S]*?)<\/script>/g)].flatMap((m) => arabicLiterals(file, m[1]));
}
// the server's messages: msg("...") (server/messages.py)
function serverKeys() {
  const keys = [];
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) { if (!/tests|__pycache__/.test(e.name)) walk(p); } else if (e.name.endsWith('.py')) {
      for (const m of fs.readFileSync(p, 'utf8').matchAll(/\bmsg\(\s*(?:"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)')/g)) keys.push(m[1] ?? m[2]);
    }
  });
  walk(path.join(ROOT, 'server'));
  return keys;
}
// the Windows program's launcher: tr("...") (desktop/app.py), for what shows before the page
const launcherKeys = () => [...read('desktop/app.py').matchAll(/\btr\(\s*"((?:[^"\\\n]|\\.)*)"/g)].map((m) => m[1]);

// the built-in header templates' names (templates/*.json), shown through I18N.t()
const templateKeys = () => fs.readdirSync(path.join(ROOT, 'templates')).filter((f) => f.endsWith('.json'))
  .map((f) => JSON.parse(read('templates/' + f)).name).filter((n) => n && AR.test(n));

const literals = JS.flatMap(jsLiterals).concat(pageScriptLiterals('web/phone.html'), pageScriptLiterals('web/index.html'));
const used = new Set([
  ...literals.filter((l) => KEYED.test(l.before)).map((l) => l.text),
  ...htmlKeys('web/index.html'), ...htmlKeys('web/phone.html'),
  ...serverKeys(), ...launcherKeys(), ...templateKeys(),
]);

test('every Arabic literal in the browser code goes through tx()', () => {
  const loose = literals.filter((l) => !KEYED.test(l.before) && !NOT_TEXT.has(l.file + '|' + l.text));
  assert.deepStrictEqual(loose.map((l) => `${l.file}: ${l.raw.slice(0, 80)}`), []);
});

test('no key is built from a template literal (its values go in {braces})', () => {
  const bad = literals.filter((l) => l.template);
  assert.deepStrictEqual(bad.map((l) => `${l.file}: ${l.raw.slice(0, 80)}`), []);
});

test('each language file is I18N.add(code, { name, dir }, entries) for its own code', () => {
  for (const code of CODES) {
    const meta = LANG_INFO.find((l) => l.code === code);
    assert.ok(meta && meta.name && ['ltr', 'rtl'].includes(meta.dir), code);
  }
  assert.ok(CODES.includes('ar') && CODES.includes('en'));
});

const holes = (s) => [...new Set([...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort().join(',');
const within = (form, key) => holes(form).split(',').every((h) => !h || holes(key).split(',').includes(h));
const forms = (v) => (typeof v === 'object' ? Object.values(v) : [v]);

// every language but the source (Arabic, the code's own text) has every key, and nothing else
for (const code of CODES.filter((c) => c !== 'ar')) {
  const D = I18N.dict(code);
  const ltr = LANG_INFO.find((l) => l.code === code).dir === 'ltr';
  test(`${code}: every key has an entry`, () => {
    assert.deepStrictEqual([...used].filter((k) => !(k in D)), []);
  });
  test(`${code}: no entry is left over`, () => {
    assert.deepStrictEqual(Object.keys(D).filter((k) => !used.has(k)), []);
  });
  test(`${code}: the same {values} as the Arabic (a plural's "one" may leave out {n})`, () => {
    const bad = Object.entries(D).filter(([k, v]) => typeof v === 'object'
      ? holes(v.other) !== holes(k) || !forms(v).every((f) => within(f, k))
      : holes(v) !== holes(k)).map(([k]) => k);
    assert.deepStrictEqual(bad, []);
  });
  test(`${code}: plain text: no dashes or curly quotes${ltr ? ', no Arabic letters' : ''}`, () => {
    const bad = Object.entries(D).filter(([, v]) => forms(v).some((f) => typeof f !== 'string' || !f.trim()
      || /[–—‘’“”]/.test(f) || (ltr && AR.test(f)))).map(([k]) => k);
    assert.deepStrictEqual(bad, []);
  });
  test(`${code}: plurals have one and other`, () => {
    assert.deepStrictEqual(Object.entries(D).filter(([, v]) => typeof v === 'object' && !(v.one && v.other)).map(([k]) => k), []);
  });
}

test('Arabic plural forms (web/i18n/ar.js): used keys, an "other" form, the same {values}', () => {
  const AR_DICT = I18N.dict('ar');
  const bad = Object.entries(AR_DICT).filter(([k, v]) => !used.has(k) || typeof v !== 'object' || !v.other || !forms(v).every((f) => within(f, k)));
  assert.deepStrictEqual(bad.map(([k]) => k), []);
  const ctx = load();
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 0 }), 'بلا صفحات');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 2 }), 'صفحتان');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 7 }), '7 صفحات');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 12 }), '12 صفحة');
  assert.strictEqual(ctx.tx('{n} صفوف', { n: 1 }), '1 صف');
});

test('English zero and plural forms, and a message inside a message', () => {
  const ctx = load('en');
  assert.strictEqual(ctx.I18N.lang(), 'en');
  assert.strictEqual(ctx.I18N.dir(), 'ltr');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 0 }), 'No pages');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 1 }), '1 page');
  assert.strictEqual(ctx.tx('{n} صفحات', { n: 12 }), '12 pages');
  assert.strictEqual(ctx.I18N.message({ error: 'x', key: 'تعذر تنزيل القرّاء الإضافيين: {error}',
    args: { error: { key: 'تعذرت القراءة بـ EasyOCR: {error}', args: { error: 'boom' } } } }),
  "Couldn't download the extra readers: Couldn't read with EasyOCR: boom");
});

test('tx(): values, plurals, falling back to the Arabic, and an unknown language', () => {
  const ctx = load('xx');
  ctx.I18N.add('xx', { name: 'Test', dir: 'ltr' }, { 'صفحة {n}': { one: '{n} page', other: '{n} pages' }, 'مرحباً {name}': 'Hello {name}' });
  assert.strictEqual(ctx.tx('صفحة {n}', { n: 1 }), '1 page');
  assert.strictEqual(ctx.tx('صفحة {n}', { n: 3 }), '3 pages');
  assert.strictEqual(ctx.tx('مرحباً {name}', { name: 'Eyas' }), 'Hello Eyas');
  assert.strictEqual(ctx.tx('نص بلا ترجمة'), 'نص بلا ترجمة');
  assert.strictEqual(ctx.I18N.message({ error: 'مرحباً x', key: 'مرحباً {name}', args: { name: 'x' } }), 'Hello x');
  assert.strictEqual(ctx.I18N.message({ detail: 'غير معروف' }), 'غير معروف');
  assert.strictEqual(ctx.I18N.message('غير معروف'), 'غير معروف');
  assert.strictEqual(load('zz').I18N.lang(), 'ar');  // no such file: Arabic
  assert.strictEqual(load().tx('مرحباً {name}', { name: 'x' }), 'مرحباً x');  // Arabic unless chosen
});

test('en: spot checks that the English is the right sentence (numbers and names carry over)', () => {
  // a digit, a Latin name or a file type in the Arabic must be in its English too: catches lines put against the
  // wrong key, which the {values} check alone does not
  const D = I18N.dict('en');
  const marks = (s) => (String(s).match(/[0-9]+|[A-Za-z][A-Za-z.]*[A-Za-z]/g) || []).filter((w) => !/^(n|x)$/.test(w));
  const bad = Object.entries(D).filter(([k, v]) => {
    const want = marks(k.replace(/\{\w+\}/g, ''));
    const got = forms(v).join(' ');
    return want.some((w) => !got.includes(w));
  }).map(([k]) => k);
  assert.deepStrictEqual(bad, []);
});
