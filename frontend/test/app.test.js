import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { EditorView } from '@codemirror/view';
import { JSDOM, VirtualConsole } from 'jsdom';

const bundle = readdirSync(new URL('../dist/assets/', import.meta.url)).find((name) => name.endsWith('.js'));
const source = readFileSync(new URL(`../dist/assets/${bundle}`, import.meta.url), 'utf8');
const q = (id, provenance = 'seeded') => ({ questionId: id, topic: 'Arrays', difficulty: 3,
  prompt: `Return the first number (${id}).`, starterCode: 'def solve(values):\n    pass',
  provenance, examples: [{input: [[4, 5]], expected: 4}], techniqueTag: 'indexing' });

async function eventually(check, message) {
  for (let i = 0; i < 150; i++) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.ok(check(), message);
}
function button(window, text) {
  return [...window.document.querySelectorAll('button')].find((b) => b.textContent.trim() === text);
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
function editorView(window) {
  const editor = window.document.querySelector('.cm-editor');
  return editor ? EditorView.findFromDOM(editor) : null;
}
function mount(path, handler) {
  const errors = [];
  const console = new VirtualConsole();
  console.on('jsdomError', (error) => errors.push(error.message));
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: `https://compile.test${path}`, runScripts: 'outside-only', virtualConsole: console,
  });
  const { window } = dom;
  installEditorDomSupport(window);
  const originalTimeout = window.setTimeout.bind(window);
  window.setTimeout = (fn, delay, ...args) => originalTimeout(fn, delay === 8000 ? 10 : delay, ...args);
  window.fetch = async (url, options = {}) => {
    const path = new URL(url, window.location.href).pathname.replace(/^\/v1/, '');
    const result = await handler(path, options.body ? JSON.parse(options.body) : undefined, options);
    return new Response(result.status === 204 ? null : JSON.stringify(result.body ?? result), {
      status: result.status ?? 200, headers: {'Content-Type': 'application/json'},
    });
  };
  window.eval(source);
  return { window, errors, close: () => window.close() };
}

