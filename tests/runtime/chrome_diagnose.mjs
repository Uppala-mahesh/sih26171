/**
 * Run the extension in a real browser and read its real console.
 *
 * ── Why Edge, not Chrome ─────────────────────────────────────────────────────
 * Branded Google Chrome 154 removed the flag outright:
 *
 *   --load-extension is not allowed in Google Chrome, ignoring.
 *
 * Edge is the same engine and still honours it, so this drives Edge. Both answer
 * an MV3 service worker identically; only the packaging differs.
 *
 * ── Why this file exists ─────────────────────────────────────────────────────
 * Six rounds of "still errors" produced six rounds of code changes made WITHOUT
 * EVER SEEING THE FAILURE. Every hypothesis was unverifiable, because the only
 * way to see it was to ask a human to transcribe a console. A person replying
 * "still errors" six times is telling you the loop is broken; it is not a request
 * for a seventh guess.
 *
 * Usage:  node tests/runtime/chrome_diagnose.mjs
 */

import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..');
const EXT = path.join(ROOT, 'dist-extension');
const PORT = 9333;

const BROWSER = [
  path.join(process.env['PROGRAMFILES(X86)'] ?? 'C:\\Program Files (x86)', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
  path.join(process.env['PROGRAMFILES'] ?? 'C:\\Program Files', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
].find((p) => p && fs.existsSync(p));

if (!BROWSER) { console.error('no Edge found; Chrome no longer supports --load-extension'); process.exit(2); }
if (!fs.existsSync(path.join(EXT, 'manifest.json'))) {
  console.error(`extension not built at ${EXT}; run: node infra/build-extension.cjs`);
  process.exit(2);
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'sih-edge-'));
const page = path.join(profile, 'test-page.html');
fs.writeFileSync(
  page,
  `<!doctype html><html><head><title>SIH Test</title></head><body>
   <h1>Application form</h1>
   <p>Aadhaar 1234 5678 9012</p>
   <p>Call me on +91 98765 43210</p>
   <p>Ordinary prose with nothing sensitive.</p>
   </body></html>`,
);

const chrome = spawn(
  BROWSER,
  [
    '--headless=new',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    `--load-extension=${EXT}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    page,
  ],
  { stdio: ['ignore', 'pipe', 'pipe'] },
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const targets = async () => (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();

function cleanup(code) {
  try { execFileSync('taskkill', ['/F', '/T', '/PID', String(chrome.pid)], { stdio: 'ignore' }); } catch {}
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
  process.exit(code);
}

// A diagnostic that hangs is worse than one that fails loudly.
const watchdog = setTimeout(() => { console.error('\nwatchdog: timed out'); cleanup(3); }, 45_000);
watchdog.unref();

async function waitForBrowser() {
  for (let i = 0; i < 60; i += 1) {
    try { await fetch(`http://127.0.0.1:${PORT}/json/version`); return true; } catch { await sleep(250); }
  }
  return false;
}

if (!(await waitForBrowser())) { console.error('browser never opened a debugging port'); cleanup(2); }

let worker = null;
for (let i = 0; i < 40 && !worker; i += 1) {
  worker = (await targets()).find((t) => t.type === 'service_worker' && /background\/service-worker\.js$/.test(t.url));
  if (!worker) await sleep(250);
}

if (!worker) {
  console.log('no target for background/service-worker.js');
  console.log('observed:', (await targets()).map((t) => `${t.type} ${t.url}`));
  cleanup(4);
}
console.log(`worker: ${worker.url}\n`);
const seen = [];
const ws = new WebSocket(worker.webSocketDebuggerUrl);
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);
  if (msg.method === 'Runtime.consoleAPICalled') {
    seen.push(`[${msg.params.type}] ` + (msg.params.args ?? [])
      .map((a) => a.value ?? a.description ?? a.unserializableValue ?? '')
      .join(' '));
  }
  if (msg.method === 'Runtime.exceptionThrown') {
    const d = msg.params.exceptionDetails;
    seen.push(`[EXCEPTION] ${d.text} ${d.exception?.description ?? ''}`);
  }
  if (msg.method === 'Log.entryAdded') {
    const e = msg.params.entry;
    if (e.level === 'error' || e.level === 'warning') seen.push(`[${e.level}] ${e.text}`);
  }
});
await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
ws.send(JSON.stringify({ id: 1, method: 'Runtime.enable' }));
ws.send(JSON.stringify({ id: 2, method: 'Log.enable' }));
// A newly-attached service worker context is PAUSED waiting for a debugger.
// Without this, every evaluation lands in a context where `chrome` has not been
// installed yet, which looks exactly like "the API is missing" and is not.
ws.send(JSON.stringify({ id: 3, method: 'Runtime.runIfWaitingForDebugger' }));
await sleep(500);

let seq = 100;
function probe(expression) {
  const id = seq++;
  return new Promise((resolve) => {
    const onMessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id !== id) return;
      ws.removeEventListener('message', onMessage);
      if (msg.result?.exceptionDetails) {
        resolve('THREW: ' + (msg.result.exceptionDetails.exception?.description ?? msg.result.exceptionDetails.text));
      } else {
        resolve(msg.result?.result?.value ?? String(msg.result?.result?.description ?? null));
      }
    };
    ws.addEventListener('message', onMessage);
    ws.send(JSON.stringify({
      id, method: 'Runtime.evaluate',
      params: { expression, awaitPromise: true, returnByValue: true },
    }));
  });
}

// THE CALL THAT HAS BEEN FAILING, executed for real against a real page.
console.log('--- the failing call, run for real ---');
console.log('tabs        :', await probe(`(async()=>{const t=await chrome.tabs.query({});
  return t.map(x=>x.id+' '+String(x.url).slice(0,55)).join(' | ')||'NONE';})()`));
console.log('sendMessage :', await probe(`(async()=>{
  const t=(await chrome.tabs.query({})).find(x=>String(x.url).includes('test-page'));
  if(!t) return 'no test tab';
  try { const r = await chrome.tabs.sendMessage(t.id,{kind:'COLLECT'});
        return 'OK, segments=' + (r && r.segments ? r.segments.length : 'null'); }
  catch(e){ return 'THREW: ' + e.message; }
})()`));

await sleep(600);
console.log('badge api   :', await probe(`(async()=>{
  try { await chrome.action.setBadgeText({text:'OK'});
        await chrome.action.setTitle({title:'probe'});
        return 'setBadgeText + setTitle OK'; }
  catch(e){ return 'THREW: ' + e.message; }
})()`));

// The boundary the user is most likely on. A chrome:// page cannot host a content
// script for ANY extension, so this must fail - and must fail cleanly.
console.log('chrome://   :', await probe(`(async()=>{
  const t = await chrome.tabs.create({url:'chrome://extensions/'});
  await new Promise(r=>setTimeout(r,800));
  try { const r = await chrome.tabs.sendMessage(t.id,{kind:'COLLECT'});
        return 'OK segments=' + (r&&r.segments?r.segments.length:'null'); }
  catch(e){ return 'THREW: ' + e.message; }
})()`));

console.log('\n--- worker console ---');
if (seen.length === 0) console.log('(nothing logged)');
for (const line of seen) console.log(line);

cleanup(seen.some((l) => l.includes('EXCEPTION')) ? 1 : 0);