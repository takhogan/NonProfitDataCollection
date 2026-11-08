#!/usr/bin/env node
// Run every component locally with one command: `npm run start:dev`.
//
//   npm run start:dev                     # mock web client (default)
//   npm run start:dev -- --web=http       # web talks to the backend on :8000
//   npm run start:dev -- --no-seed        # skip both seed scripts
//   npm run start:dev -- --setup-only     # prepare db/venvs/migrations/seed, then exit
//
// Env equivalents: DEV_WEB_MODE=http, DEV_SKIP_SEED=1. PYTHON=/path/to/python3.x
// picks the interpreter used to create missing venvs.
//
// No npm dependencies: Node >= 24 built-ins only. Synthetic data only.
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { styleText } from 'node:util';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BACKEND = path.join(ROOT, 'components/whatsapp/api');
const DASH = path.join(ROOT, 'components/api');
const WEB = path.join(ROOT, 'components/web');

const args = new Set(process.argv.slice(2));
const flag = (name) => args.has(name);
const webModeArg = [...args].find((a) => a.startsWith('--web='));
const WEB_MODE = (webModeArg ? webModeArg.slice(6) : process.env.DEV_WEB_MODE) || 'mock';
const SKIP_SEED = flag('--no-seed') || process.env.DEV_SKIP_SEED === '1';
const SETUP_ONLY = flag('--setup-only');
if (flag('--help') || flag('-h')) {
  console.log(readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\n').slice(1, 11).join('\n'));
  process.exit(0);
}
if (!['mock', 'http'].includes(WEB_MODE)) die(`--web must be "mock" or "http", got "${WEB_MODE}"`);

const log = (msg) => console.log(styleText(['bold', 'cyan'], '[dev]'), msg);
function die(msg) {
  console.error(styleText(['bold', 'red'], '[dev] error:'), msg);
  process.exit(1);
}

// Run a setup command synchronously with inherited output; abort on failure.
function run(cmd, cmdArgs, opts = {}) {
  const cwd = opts.cwd ?? ROOT;
  const shown = path.isAbsolute(cmd) ? path.relative(cwd, cmd) : cmd;
  log(styleText('dim', `${path.relative(ROOT, cwd) || '.'}$ ${shown} ${cmdArgs.join(' ')}`));
  const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit', ...opts });
  if (r.error) die(`${cmd}: ${r.error.message}`);
  if (r.status !== 0) die(`\`${cmd} ${cmdArgs.join(' ')}\` exited with ${r.status}`);
}
const capture = (cmd, cmdArgs, opts = {}) =>
  spawnSync(cmd, cmdArgs, { encoding: 'utf8', ...opts });

// ---------------------------------------------------------------- prerequisites
function checkPrereqs() {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 24 || (major === 24 && minor < 22)) {
    die(`Node ${process.versions.node} found; components/web needs >= 24.22.0.\n` +
        `  Run \`nvm use\` (reads .nvmrc) or install Node 24, then retry.`);
  }
  const docker = capture('docker', ['info', '--format', '{{.ServerVersion}}']);
  if (docker.error) die('docker not found on PATH. Install Docker Desktop.');
  if (docker.status !== 0) die('Docker is not running. Start Docker Desktop and retry.');
  if (capture('docker', ['compose', 'version']).status !== 0) die('`docker compose` (v2) is not available.');

  const py = process.env.PYTHON || 'python3';
  const v = capture(py, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])']);
  if (v.error || v.status !== 0) die(`${py} not found. Install Python >= 3.11 or set PYTHON=/path/to/python3.x`);
  const [pmaj, pmin] = v.stdout.trim().split('.').map(Number);
  if (pmaj < 3 || (pmaj === 3 && pmin < 11)) die(`${py} is ${v.stdout.trim()}; need >= 3.11 (set PYTHON=...)`);
  return py;
}

function portInUse(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: '127.0.0.1' });
    s.once('connect', () => { s.destroy(); resolve(true); });
    s.once('error', () => resolve(false));
  });
}

// ---------------------------------------------------------------- setup steps
// Every checkout shares one Postgres server (the compose project is named after
// the folder, `api`, so all worktrees reuse the same container and volume).
// Branches can carry different migrations under the same revision id, so a git
// worktree gets its own database (csl_dev_<worktree>) instead of `csl_dev`.
function devDbName() {
  const m = ROOT.match(/[\/]\.claude[\/]worktrees[\/]([^\/]+)$/);
  if (!m) return 'csl_dev';
  return ('csl_dev_' + m[1].toLowerCase().replace(/[^a-z0-9_]/g, '_')).slice(0, 63);
}

