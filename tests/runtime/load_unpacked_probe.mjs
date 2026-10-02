/**
 * Reproduce the user's EXACT action and capture Chrome's real error.
 *
 * "Load unpacked" is not a browser internal: it calls
 * `chrome.developerPrivate.loadUnpacked(...)` from the chrome://extensions page.
 * That API is reachable over the DevTools Protocol, so the failing load can be
 * triggered here and the ERROR STRING read back, instead of being guessed at
 * from documentation that does not settle the question.
 *
 * Chrome 154 refuses --load-extension, which is why previous rounds drove Edge.
 * This runs real Chrome because the failure is in real Chrome's loader.
 *
 * ── The hard limit, established rather than assumed ──────────────────────────
 * Three routes to loading an unpacked extension were attempted from here:
 *
 *   1. --load-extension            -> "not allowed in Google Chrome, ignoring."
 *   2. seeding extensions.settings -> silently discarded; extensions live in
 *                                     HMAC-signed Secure Preferences.
 *   3. developerPrivate.loadDirectory(DirectoryEntry, cb)
 *                                  -> "Value must be an instance of
 *                                     DirectoryEntry", which can only come from
 *                                     a real file picker or a drop.
 *
 * So the install step needs one human click on an OS file dialog. Everything
 * reachable from here is verified automatically instead; this script exists so
 * that boundary is documented rather than rediscovered next time.
 *
 * Usage:  node tests/runtime/load_unpacked_probe.mjs
 */

import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..');
const EXT = path.join(ROOT, 'dist-extension');
const PORT = 9334;

const CHROME = [
  path.join(process.env['PROGRAMFILES'] ?? 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)'] ?? 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
].find((p) => p && fs.existsSync(p));

if (!CHROME) { console.error('no chrome'); process.exit(2); }
if (!fs.existsSync(path.join(EXT, 'manifest.json'))) {
  console.error(`not built at ${EXT}; run: node infra/build-extension.cjs`);
  process.exit(2);
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'sih-load-'));
const browser = spawn(
  CHROME,
  [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    'about:blank',
  ],
  { stdio: ['ignore', 'pipe', 'pipe'] },
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const targets = async () => (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();

function cleanup(code) {
  try { execFileSync('taskkill', ['/F', '/T', '/PID', String(browser.pid)], { stdio: 'ignore' }); } catch {}
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
  process.exit(code);
}
const watchdog = setTimeout(() => { console.error('\nwatchdog: timed out'); cleanup(3); }, 45_000);
watchdog.unref();

for (let i = 0; i < 60; i += 1) {
  try { await fetch(`http://127.0.0.1:${PORT}/json/version`); break; } catch { await sleep(250); }
}

// WebUI targets are not always listed, so ASK for one to be created.
// (Newer Chrome requires PUT on /json/new.)
let page = null;
for (let i = 0; i < 20 && !page; i += 1) {
  try {
    await fetch(`http://127.0.0.1:${PORT}/json/new?chrome://extensions`, { method: 'PUT' });
  } catch { /* older Chrome wants POST */ 
    try { await fetch(`http://127.0.0.1:${PORT}/json/new?chrome://extensions`); } catch {}
  }
  await sleep(500);
  page = (await targets()).find((t) => t.type === 'page' && /extensions/.test(t.url));
  if (!page) await sleep(500);
}
if (!page) {
  console.log('could not open chrome://extensions');
  console.log('targets seen:', (await targets()).map((t) => `${t.type} ${t.url}`));
  cleanup(4);
}

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
ws.send(JSON.stringify({ id: 1, method: 'Runtime.enable' }));
ws.send(JSON.stringify({ id: 2, method: 'Runtime.runIfWaitingForDebugger' }));
await sleep(800);

let seq = 10;
function probe(expression) {
  const id = seq++;
  return new Promise((resolve) => {
    const onMessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id !== id) return;
      ws.removeEventListener('message', onMessage);
      if (msg.result?.exceptionDetails) {
        resolve('THREW: ' + (msg.result.exceptionDetails.exception?.description ?? msg.result.exceptionDetails.text));
      } else resolve(msg.result?.result?.value ?? String(msg.result?.result?.description ?? null));
    };
    ws.addEventListener('message', onMessage);
    ws.send(JSON.stringify({ id, method: 'Runtime.evaluate', params: { expression, awaitPromise: true, returnByValue: true } }));
  });
}

console.log('developerPrivate present :', await probe('typeof chrome.developerPrivate'));

// Enumerate the real API surface instead of guessing method and property names.
console.log('\ndeveloperPrivate API:');
console.log(await probe(`Object.keys(chrome.developerPrivate).sort().join('  ')`));

console.log('\nload* methods:');
console.log(await probe(
  `Object.keys(chrome.developerPrivate).filter(k=>/load/i.test(k)).sort()
     .map(k=>k+'('+(chrome.developerPrivate[k].length)+' args)').join('  ') || 'none'`,
));

console.log('enable dev mode           :', await probe(`(async () => {
  await chrome.developerPrivate.updateProfileConfiguration({ inDeveloperMode: true });
  const c = await chrome.developerPrivate.getProfileConfiguration();
  return 'inDeveloperMode=' + c.inDeveloperMode;
})()`));

console.log('schema probe              :', await probe(`(async () => {
  // Now that developer mode is on, an empty options object should fail on the
  // MISSING required property - which names the schema instead of guessing it.
  try { await chrome.developerPrivate.loadUnpacked({}); return 'accepted empty?!'; }
  catch (e) { return 'with {} -> ' + e.message; }
})()`));

console.log('loadUnpacked              :', await probe(`(async () => {
  try {
    await chrome.developerPrivate.loadUnpacked({ filepath: ${JSON.stringify(EXT)} });
    return 'LOADED OK';
  } catch (e) {
    return 'FAILED: ' + (e && e.message ? e.message : String(e));
  }
})()`));

console.log('\n--- trying every loadDirectory calling convention ---');
for (const expr of [
  `chrome.developerPrivate.loadDirectory(${JSON.stringify(EXT)})`,
  `chrome.developerPrivate.loadDirectory({ path: ${JSON.stringify(EXT)} })`,
  `chrome.developerPrivate.loadDirectory({ filepath: ${JSON.stringify(EXT)} })`,
  `chrome.developerPrivate.loadDirectory(undefined, ${JSON.stringify(EXT)})`,
]) {
  console.log('\n  ' + expr.slice(0, 70));
  console.log('   ->', await probe(`(async () => {
    try { const r = await chrome.developerPrivate.loadDirectory(${
      expr.slice('chrome.developerPrivate.loadDirectory'.length)
    }); return 'OK: ' + JSON.stringify(r); }
    catch (e) { return 'FAILED: ' + (e && e.message ? e.message : String(e)); }
  })()`));
}

console.log('\n--- installed extensions now ---');
console.log(await probe(`(async () => {
  const info = await chrome.developerPrivate.getExtensionsInfo();
  return JSON.stringify(info.filter(e => e.name && /SIH/i.test(e.name)).map(e => ({
    name: e.name, state: e.state, disableReasons: e.disableReasons,
    manifestErrors: e.manifestErrors,
    runtimeErrors: (e.runtimeErrors || []).map(r => r.message),
  })), null, 1);
})()`));

cleanup(0);