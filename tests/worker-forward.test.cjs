const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const ts = require('typescript');

// Compile the server helper as CommonJS so tests use Next's real Response implementation.
const filename = require.resolve('../lib/worker.ts');
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, filename);
const { forward } = compiled.exports;

function configure(t, { internal, external } = {}) {
  const original = { ...process.env };
  process.env.VIDEO_WORKER_SECRET = 'test-secret-for-forwarding-only';
  delete process.env.VIDEO_WORKER_INTERNAL_URL;
  delete process.env.VIDEO_WORKER_URL;
  if (internal) process.env.VIDEO_WORKER_INTERNAL_URL = internal;
  if (external) process.env.VIDEO_WORKER_URL = external;
  t.after(() => { process.env = original; });
}

test('the service binding wins over stale external worker configuration', async t => {
  configure(t, { internal: 'https://worker.internal/', external: 'http://localhost:8000' });
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://worker.internal/download');
    assert.equal(options.headers.Authorization, 'Bearer test-secret-for-forwarding-only');
    return Response.json({ url: '/file/signed-ticket' });
  });
  const response = await forward(new Request('https://site.example/api/download', {
    method: 'POST', body: JSON.stringify({ token: 'token', quality: '360' }),
  }), 'download');
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { url: '/file/signed-ticket' });
});

test('standalone workers return reachable absolute download URLs', async t => {
  configure(t, { external: 'http://localhost:8000' });
  t.mock.method(globalThis, 'fetch', async () => Response.json({ url: '/file/signed-ticket' }));
  const response = await forward(new Request('http://localhost:3000/api/download', {
    method: 'POST', body: '{}',
  }), 'download');
  assert.deepEqual(await response.json(), { url: 'http://localhost:8000/file/signed-ticket' });
});

test('source errors reach the page without exposing internal service URLs', async t => {
  configure(t, { internal: 'https://worker.internal' });
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Video unavailable' }, { status: 422 }));
  const response = await forward(new Request('https://site.example/api/analyze', {
    method: 'POST', body: '{}',
  }), 'analyze');
  assert.equal(response.status, 422);
  assert.deepEqual(await response.json(), { detail: 'Video unavailable' });
});