function ensureEnvFile() {
  const env = path.join(BACKEND, '.env');
  if (existsSync(env)) return log('components/whatsapp/api/.env exists; leaving it as is');
  const db = devDbName();
  let text = readFileSync(path.join(BACKEND, '.env.postgres.example'), 'utf8');
  if (db !== 'csl_dev') {
    text = text.replace(/(DATABASE_URL=\S+\/)csl_dev\b/, `$1${db}`);
  }
  writeFileSync(env, text, { flag: 'wx' }); // wx: never overwrite
  log(`created components/whatsapp/api/.env from .env.postgres.example (database ${db})`);
}

// CREATE DATABASE for the one named in DATABASE_URL if it is missing (local
// Docker server only; PostGIS is enabled by the first migration).
function ensureDatabase(url) {
  const m = url?.match(/^postgresql(?:\+\w+)?:\/\/[^/]*@(localhost|127\.0\.0\.1):\d+\/([A-Za-z0-9_]+)$/);
  if (!m) return log(`DATABASE_URL is not a local Docker database; not creating it`);
  const name = m[2];
  const psql = (sql, db = 'postgres') =>
    capture('docker', ['compose', 'exec', '-T', 'db', 'psql', '-U', 'postgres', '-d', db, '-tAc', sql], { cwd: BACKEND });
  const exists = psql(`SELECT 1 FROM pg_database WHERE datname='${name}'`);
  if (exists.status !== 0) die(`could not query Postgres: ${exists.stderr}`);
  if (exists.stdout.trim() === '1') return log(`database ${name} exists`);
  const created = psql(`CREATE DATABASE "${name}"`);
  if (created.status !== 0) die(`CREATE DATABASE ${name} failed: ${created.stderr}`);
  log(`created database ${name}`);
}

