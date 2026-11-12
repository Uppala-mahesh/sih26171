#!/usr/bin/env node
/**
 * Run a Python module with the project virtualenv when one exists.
 * Keeps `npm run ...` working on machines where `python` is not on PATH.
 */
import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const candidates = process.platform === 'win32'
  ? [join(root, '.venv', 'Scripts', 'python.exe'), join(root, 'venv', 'Scripts', 'python.exe')]
  : [join(root, '.venv', 'bin', 'python'), join(root, 'venv', 'bin', 'python')]

const python = candidates.find(existsSync) || process.env.PYTHON || 'python'
const result = spawnSync(python, process.argv.slice(2), { stdio: 'inherit', windowsHide: true })

if (result.error) {
  console.error(`[drishti] Could not start Python (${python}).`)
  console.error('[drishti] Create the local environment first:')
  console.error('  py -3.11 -m venv .venv')
  console.error('  .\\.venv\\Scripts\\python.exe -m pip install -r server/requirements.txt')
  process.exit(1)
}

process.exit(result.status ?? 1)
