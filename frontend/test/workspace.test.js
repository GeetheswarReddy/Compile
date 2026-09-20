import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { EditorView } from '@codemirror/view';
import { JSDOM, VirtualConsole } from 'jsdom';

const bundle = readdirSync(new URL('../dist/assets/', import.meta.url)).find((name) => name.endsWith('.js'));
const source = readFileSync(new URL(`../dist/assets/${bundle}`, import.meta.url), 'utf8');

const question = {
  questionId: 'workspace-question',
  topic: 'Arrays',
  difficulty: 4,
  prompt: 'Return the first value while preserving the input.',
  starterCode: 'def solve(values):\n    pass',
  provenance: 'generated',
  techniqueTag: 'indexing',
  functionSignature: 'def solve(values: list[int]) -> int:',
  examples: [{ input: [[7, 8]], expected: 7 }],
  constraints: ['1 <= len(values) <= 100', 'values contain integers'],
};

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

test('practice workspace keeps question, trace, editor, actions, and bounded results in their regions', async () => {
  let releaseQuestion;
  let traceCalls = 0;
  let checked = false;
  const app = mount('/practice/arrays', async (path) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path.endsWith('/next-question')) {
      return new Promise((resolve) => { releaseQuestion = () => resolve({ question }); });
    }
    if (path.endsWith('/history')) return { entries: [] };
    if (path.startsWith('/reflection/')) return { reflection: null };
    if (path === '/demo-trace') {
      traceCalls += 1;
      if (checked) return { status: 503, body: {} };
      return { entries: [{
        eventTimestamp: '2026-09-20T08:00:00Z',
        provenance: 'Generated',
        verificationRetries: 2,
        masterySnapshot: { topic: 'Arrays', score: 6, confidence: 0.8 },
      }] };
    }
    if (path === '/run-check') {
      checked = true;
      return {
        passed: false,
        failedCases: [
          { input: [[1]], expected: 1, actual: null },
          { input: [[2]], expected: 2, actual: null },
          { input: [[3]], expected: 3, actual: null },
        ],
      };
    }
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => typeof releaseQuestion === 'function', 'question request starts');
    assert.equal(app.window.document.querySelector('[aria-busy="true"]')?.textContent.includes('Finding your next question'), true);
    releaseQuestion();
    await eventually(() => app.window.document.querySelector('.practice-workspace'), 'workspace renders');

    const { document, Node } = app.window;
    const workspace = document.querySelector('.practice-workspace');
    const questionPane = workspace.querySelector('.practice-question-pane');
    const solutionPane = workspace.querySelector('.practice-solution-pane');
    const traceSlot = workspace.querySelector('.practice-trace-slot');
    const separator = workspace.querySelector('[role="separator"]');
    assert.ok(questionPane && solutionPane);
    assert.ok(separator, 'desktop workspace exposes a pane resizer');
    const initialSize = Number(separator.getAttribute('aria-valuenow'));
    separator.dispatchEvent(new app.window.KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'ArrowRight' }));
    await eventually(() => Number(separator.getAttribute('aria-valuenow')) === initialSize + 5, 'keyboard resizes practice panes');
    assert.equal(workspace.style.getPropertyValue('--workspace-left'), `${initialSize + 5}%`);
    assert.ok(questionPane.compareDocumentPosition(solutionPane) & Node.DOCUMENT_POSITION_FOLLOWING);
    assert.ok(questionPane.textContent.includes('Generated for your level'));
    assert.ok(questionPane.textContent.includes('Input: [[7,8]]'));
    assert.ok(questionPane.textContent.includes('1 <= len(values) <= 100'));
    await eventually(() => solutionPane.querySelector('.cm-content[role="textbox"][aria-label="Your Python solution"]'), 'practice editor mounts');
    const editorContent = solutionPane.querySelector('.cm-content[role="textbox"][aria-label="Your Python solution"]');
    assert.ok(editorContent);
    assert.ok(EditorView.findFromDOM(editorContent.closest('.cm-editor')));
    assert.ok(solutionPane.querySelector('[aria-label="Solution actions"]'));

    if (traceSlot) {
      assert.equal(workspace.classList.contains('has-trace'), true);
      await eventually(
        () => document.querySelector('.practice-trace-slot')?.textContent.includes('Verification retries'),
        'populated trace renders',
      );
      const currentTraceSlot = document.querySelector('.practice-trace-slot');
      assert.ok(currentTraceSlot.compareDocumentPosition(solutionPane) & Node.DOCUMENT_POSITION_FOLLOWING);
      assert.ok(currentTraceSlot.textContent.includes('Generated'));
      assert.ok(currentTraceSlot.textContent.includes('80%'));
    } else {
      assert.equal(workspace.classList.contains('has-trace'), false);
      assert.equal(traceCalls, 0, 'disabled trace is not fetched');
    }

    button(app.window, 'Run & Check').click();
    await eventually(() => solutionPane.querySelector('.practice-verdict'), 'result renders below editor actions');
    const failures = solutionPane.querySelectorAll('.practice-verdict li');
    assert.equal(failures.length, 2, 'only two failed cases are exposed');
    assert.ok(solutionPane.querySelector('.practice-actions').compareDocumentPosition(solutionPane.querySelector('.practice-verdict')) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (traceSlot) {
      await eventually(
        () => document.querySelector('.practice-trace-slot')?.textContent.includes('Could not load demo details.'),
        'trace refreshes after an attempt',
      );
      assert.ok(traceCalls >= 2);
    }
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('baseline uses the same question-left and solution-right landmark order', async () => {
  const app = mount('/baseline', async (path) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: false } };
    if (path === '/baseline/next') return {
      question,
      completed: false,
      progress: { answered: 1, total: 5 },
    };
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => app.window.document.querySelector('.baseline-workspace'), 'baseline workspace renders');
    const { document, Node } = app.window;
    const workspace = document.querySelector('.baseline-workspace');
    const questionPane = workspace.querySelector('.baseline-question-pane');
    const solutionPane = workspace.querySelector('.baseline-solution-pane');
    const separator = workspace.querySelector('[role="separator"]');
    assert.ok(questionPane && solutionPane);
    assert.ok(separator, 'baseline workspace exposes a pane resizer');
    assert.ok(questionPane.compareDocumentPosition(solutionPane) & Node.DOCUMENT_POSITION_FOLLOWING);
    assert.ok(questionPane.textContent.includes(question.prompt));
    assert.ok(questionPane.textContent.includes('values contain integers'));
    await eventually(() => solutionPane.querySelector('.cm-content[aria-label="Your Python solution"]'), 'baseline editor mounts');
    assert.ok(solutionPane.querySelector('.cm-content[aria-label="Your Python solution"]'));
    assert.ok(solutionPane.querySelector('.cm-lineNumbers'));
    assert.equal(solutionPane.querySelector('.practice-editor__language')?.textContent, 'Python');
    assert.equal(solutionPane.querySelector('button[type="submit"]')?.textContent, 'Run & Check');
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});

test('completed baseline status shows five-question progress and topic mastery', async () => {
  const app = mount('/baseline', async (path) => {
    if (path === '/learner/init') return { learner: { baselineCompleted: true } };
    if (path === '/baseline/next') return {
      question: null,
      completed: true,
      progress: { answered: 5, total: 5 },
      mastery: [
        { topic: 'Arrays', score: 6, confidence: 1 },
        { topic: 'Strings', score: 4, confidence: 0.9 },
        { topic: 'Hash Maps/Two Pointers', score: 5, confidence: 0.8 },
      ],
    };
    throw new Error(`Unexpected request: ${path}`);
  });

  try {
    await eventually(() => app.window.document.querySelector('.baseline-summary'), 'baseline summary renders');
    const summary = app.window.document.querySelector('.baseline-summary');
    assert.ok(summary.textContent.includes('Baseline complete · 5/5'));
    assert.ok(summary.textContent.includes('Arrays'));
    assert.ok(summary.textContent.includes('6/10'));
    assert.ok(summary.textContent.includes('Strings'));
    assert.ok(summary.textContent.includes('Hash Maps/Two Pointers'));
    assert.deepEqual(app.errors, []);
  } finally {
    app.close();
  }
});
