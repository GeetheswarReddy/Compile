import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { EditorView } from '@codemirror/view';
import { JSDOM, VirtualConsole } from 'jsdom';

const bundle = readdirSync(new URL('../dist/assets/', import.meta.url)).find((name) => name.endsWith('.js'));
const source = readFileSync(new URL(`../dist/assets/${bundle}`, import.meta.url), 'utf8');
const question = (questionId) => ({
  questionId,
  topic: 'Arrays',
  difficulty: 3,
  prompt: `Keep this question (${questionId}).`,
  starterCode: 'def solve(values):\n    pass',
  examples: [{ input: [[4, 5]], expected: 4 }],
});

async function eventually(check, message) {
  for (let index = 0; index < 150; index += 1) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.ok(check(), message);
}

function button(window, text) {
  return [...window.document.querySelectorAll('button')]
    .find((candidate) => candidate.textContent.trim() === text);
}

function type(window, node, value) {
  Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(node, value);
  node.dispatchEvent(new window.Event('input', { bubbles: true }));
}

function installEditorDomSupport(window) {
  window.requestAnimationFrame = (callback) => window.setTimeout(() => callback(Date.now()), 0);
  window.cancelAnimationFrame = (handle) => window.clearTimeout(handle);
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  window.Range.prototype.getClientRects = () => [];
  window.Range.prototype.getBoundingClientRect = () => ({
    bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0,
  });
}

function mount(path, handler) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', (error) => errors.push(error.message));
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: `https://compile.test${path}`,
    runScripts: 'outside-only',
    virtualConsole,
  });
  const { window } = dom;
  installEditorDomSupport(window);
  window.addEventListener('unhandledrejection', (event) => {
    errors.push(event.reason?.message || String(event.reason));
  });
  window.fetch = async (url, options = {}) => {
    const requestPath = new URL(url, window.location.href).pathname.replace(/^\/v1/, '');
    const body = options.body && !(options.body instanceof window.FormData)
      ? JSON.parse(options.body)
      : undefined;
    const result = await handler(requestPath, body, options);
    return new Response(result.status === 204 ? null : JSON.stringify(result.body ?? result), {
      status: result.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  window.eval(source);
  return { window, errors, close: () => window.close() };
}

function editorView(window) {
  const editor = window.document.querySelector('.cm-editor');
  return editor ? EditorView.findFromDOM(editor) : null;
}

function supportResponse(path) {
  if (path.endsWith('/history') || path === '/demo-trace') return { entries: [] };
  if (path.startsWith('/reflection/')) return { reflection: null };
  return null;
}

test('initialization connectivity failure retries without replacing browser identity', async () => {
  let attempts = 0;
  const learnerIds = [];
  const app = mount('/', async (path, body, options) => {
    assert.equal(path, '/learner/init');
    learnerIds.push(options.headers['X-Learner-Id']);
    attempts += 1;
    if (attempts === 1) throw new TypeError('Failed to fetch');
    return { learner: { baselineCompleted: false } };
  });

  try {
    await eventually(() => button(app.window, 'Try again'), 'recoverable initialization error');
    assert.ok(app.window.document.body.textContent.includes('Check your connection'));
    assert.equal(button(app.window, 'Take the baseline assessment'), undefined);
    button(app.window, 'Try again').click();
    await eventually(() => button(app.window, 'Take the baseline assessment'), 'successful initialization retry');
    assert.equal(attempts, 2);
    assert.equal(learnerIds[0], learnerIds[1]);
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('practice network failure preserves code and question, then retries the same payload', async () => {
  const submissions = [];
  const app = mount('/practice/arrays', async (path, body) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path.endsWith('/next-question')) return { question: question('practice-keep') };
    const support = supportResponse(path);
    if (support) return support;
    if (path === '/run-check') {
      submissions.push(body);
      if (submissions.length === 1) throw new TypeError('Failed to fetch');
      return { passed: false, failedCases: [], learner: { runCheckActions: 2 } };
    }
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => editorView(app.window) && button(app.window, 'Run & Check'), 'practice controls');
    const editor = editorView(app.window);
    const code = 'def solve(values):\n    return values[-1]';
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: code } });
    await new Promise((resolve) => setTimeout(resolve, 0));
    button(app.window, 'Run & Check').click();
    await eventually(() => app.window.document.body.textContent.includes('Check your connection'), 'network failure');
    assert.ok(app.window.document.body.textContent.includes('practice-keep'));
    assert.equal(editor.state.doc.toString(), code);
    button(app.window, 'Run & Check').click();
    await eventually(() => app.window.document.body.textContent.includes('Not quite yet'), 'successful retry verdict');
    assert.deepEqual(submissions, [
      { questionId: 'practice-keep', code },
      { questionId: 'practice-keep', code },
    ]);
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('baseline server failure exits pending state, prevents duplicates, and preserves the resume point', async () => {
  let releaseFirst;
  let submitCalls = 0;
  const submissions = [];
  const app = mount('/baseline', async (path, body) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: false } };
    if (path === '/baseline/next') {
      return { question: question('baseline-keep'), completed: false, progress: { answered: 2, total: 5 } };
    }
    if (path === '/baseline/submit') {
      submitCalls += 1;
      submissions.push(body);
      if (submitCalls === 1) {
        return new Promise((resolve) => { releaseFirst = () => resolve({ status: 503, body: {} }); });
      }
      return { question: question('baseline-next'), completed: false, progress: { answered: 3, total: 5 } };
    }
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => button(app.window, 'Continue'), 'baseline controls');
    const editor = app.window.document.querySelector('#baseline-code');
    const code = 'def solve(values):\n    return len(values)';
    type(app.window, editor, code);
    button(app.window, 'Continue').click();
    button(app.window, 'Checking…')?.click();
    await eventually(() => submitCalls === 1 && typeof releaseFirst === 'function', 'single pending request');
    releaseFirst();
    await eventually(() => app.window.document.body.textContent.includes('service could not complete'), 'server failure');
    assert.equal(editor.value, code);
    assert.ok(app.window.document.body.textContent.includes('baseline-keep'));
    assert.equal(button(app.window, 'Continue').disabled, false);
    button(app.window, 'Continue').click();
    await eventually(() => app.window.document.body.textContent.includes('baseline-next'), 'baseline retry advances');
    assert.deepEqual(submissions, [
      { questionId: 'baseline-keep', code },
      { questionId: 'baseline-keep', code },
    ]);
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('quota denial leaves practice material visible and disables execution actions', async () => {
  const app = mount('/practice/arrays', async (path) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path.endsWith('/next-question')) return { question: question('quota-visible') };
    const support = supportResponse(path);
    if (support) return support;
    if (path === '/run-check') return { status: 429, body: { error: 'Demo execution quota exhausted.' } };
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => button(app.window, 'Run & Check'), 'practice controls');
    button(app.window, 'Run & Check').click();
    await eventually(() => app.window.document.body.textContent.includes('Demo execution quota exhausted.'), 'quota explanation');
    assert.ok(app.window.document.body.textContent.includes('quota-visible'));
    assert.equal(button(app.window, 'Run & Check').disabled, true);
    assert.equal(button(app.window, 'Generate another').disabled, true);
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});