test('mounted App gates direct practice, finishes five baseline questions, checks code and handles generation', async () => {
  let answered = 0;
  let generated = false;
  let checks = 0;
  const requests = [];
  const app = mount('/practice/arrays', async (path, body) => {
    requests.push({path, body});
    if (path === '/learner/init') return {learner: {baselineCompleted: answered === 5}};
    if (path === '/baseline/next') return {question: q(`baseline-${answered}`), completed: false, progress: {answered, total: 5}};
    if (path === '/baseline/submit') {
      assert.equal(body.questionId, `baseline-${answered}`);
      assert.equal(typeof body.code, 'string');
      answered++;
      return {question: answered < 5 ? q(`baseline-${answered}`) : null, verdict: {passed: true, failedCases: []}, completed: answered === 5, progress: {answered, total: 5}};
    }
    if (path.endsWith('/next-question')) return {question: q(generated ? 'generated-1' : 'practice-1', generated ? 'generated' : 'seeded'), learner: {runCheckActions: checks, generationRequests: generated ? 1 : 0}};
    if (path === '/run-check') {
      checks++;
      assert.equal(body.questionId, 'practice-1');
      assert.equal(body.code, 'def solve(values):\n    return values[0]');
      return {passed: true, scored: true, failedCases: [], learner: {runCheckActions: checks}};
    }
    if (path === '/generate') { generated = true; return {status: 202, body: {executionArn: 'pending'}}; }
    if (path.endsWith('/history')) return {entries: []};
    if (path === '/demo-trace') return {entries: checks ? [{eventTimestamp: new Date().toISOString(), provenance: 'Seeded', verificationRetries: 0, masterySnapshot: {topic: 'Arrays', score: 4, confidence: 1}}] : []};
    if (path.startsWith('/reflection/')) return {reflection: null};
    if (path === '/hint') return {level: 1, hint: 'Look at the first index.'};
    throw new Error(`Unexpected request: ${path}`);
  });
  try {
    const {window} = app;
    await eventually(() => window.location.pathname === '/baseline' && editorView(window), 'practice must redirect to baseline');
    assert.equal(requests.some((r) => r.path.endsWith('/next-question')), false);
    for (let i = 0; i < 5; i++) {
      await eventually(() => window.document.body.textContent.includes(`baseline-${i}`) && !button(window, 'Run & Check')?.disabled, 'next baseline question');
      button(window, 'Run & Check').click();
      await eventually(() => answered === i + 1, 'baseline submission');
      await eventually(() => window.document.querySelector('.baseline-verdict')?.textContent.includes('Passed'), 'baseline verdict');
      button(window, i === 4 ? 'Finish assessment' : 'Next question').click();
    }
    await eventually(() => window.document.body.textContent.includes('Your starting point is ready.'), 'baseline completion screen');
    button(window, 'Compile').click();
    await eventually(() => button(window, 'Practice topic'), 'home navigation');
    button(window, 'Practice topic').click();
    await eventually(() => button(window, 'Run & Check'), 'practice renders real editor');
    assert.equal(window.document.body.textContent.includes('Technique: indexing'), false);
    const editor = editorView(window);
    assert.ok(editor, 'practice renders a CodeMirror EditorView');
    editor.dispatch({
      changes: {
        from: 0,
        to: editor.state.doc.length,
        insert: 'def solve(values):\n    return values[0]',
      },
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    button(window, 'Run & Check').click();
    await eventually(() => window.document.querySelector('.practice-verdict')?.textContent.includes('Passed'), 'passing verdict renders');
    button(window, 'Reveal Nudge').click();
    await eventually(() => window.document.body.textContent.includes('Look at the first index.'), 'hint targets active question');
    assert.equal(requests.find((r) => r.path === '/hint').body.questionId, 'practice-1');
    button(window, 'Generate another').click();
    await eventually(() => window.document.body.textContent.includes('generated-1'), 'async acknowledgement resolves to a real question');
    assert.equal(editorView(window).state.doc.toString(), q('generated-1').starterCode);
    assert.deepEqual(app.errors, []);
  } finally { app.close(); }
});

test('completed topics render a completion state without an editor or execution controls', async () => {
  const app = mount('/practice/strings', async (path) => {
    if (path === '/learner/init') return {learner: {baselineCompleted: true}};
    if (path.endsWith('/next-question')) return {question: null, completed: true};
    if (path.endsWith('/history') || path === '/demo-trace') return {entries: []};
    throw new Error(path);
  });
  try {
    await eventually(() => app.window.document.body.textContent.includes('completed the available questions'), 'completed topic message');
    assert.equal(app.window.document.querySelector('.cm-editor'), null);
    assert.equal(button(app.window, 'Run & Check'), undefined);
    assert.deepEqual(app.errors, []);
  } finally { app.close(); }
});

test('quota denial keeps material visible and disables expensive actions', async () => {
  const app = mount('/practice/arrays', async (path) => {
    if (path === '/learner/init') return {learner: {baselineCompleted: true}};
    if (path.endsWith('/next-question')) return {question: q('practice-1')};
    if (path.endsWith('/history') || path === '/demo-trace') return {entries: []};
    if (path.startsWith('/reflection/')) return {reflection: null};
    if (path === '/run-check') return {status: 429, body: {error: 'Demo execution quota exhausted.'}};
    throw new Error(path);
  });
  try {
    await eventually(() => button(app.window, 'Run & Check'), 'practice controls');
    button(app.window, 'Run & Check').click();
    await eventually(() => app.window.document.body.textContent.includes('Demo execution quota exhausted.'), 'server error text');
    assert.equal(button(app.window, 'Run & Check').disabled, true);
    assert.equal(button(app.window, 'Generate another').disabled, true);
    assert.equal(button(app.window, 'Reveal Nudge').disabled, false);
    assert.ok(app.window.document.body.textContent.includes('Return the first number'));
    assert.deepEqual(app.errors, []);
  } finally { app.close(); }
});

test('previous reflections expose playback and successfully handle an empty 204 delete response', async () => {
  let deleted = false;
  const app = mount('/practice/arrays', async (path, body, options) => {
    if (path === '/learner/init') return {learner: {baselineCompleted: true}};
    if (path.endsWith('/next-question')) return {question: q('practice-1')};
    if (path.endsWith('/history')) return {entries: [{question: q('previous-1'), passed: true}]};
    if (path === '/demo-trace') return {entries: []};
    if (path === '/reflection/practice-1') return {reflection: null};
    if (path === '/reflection/previous-1') {
      if (options.method === 'DELETE') { deleted = true; return {status: 204}; }
      return {reflection: {playbackUrl: 'https://example.test/private-audio', expiresAt: '2030-01-01T00:00:00Z'}};
    }
    throw new Error(path);
  });
  try {
    await eventually(() => button(app.window, 'Passed · Return the first number (previous-1).'), 'attempt history');
    button(app.window, 'Passed · Return the first number (previous-1).').click();
    await eventually(() => app.window.document.querySelector('audio'), 'reflection playback');
    assert.equal(app.window.document.querySelector('audio').src, 'https://example.test/private-audio');
    button(app.window, 'Delete recording').click();
    await eventually(() => deleted && !app.window.document.querySelector('audio'), '204 delete clears recording');
    assert.equal(app.window.document.querySelector('.reflection-error'), null);
    assert.deepEqual(app.errors, []);
  } finally { app.close(); }
});
