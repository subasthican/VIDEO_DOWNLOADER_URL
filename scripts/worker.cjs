const { loadEnvConfig } = require('@next/env');
const { spawn } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
loadEnvConfig(root, true);
const bin = path.join(root, 'worker', '.venv', process.platform === 'win32' ? 'Scripts' : 'bin');
const python = path.join(bin, process.platform === 'win32' ? 'python.exe' : 'python');
if (!existsSync(python)) {
  console.error('Create worker/.venv and install worker/requirements.txt first. See README.md.');
  process.exit(1);
}

const worker = spawn(python, ['-m', 'uvicorn', 'main:app', '--app-dir', 'worker', '--host', '127.0.0.1', '--port', '8000'], {
  cwd: root,
  stdio: 'inherit',
  env: { ...process.env, PATH: bin + path.delimiter + process.env.PATH },
});
worker.on('error', error => { console.error(error.message); process.exitCode = 1; });
worker.on('exit', code => { process.exitCode = code ?? 1; });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => worker.kill(signal));