// Minimal KEY=VALUE reader for the backend .env (no interpolation).
function readEnv(file) {
  const out = {};
  for (const line of readFileSync(file, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  return out;
}

// (Re)install when the venv is new or pyproject.toml changed since the last
// install (a stamp holds its hash), so a stale venv never misses a dependency.
function ensureVenv(dir, py) {
  const vpy = path.join(dir, '.venv/bin/python');
  const stamp = path.join(dir, '.venv/.start-dev-pyproject.sha256');
  if (!existsSync(vpy)) run(py, ['-m', 'venv', '.venv'], { cwd: dir });
  const hash = createHash('sha256').update(readFileSync(path.join(dir, 'pyproject.toml'))).digest('hex');
  if (existsSync(stamp) && readFileSync(stamp, 'utf8').trim() === hash) {
    return log(`${path.relative(ROOT, dir)}/.venv ready`);
  }
  run(vpy, ['-m', 'pip', 'install', '--quiet', '--upgrade', 'pip'], { cwd: dir });
  run(vpy, ['-m', 'pip', 'install', '--quiet', '-e', '.[dev]'], { cwd: dir });
  writeFileSync(stamp, hash + '\n');
}

function ensureNodeModules() {
  if (existsSync(path.join(WEB, 'node_modules/.bin/vite'))) return log('components/web/node_modules ready');
  run('npm', ['ci'], { cwd: WEB });
}

async function startDb() {
  run('docker', ['compose', 'up', '-d', 'db'], { cwd: BACKEND });
  const id = capture('docker', ['compose', 'ps', '-q', 'db'], { cwd: BACKEND }).stdout.trim();
  if (!id) die('docker compose did not start the db container');
  log('waiting for Postgres to be healthy…');
  for (let i = 0; i < 90; i++) {
    const s = capture('docker', ['inspect', '-f', '{{.State.Health.Status}}', id]).stdout.trim();
    if (s === 'healthy') return log('Postgres is healthy');
    if (s === 'unhealthy') die('Postgres container is unhealthy; see `docker compose logs db` in components/whatsapp/api');
    await new Promise((r) => setTimeout(r, 1000));
  }
  die('timed out waiting for Postgres to become healthy');
}

// ---------------------------------------------------------------- process runner
const COLORS = ['magenta', 'yellow', 'green', 'blue'];
const children = [];
let shuttingDown = false;

function startProc(name, cmd, cmdArgs, opts, color) {
  const label = styleText(['bold', color], `[${name.padEnd(9)}]`);
  // detached => own process group, so we can signal uvicorn's reloader/vite and
  // all of their children together, and the terminal's Ctrl-C reaches only us.
  const child = spawn(cmd, cmdArgs, { ...opts, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const pipe = (stream, out) => {
    let buf = '';
    stream.setEncoding('utf8');
    stream.on('data', (d) => {
      buf += d;
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const l of lines) out.write(`${label} ${l}\n`);
    });
    stream.on('end', () => { if (buf) out.write(`${label} ${buf}\n`); });
  };
  pipe(child.stdout, process.stdout);
  pipe(child.stderr, process.stderr);
  child.on('error', (e) => { console.error(`${label} failed to start: ${e.message}`); shutdown(1); });
  child.on('exit', (code, sig) => {
    child.exited = true;
    console.log(`${label} exited (${sig ?? code})`);
    if (!shuttingDown) {
      log(styleText('red', `${name} stopped unexpectedly; stopping the others`));
      shutdown(code || 1);
    } else if (children.every((c) => c.exited)) {
      log('all processes stopped');
      process.exit(process.exitCode ?? 0);
    }
  });
  children.push(child);
}

function signalGroup(child, sig) {
  if (child.exited) return;
  try { process.kill(-child.pid, sig); } catch { /* already gone */ }
}

function shutdown(code = 0) {
  if (shuttingDown) {
    log('second interrupt: killing now');
    children.forEach((c) => signalGroup(c, 'SIGKILL'));
    process.exit(code || 130);
  }
  shuttingDown = true;
  process.exitCode = code;
  log('stopping all processes (Ctrl-C again to force)…');
  children.forEach((c) => signalGroup(c, 'SIGTERM'));
  setTimeout(() => {
    children.forEach((c) => signalGroup(c, 'SIGKILL'));
    process.exit(code);
  }, 10_000).unref();
  if (children.every((c) => c.exited)) process.exit(code);
}

// ---------------------------------------------------------------- main
const py = checkPrereqs();
if (!SETUP_ONLY) {
  for (const port of [8000, 8001, 5173]) {
    if (await portInUse(port)) die(`port ${port} is already in use (another start:dev running?). Free it and retry.`);
  }
}

await startDb();
ensureEnvFile();
ensureVenv(BACKEND, py);
ensureVenv(DASH, py);
ensureNodeModules();

const env = readEnv(path.join(BACKEND, '.env'));
if (!env.DATABASE_URL?.startsWith('postgresql')) {
  log(styleText('yellow', `warning: DATABASE_URL in components/whatsapp/api/.env is not PostgreSQL (${env.DATABASE_URL}); the dashboard API will use it as well`));
}
// The dashboard API reads the same database and must share JWT_SECRET.
const dashEnv = {
  ...process.env,
  DATABASE_URL: env.DATABASE_URL ?? '',
  JWT_SECRET: env.JWT_SECRET ?? 'change-me-dev-only',
  APP_ENV: 'local',
};
ensureDatabase(env.DATABASE_URL);
const bpy = path.join(BACKEND, '.venv/bin/python');
const dpy = path.join(DASH, '.venv/bin/python');

run(path.join(BACKEND, '.venv/bin/alembic'), ['upgrade', 'head'], { cwd: BACKEND });
if (SKIP_SEED) {
  log('skipping seed (--no-seed / DEV_SKIP_SEED=1)');
} else {
  // Both seeds are idempotent: scripts.seed skips if the demo orgs exist;
  // seed_miami upserts its org/user/areas and only adds reports once.
  run(bpy, ['-m', 'scripts.seed'], { cwd: BACKEND });
  run(dpy, ['-m', 'scripts.seed_miami'], { cwd: DASH, env: dashEnv });
}
if (SETUP_ONLY) { log('setup done (--setup-only)'); process.exit(0); }

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));
process.on('SIGHUP', () => shutdown(0));

const webEnv = { ...process.env, VITE_API_MODE: WEB_MODE };
if (WEB_MODE === 'http') webEnv.VITE_API_BASE_URL ??= 'http://localhost:8000';

startProc('api', path.join(BACKEND, '.venv/bin/uvicorn'),
  ['app.main:app', '--reload', '--port', '8000'], { cwd: BACKEND, env: process.env }, COLORS[0]);
startProc('worker', bpy, ['-u', '-m', 'scripts.worker'], { cwd: BACKEND, env: process.env }, COLORS[1]);
startProc('dashboard', path.join(DASH, '.venv/bin/uvicorn'),
  ['dash.main:app', '--reload', '--port', '8001'], { cwd: DASH, env: dashEnv }, COLORS[2]);
startProc('web', 'npm', ['run', 'dev', '--', '--port', '5173', '--strictPort'], { cwd: WEB, env: webEnv }, COLORS[3]);

log([
  'started:',
  '  backend API    http://localhost:8000/health   (docs: /docs)',
  '  dashboard API  http://localhost:8001/docs     (demo@metron.org / demo-pass)',
  `  web            http://localhost:5173          (api mode: ${WEB_MODE})`,
  '  worker         polling the inbound_event inbox (fake WhatsApp adapter)',
  'Ctrl-C stops everything.',
].join('\n'));
