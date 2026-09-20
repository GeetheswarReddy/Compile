import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { EditorView } from '@codemirror/view';
import { JSDOM, VirtualConsole } from 'jsdom';

const bundle = readdirSync(new URL('../dist/assets/', import.meta.url)).find((name) => name.endsWith('.js'));
const source = readFileSync(new URL(`../dist/assets/${bundle}`, import.meta.url), 'utf8');

const question = (questionId, options = {}) => ({
  questionId,
  topic: 'Arrays',
  difficulty: 3,
  prompt: `Return the first value (${questionId}).`,
  starterCode: options.starterCode ?? 'def solve(values):\n    pass',
  examples: [{ input: [[4, 5]], expected: 4 }],
  readOnly: options.readOnly ?? false,
});

async function eventually(check, message, errors = []) {
  for (let index = 0; index < 150; index += 1) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.ok(check(), `${message}${errors.length ? `: ${errors.join('; ')}` : ''}`);
}

function button(window, text) {
  return [...window.document.querySelectorAll('button')]
    .find((candidate) => candidate.textContent.trim() === text);
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

function mount(handler) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', (error) => errors.push(error.message));
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'https://compile.test/practice/arrays',
    runScripts: 'outside-only',
    virtualConsole,
  });
  const { window } = dom;
  installEditorDomSupport(window);
  window.fetch = async (url, options = {}) => {
    const requestPath = new URL(url, window.location.href).pathname.replace(/^\/v1/, '');
    const body = options.body ? JSON.parse(options.body) : undefined;
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

function support(path) {
  if (path.endsWith('/history') || path === '/demo-trace') return { entries: [] };
  if (path.startsWith('/reflection/')) return { reflection: null };
  return null;
}

test('CodeMirror controls practice code, applies Python indentation, and accepts question replacement', async () => {
  let questionCalls = 0;
  const submissions = [];
  const first = question('editor-first');
  const second = question('editor-second', { starterCode: 'def solve(items):\n    return items[-1]' });
  const app = mount(async (path, body) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path.endsWith('/next-question')) {
      questionCalls += 1;
      return { question: questionCalls === 1 ? first : second };
    }
    if (path === '/run-check') {
      submissions.push(body);
      return { passed: true, failedCases: [] };
    }
    const response = support(path);
    if (response) return response;
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => editorView(app.window), 'CodeMirror editor renders', app.errors);
    const view = editorView(app.window);
    const content = app.window.document.querySelector('.cm-content');
    assert.equal(content.getAttribute('aria-label'), 'Your Python solution');
    assert.equal(content.getAttribute('role'), 'textbox');
    assert.equal(content.getAttribute('contenteditable'), 'true');
    assert.ok(app.window.document.querySelector('.cm-lineNumbers'));
    assert.equal(app.window.document.querySelector('.practice-editor__language').textContent, 'Python');
    assert.equal(app.window.document.querySelector('.practice-editor__key-help').textContent, 'Tab moves focus');

    const header = 'def solve(values):';
    view.dispatch({ selection: { anchor: header.length } });
    content.dispatchEvent(new app.window.KeyboardEvent('keydown', {
      bubbles: true,
      cancelable: true,
      code: 'Enter',
      key: 'Enter',
    }));
    assert.equal(view.state.doc.toString(), `${header}\n    \n    pass`);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const editedCode = `${header}\n    return values[0]`;
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: editedCode } });
    await new Promise((resolve) => setTimeout(resolve, 0));

    await eventually(() => button(app.window, 'Run & Check'), 'practice actions remain available', app.errors);
    button(app.window, 'Run & Check').click();
    await eventually(() => submissions.length === 1, 'controlled value reaches submission', app.errors);
    assert.deepEqual(submissions[0], {
      questionId: first.questionId,
      code: editedCode,
    });

    await eventually(() => !button(app.window, 'Next question').disabled, 'next question becomes available', app.errors);
    button(app.window, 'Next question').click();
    await eventually(
      () => editorView(app.window)?.state.doc.toString() === second.starterCode,
      'external question value replaces editor content',
      app.errors,
    );
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('CodeMirror exposes and enforces the disabled read-only state', async () => {
  const readonlyQuestion = question('editor-readonly', { readOnly: true });
  const app = mount(async (path) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path.endsWith('/next-question')) return { question: readonlyQuestion };
    const response = support(path);
    if (response) return response;
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => editorView(app.window), 'read-only CodeMirror editor renders', app.errors);
    const view = editorView(app.window);
    const before = view.state.doc.toString();
    const content = app.window.document.querySelector('.cm-content');
    assert.equal(content.getAttribute('contenteditable'), 'false');
    assert.equal(content.getAttribute('aria-readonly'), 'true');
    assert.equal(content.getAttribute('aria-disabled'), 'true');
    assert.equal(content.getAttribute('tabindex'), '-1');
    content.dispatchEvent(new app.window.KeyboardEvent('keydown', {
      bubbles: true,
      cancelable: true,
      code: 'Enter',
      key: 'Enter',
    }));
    assert.equal(view.state.doc.toString(), before);
    assert.equal(button(app.window, 'Run & Check').disabled, true);
    assert.ok(app.window.document.querySelector('.practice-editor__note'));
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});
