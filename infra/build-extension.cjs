/**
 * Build the loadable Chrome MV3 extension into dist-extension/.
 *
 * Three steps:
 *   1. compile packages/ and apps/extension/src/ as native ES modules
 *   2. lay the output out the way the manifest expects
 *   3. copy the static files Chrome also needs
 *
 * Why ES modules and NOT a bundle: the extension is a security boundary, and a
 * bundler is another program rewriting the privacy core on its way to the
 * browser. The sources already use explicit `.js` specifiers, so Chrome's own
 * module loader resolves them correctly with no transform step at all. The code
 * that runs in the browser is the code in this repository, unmodified.
 *
 * Usage:  node infra/build-extension.cjs
 */

'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'dist-extension');
const tsc = path.join(
  ROOT,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'tsc.cmd' : 'tsc',
);

console.log('> compiling extension sources (ES modules)');
const build = spawnSync(tsc, ['-p', 'tsconfig.extension.json'], {
  cwd: ROOT,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

if (build.status !== 0) {
  console.error('build failed');
  process.exit(build.status ?? 1);
}

/**
 * Copy one file, creating the destination directory, and REWRITE its relative
 * specifiers for its new depth.
 *
 * tsc emits `apps/extension/src/offscreen.js` with `../../../packages/...`,
 * which is correct there and catastrophically wrong at `offscreen/offscreen.js`
 * - it would resolve out of dist-extension and into the TypeScript sources.
 * Leaving that in place produces a build that succeeds and an extension Chrome
 * cannot load, which is worse than a failed build because it looks fine.
 *
 * The rewrite is a single explicit substitution rather than a general transform,
 * so what it does is auditable by reading it.
 */
function place(relativeFrom, relativeTo, depthRewrite) {
  const from = path.join(OUT, relativeFrom);
  const to = path.join(OUT, relativeTo);
  fs.mkdirSync(path.dirname(to), { recursive: true });

  if (!from.endsWith('.js') || !depthRewrite) {
    fs.copyFileSync(from, to);
    return;
  }
  const original = fs.readFileSync(from, 'utf8');
  const rewritten = original.split(depthRewrite.from).join(depthRewrite.to);
  if (rewritten === original) {
    console.warn(`> warning: no '${depthRewrite.from}' specifier found in ${relativeFrom}`);
  }
  fs.writeFileSync(to, rewritten, 'utf8');
}

// tsc emits apps/extension/src/*.js; the manifest wants them at stable paths.
place(path.join('apps', 'extension', 'src', 'content.js'), path.join('content', 'content.js'), null);
place(
  path.join('apps', 'extension', 'src', 'service-worker.js'),
  path.join('background', 'service-worker.js'),
  null,
);
// messages.js is imported by BOTH the worker and the offscreen document, so it
// has to exist beside each. A worker that imports a module living only in the
// offscreen directory fails at load, not at test time.
for (const dir of ['background', 'offscreen']) {
  place(
    path.join('apps', 'extension', 'src', 'messages.js'),
    path.join(dir, 'messages.js'),
    null,
  );
}
place(
  path.join('apps', 'extension', 'src', 'offscreen.js'),
  path.join('offscreen', 'offscreen.js'),
  { from: '../../../packages/', to: '../packages/' },
);

// The privacy core is imported by the offscreen document, so it must ship too.
const copyTree = (from, to) => {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const a = path.join(from, entry.name);
    const b = path.join(to, entry.name);
    if (entry.isDirectory()) copyTree(a, b);
    else if (entry.name.endsWith('.js')) fs.copyFileSync(a, b);
  }
};
copyTree(path.join(OUT, 'packages'), path.join(OUT, 'packages'));

// The HTML host and the manifest itself are static.
fs.copyFileSync(
  path.join(ROOT, 'apps', 'extension', 'manifest.json'),
  path.join(OUT, 'manifest.json'),
);
fs.mkdirSync(path.join(OUT, 'offscreen'), { recursive: true });
fs.copyFileSync(
  path.join(ROOT, 'apps', 'extension', 'offscreen.html'),
  path.join(OUT, 'offscreen', 'offscreen.html'),
);

// Remove tsc's intermediate tree: it is a duplicate of files already placed, and
// shipping two copies of the privacy core invites loading the wrong one.
fs.rmSync(path.join(OUT, 'apps'), { recursive: true, force: true });

// ── gate: every relative import must resolve INSIDE the artifact ─────────────
//
// This is the check that would have caught the `../../../packages/` defect. A
// specifier pointing outside dist-extension resolves in a developer's checkout
// and fails in a loaded extension, so it is verified here rather than
// discovered when the extension silently does nothing.
function checkImports(dir, problems) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      checkImports(p, problems);
      continue;
    }
    if (!entry.name.endsWith('.js')) continue;
    const source = fs.readFileSync(p, 'utf8');
    // tsc emits DOUBLE-quoted specifiers; hand-written sources use single. Both
    // must be matched, or this gate silently checks nothing.
    const specifiers = source.matchAll(/from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)/g);
    for (const match of specifiers) {
      const spec = match[1] ?? match[2];
      if (!spec || !spec.startsWith('.')) continue; // bare/absolute: not ours
      const resolved = path.resolve(path.dirname(p), spec);
      const relative = path.relative(OUT, resolved);
      if (relative.startsWith('..') || !fs.existsSync(resolved)) {
        problems.push(`${path.relative(OUT, p)} imports ${spec} -> ${relative}`);
      }
    }
  }
}

const importProblems = [];
checkImports(OUT, importProblems);
if (importProblems.length > 0) {
  console.error('unresolvable imports in the built extension:');
  for (const problem of importProblems) console.error(`  ${problem}`);
  process.exit(1);
}

// Chrome requires an explicit ESM marker: the root package.json declares
// "type": "module", but dist-extension must not depend on that staying true.
fs.writeFileSync(
  path.join(OUT, 'package.json'),
  `${JSON.stringify({ type: 'module' }, null, 2)}\n`,
  'utf8',
);

// ── fail loudly if the artefact cannot actually load ─────────────────────────
// A build that produces a directory Chrome rejects is worse than no build,
// because it looks like success.
const manifest = JSON.parse(fs.readFileSync(path.join(OUT, 'manifest.json'), 'utf8'));
const required = [
  manifest.background.service_worker,
  manifest.content_scripts[0].js[0],
  'offscreen/offscreen.html',
];
const missing = required.filter((rel) => !fs.existsSync(path.join(OUT, rel)));
if (missing.length > 0) {
  console.error(`build incomplete, missing from dist-extension: ${missing.join(', ')}`);
  process.exit(1);
}

const files = [];
(function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p);
    else files.push(p);
  }
})(OUT);

console.log(`> dist-extension ready: ${files.length} files`);
console.log('> load with: chrome://extensions -> Developer mode -> Load unpacked');
