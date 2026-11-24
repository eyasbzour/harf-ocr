// The app's icon: the word حرف in Amiri on ink blue, as on the website. Renders icon.html to web/icon.png (the app's
// favicon and header mark, and what desktop/make_icon.py turns into docscan.ico) and docs/favicon.png (the website).
// Needs the browser checks' packages and Chrome: cd tests/browser && npm ci, then node ../../tools/icon/render.js
const { chromium } = require('../../tests/browser/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..', '..');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
  const p = await b.newPage({ viewport: { width: 512, height: 512 } });
  await p.goto('file:///' + path.join(__dirname, 'icon.html').replace(/\\/g, '/'));
  await p.waitForLoadState('networkidle');
  await p.evaluate(() => document.fonts.load('700 228px Amiri', 'حرف'));
  await p.waitForTimeout(500);
  const out = path.join(root, 'web', 'icon.png');
  await p.locator('.icon').screenshot({ path: out, omitBackground: true });
  fs.copyFileSync(out, path.join(root, 'docs', 'favicon.png'));
  await b.close();
  console.log('wrote web/icon.png and docs/favicon.png');
})();
